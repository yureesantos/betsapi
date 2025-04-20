# db/database.py
import psycopg2
import time
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from config.settings import DATABASE_URL, RETRY_DELAY_SECONDS, TIMEZONE
from datetime import datetime, timedelta
import pytz


@contextmanager
def get_db_connection():
    """Fornece uma conexão gerenciada com o banco de dados."""
    conn = None
    retries = 3
    delay = RETRY_DELAY_SECONDS
    while retries > 0:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            yield conn
            conn.commit()  # Commit final se tudo correu bem no bloco 'with'
            break  # Sai do loop se conectou
        except psycopg2.OperationalError as e:
            print(f"Erro ao conectar ao banco de dados: {e}. Tentando novamente em {delay}s...")
            retries -= 1
            if retries == 0:
                print("Erro: Não foi possível conectar ao banco de dados após várias tentativas.")
                raise  # Re-levanta a exceção original se esgotarem as tentativas
            time.sleep(delay)
            delay *= 2  # Backoff exponencial simples
        except Exception as e:
            print(f"Erro inesperado de banco de dados: {e}")
            if conn:
                conn.rollback()  # Rollback em caso de outros erros no bloco 'with'
            raise  # Re-levanta a exceção
        finally:
            if conn:
                conn.close()


def create_db_connection():
    """Cria e retorna uma conexão direta ao banco de dados (sem context manager).
    Esta função deve ser usada para operações paralelas onde o controle da conexão
    precisa ser gerenciado manualmente."""
    retries = 3
    delay = RETRY_DELAY_SECONDS
    while retries > 0:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False  # Exige commit explícito
            return conn
        except psycopg2.OperationalError as e:
            print(f"Erro ao conectar ao banco de dados: {e}. Tentando novamente em {delay}s...")
            retries -= 1
            if retries == 0:
                print("Erro: Não foi possível conectar ao banco de dados após várias tentativas.")
                raise  # Re-levanta a exceção original se esgotarem as tentativas
            time.sleep(delay)
            delay *= 2  # Backoff exponencial simples
    return None  # Não deveria chegar aqui devido ao raise, mas para clareza


@contextmanager
def get_cursor(conn):
    """Fornece um cursor gerenciado."""
    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)  # Retorna dicts em vez de tuplas
        yield cursor
    finally:
        if cursor:
            cursor.close()


def get_fetch_state(conn, fetch_type="ended_events"):
    """Busca o estado atual da coleta no banco de dados."""
    query = "SELECT last_processed_page, last_processed_timestamp, status FROM fetch_state WHERE fetch_type = %s;"
    try:
        with get_cursor(conn) as cur:
            cur.execute(query, (fetch_type,))
            state = cur.fetchone()
            if state:
                return state
            else:
                # Se não houver estado, cria um inicial
                print(f"Nenhum estado encontrado para '{fetch_type}'. Criando estado inicial.")
                cur.execute(
                    """
                    INSERT INTO fetch_state (fetch_type, last_processed_page, status)
                    VALUES (%s, 0, 'idle')
                    ON CONFLICT (fetch_type) DO NOTHING
                    RETURNING last_processed_page, last_processed_timestamp, status;
                """,
                    (fetch_type,),
                )
                conn.commit()  # Commit a inserção
                # Tenta buscar novamente após inserir
                cur.execute(query, (fetch_type,))
                state_after_insert = cur.fetchone()
                if not state_after_insert:  # Se ainda assim não encontrar, pode ser um problema
                    print(
                        f"Aviso: Não foi possível criar ou encontrar estado inicial para {fetch_type} após tentativa de inserção."
                    )
                    return {"last_processed_page": 0, "last_processed_timestamp": None, "status": "unknown"}
                return state_after_insert
    except Exception as e:
        print(f"Erro ao buscar estado da coleta: {e}")
        raise


def update_fetch_state(conn, fetch_type, page=None, timestamp=None, status=None):
    """Atualiza o estado da coleta no banco de dados."""
    updates = []
    params = []

    if page is not None:
        updates.append("last_processed_page = %s")
        params.append(page)
    if timestamp is not None:
        updates.append("last_processed_timestamp = %s")
        params.append(timestamp)
    if status is not None:
        updates.append("status = %s")
        params.append(status)

    updates.append("updated_at = now()")  # Sempre atualiza o timestamp

    if not updates:
        print("Nenhum campo para atualizar no estado da coleta.")
        return

    query = f"UPDATE fetch_state SET {', '.join(updates)} WHERE fetch_type = %s;"
    params.append(fetch_type)

    try:
        with get_cursor(conn) as cur:
            cur.execute(query, tuple(params))
        # Não precisa de commit aqui, pois é gerenciado pelo 'with get_db_connection'
        # print(f"Estado da coleta '{fetch_type}' atualizado: page={page}, status={status}")
    except Exception as e:
        print(f"Erro ao atualizar estado da coleta: {e}")
        raise


