# db/database.py
import psycopg2
import time
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from config.settings import DATABASE_URL, RETRY_DELAY_SECONDS


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
                return cur.fetchone()
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
        final_score = COALESCE(EXCLUDED.final_score, events.final_score), -- Mantém placar se já existir
        has_odds = COALESCE(EXCLUDED.has_odds, events.has_odds), -- Atualiza se vier no novo dado
        last_odds_update = COALESCE(EXCLUDED.last_odds_update, events.last_odds_update),
        updated_at = NOW() -- Atualizado pelo trigger ou aqui explicitamente
    RETURNING event_id;
    """
    try:
        with get_cursor(conn) as cur:
            cur.execute(query, event)
            result = cur.fetchone()
            return result["event_id"] if result else None
    except Exception as e:
        print(f"Erro ao inserir/atualizar evento {event.get('event_id', 'N/A')}: {e}")
        # print(f"Dados do evento: {event}") # Descomentar para depuração
        # conn.rollback() # Rollback gerenciado pelo context manager
        raise


def insert_odds(conn, odds_list):
    """Insere uma lista de registros de odds na tabela 'odds'."""
    if not odds_list:
        return 0

    query = """
    INSERT INTO odds (
        event_id, bookmaker, odds_market, odds_timestamp, odds_data, collection_timestamp
    ) VALUES (
        %(event_id)s, %(bookmaker)s, %(odds_market)s, %(odds_timestamp)s, %(odds_data)s, NOW()
    )
    ON CONFLICT DO NOTHING; -- Evita duplicatas exatas se rodar novamente, mas pode ser necessário refinar
    """
    inserted_count = 0
    try:
        with get_cursor(conn) as cur:
            # psycopg2 executemany é mais eficiente para múltiplas inserções
            # Precisamos converter a lista de dicts para lista de tuplas na ordem correta
            values = [
                (
                    o["event_id"],
                    o.get("bookmaker", "Bet365"),
                    o["odds_market"],
                    o.get("odds_timestamp"),
                    o["odds_data"],
                )
                for o in odds_list
            ]
            # Reconstruir a query para executemany
            query_many = """
            INSERT INTO odds (event_id, bookmaker, odds_market, odds_timestamp, odds_data, collection_timestamp)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING;
            """
            cur.executemany(query_many, values)
            inserted_count = cur.rowcount  # Número de linhas afetadas
            # print(f"Inserido {inserted_count} registros de odds para evento {odds_list[0]['event_id']}.")
    except Exception as e:
        print(f"Erro ao inserir odds para evento {odds_list[0].get('event_id', 'N/A')}: {e}")
        # print(f"Dados das odds: {odds_list}") # Descomentar para depuração
        # conn.rollback() # Rollback gerenciado pelo context manager
        raise
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
            cur.execute(query, (has_odds, last_update_time, event_id))
            # print(f"Status das odds atualizado para evento {event_id}: has_odds={has_odds}")
    except Exception as e:
        print(f"Erro ao atualizar status das odds para evento {event_id}: {e}")
        raise