def upsert_event(conn, event):
    """Insere ou atualiza um evento na tabela 'events'."""
    query = """
    INSERT INTO events (
        event_id, sport_id, league_id, league_name, event_timestamp,
        home_team_id, home_team_name, home_player_name,
        away_team_id, away_team_name, away_player_name,
        final_score, has_odds, last_odds_update, inserted_at
    ) VALUES (
        %(event_id)s, %(sport_id)s, %(league_id)s, %(league_name)s, %(event_timestamp)s,
        %(home_team_id)s, %(home_team_name)s, %(home_player_name)s,
        %(away_team_id)s, %(away_team_name)s, %(away_player_name)s,
        %(final_score)s, %(has_odds)s, %(last_odds_update)s, NOW()
    )
    ON CONFLICT (event_id) DO UPDATE SET
        sport_id = EXCLUDED.sport_id,
        league_id = EXCLUDED.league_id,
        league_name = EXCLUDED.league_name,
        event_timestamp = EXCLUDED.event_timestamp,
        home_team_id = EXCLUDED.home_team_id,
        home_team_name = EXCLUDED.home_team_name,
        home_player_name = EXCLUDED.home_player_name,
        away_team_id = EXCLUDED.away_team_id,
        away_team_name = EXCLUDED.away_team_name,
        away_player_name = EXCLUDED.away_player_name,
        final_score = COALESCE(EXCLUDED.final_score, events.final_score),
        has_odds = COALESCE(EXCLUDED.has_odds, events.has_odds),
        last_odds_update = COALESCE(EXCLUDED.last_odds_update, events.last_odds_update)
    RETURNING event_id;
    """
    try:
        with get_cursor(conn) as cur:
            # Garantir que valores numéricos sejam realmente numéricos ou None
            event["event_id"] = int(event["event_id"])
            event["sport_id"] = int(event["sport_id"]) if event.get("sport_id") is not None else None
            event["league_id"] = int(event["league_id"]) if event.get("league_id") is not None else None
            event["home_team_id"] = int(event["home_team_id"]) if event.get("home_team_id") is not None else None
            event["away_team_id"] = int(event["away_team_id"]) if event.get("away_team_id") is not None else None

            cur.execute(query, event)
            result = cur.fetchone()
            return result["event_id"] if result else None
    except ValueError as ve:
        print(f"Erro de conversão de tipo ao preparar evento {event.get('event_id', 'N/A')}: {ve}")
        print(f"Dados do evento: {event}")
        raise
    except Exception as e:
        print(f"Erro ao inserir/atualizar evento {event.get('event_id', 'N/A')}: {e}")
        # print(f"Dados do evento: {event}") # Descomentar para depuração
        # conn.rollback() # Rollback gerenciado pelo context manager
        raise


def insert_odds(conn, odds_list):
    """Insere uma lista de registros de odds na tabela 'odds'."""
    if not odds_list:
        return 0

    # Query para inserir UMA linha, usada dentro do loop para tratamento individual
    query_single = """
    INSERT INTO odds (
        event_id, bookmaker, odds_market, odds_timestamp, odds_data, collection_timestamp
    ) VALUES (
        %(event_id)s, %(bookmaker)s, %(odds_market)s, %(odds_timestamp)s, %(odds_data)s, NOW()
    )
    ON CONFLICT DO NOTHING; -- Evita duplicatas exatas
    """
    inserted_count = 0
    with get_cursor(conn) as cur:
        for odds_item in odds_list:
            try:
                # Garantir tipos corretos
                odds_item["event_id"] = int(odds_item["event_id"])
                # odds_data já deve ser string JSON

                cur.execute(query_single, odds_item)
                if cur.rowcount > 0:
                    inserted_count += 1
            except ValueError as ve:
                print(f"Erro de tipo ao preparar odds para evento {odds_item.get('event_id', 'N/A')}: {ve}")
                print(f"Dados da odd: {odds_item}")
                # Pula esta odd específica, mas continua as outras
            except Exception as e:
                print(f"Erro ao inserir odd para evento {odds_item.get('event_id', 'N/A')}: {e}")
                print(f"Dados da odd: {odds_item}")
                # Considerar se deve parar tudo ou apenas pular esta odd
                # Por enquanto, vamos pular esta e continuar

    # print(f"Inserido {inserted_count} / {len(odds_list)} registros de odds para evento {odds_list[0]['event_id']} (após tratamento individual).")
    return inserted_count


def update_event_odds_status(conn, event_id, has_odds, last_update_time):
    """Atualiza o status das odds para um evento específico."""
    query = """
    UPDATE events
    SET has_odds = %s, last_odds_update = %s
    WHERE event_id = %s;
    """
    try:
        with get_cursor(conn) as cur:
            cur.execute(query, (has_odds, last_update_time, int(event_id)))  # Garante ID int
            # print(f"Status das odds atualizado para evento {event_id}: has_odds={has_odds}")
    except Exception as e:
        print(f"Erro ao atualizar status das odds para evento {event_id}: {e}")
        raise


def delete_old_events(conn, days_to_keep=60):
    """Deleta eventos mais antigos que um número específico de dias."""
    if days_to_keep <= 0:
        print("Erro: Número de dias para manter deve ser positivo.")
        return 0

    # Calcula a data de corte no timezone local configurado
    local_tz = pytz.timezone(TIMEZONE)
    cutoff_date_local = datetime.now(local_tz) - timedelta(days=days_to_keep)
    # Converte para UTC para comparar com TIMESTAMPTZ no banco
    cutoff_date_utc = cutoff_date_local.astimezone(pytz.utc)

    # Deleta baseado no timestamp do evento
    query = "DELETE FROM events WHERE event_timestamp < %s;"
    deleted_count = 0
    print(f"Deletando eventos com timestamp anterior a {cutoff_date_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}...")

    try:
        with get_cursor(conn) as cur:
            cur.execute(query, (cutoff_date_utc,))
            deleted_count = cur.rowcount
        # Commit gerenciado pelo 'with get_db_connection'
        print(f" -> {deleted_count} eventos antigos deletados (odds associadas também via CASCADE).")
        return deleted_count
    except Exception as e:
        print(f"Erro ao deletar eventos antigos: {e}")
        # conn.rollback() # Rollback gerenciado pelo context manager
        raise  # Re-levanta a exceção para ser tratada no main


def update_pending_event_scores(conn):
    """
    Busca eventos sem placar que já deveriam ter acontecido (data passada) e
    atualiza o status/placar deles fazendo uma nova consulta à API.

    Retorna a quantidade de eventos atualizados.
    """
    now = datetime.now(pytz.timezone(TIMEZONE))
    threshold = now - timedelta(hours=3)  # Eventos concluídos há pelo menos 3 horas

    # Busca eventos sem placar que já deveriam ter terminado
    query_get_pending = """
    SELECT event_id, event_timestamp, league_id 
    FROM events 
    WHERE (final_score IS NULL OR final_score = '') 
    AND event_timestamp < %s 
    -- Removido filtro de sport_id para atualizar todos os eventos pendentes
    ORDER BY event_timestamp DESC;
    """

    updated_count = 0

    try:
        with get_cursor(conn) as cur:
            cur.execute(query_get_pending, (threshold,))
            pending_events = cur.fetchall()

            if not pending_events:
                print(f"Nenhum evento pendente de atualização de placar encontrado.")
                return 0

            print(f"Encontrados {len(pending_events)} eventos para atualizar o placar.")

            # Cria um cliente API para consultar os eventos
            from api.client import BetsAPIClient
            from utils.helpers import parse_score

            api_client = BetsAPIClient()

            for event in pending_events:
                event_id = event["event_id"]
                print(f"Buscando atualização para evento ID: {event_id}")

                try:
                    # Busca o evento diretamente pelo método implementado no client
                    event_data = api_client.get_event_details(event_id)

                    if not event_data or event_data.get("success") != 1:
                        print(f"  → Não foi possível obter dados para o evento ID {event_id}")
                        continue

                    result = event_data.get("results", {})

                    # Extrai o placar utilizando a mesma lógica de outras partes do código
                    ss = result.get("ss", "")
                    score = parse_score(ss)

                    if score:
                        # Atualiza o placar no banco de dados
                        update_query = """
                        UPDATE events 
                        SET final_score = %s, updated_at = NOW() 
                        WHERE event_id = %s;
                        """

                        cur.execute(update_query, (score, event_id))
                        updated_count += 1
                        print(f"  → Evento ID {event_id} atualizado com placar: {score}")
                    else:
                        print(f"  → Evento ID {event_id} ainda sem placar disponível ou formato inválido.")

                except Exception as e:
                    print(f"Erro ao atualizar evento ID {event_id}: {e}")
                    continue

            # Commit após processar todos os eventos
            conn.commit()

        print(f"Atualização completa. {updated_count} eventos tiveram seu placar atualizado.")
        return updated_count

    except Exception as e:
        print(f"Erro ao atualizar placares pendentes: {e}")
        conn.rollback()
        raise
