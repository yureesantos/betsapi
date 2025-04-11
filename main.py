# main.py
import time
import signal
import sys
import json  # Para salvar odds como JSONB
from datetime import datetime, timedelta, timezone
import pytz

from config.settings import TARGET_SPORT_ID, TIMEZONE, REQUEST_DELAY_SECONDS
from api.client import BetsAPIClient
from db.database import (
    get_db_connection,
    get_fetch_state,
    update_fetch_state,
    upsert_event,
    insert_odds,
    update_event_odds_status,
)
from utils.helpers import extrair_time_jogador, inverter_handicap, converter_timestamp, parse_score

# Variável global para controlar o loop principal e permitir interrupção graciosa
running = True


def signal_handler(sig, frame):
    """Captura sinais (como Ctrl+C) para parar o loop principal."""
    global running
    print("\nRecebido sinal de interrupção. Finalizando...")
    running = False


# Registra o handler para SIGINT (Ctrl+C) e SIGTERM
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def processar_odds(odds_summary_data, event_id):
    """Processa os dados de odds e retorna uma lista de dicts para inserção."""
    odds_para_inserir = []
    if not odds_summary_data or odds_summary_data.get("success") != 1:
        print(f"    -> Sem dados de odds válidos para Event ID: {event_id}")
        return odds_para_inserir, None  # Retorna lista vazia e None timestamp

    results = odds_summary_data.get("results", {})
    # Focar nas odds da Bet365 por enquanto
    bet365_data = results.get("Bet365", {})
    odds_start = bet365_data.get("odds", {}).get("start", {})  # Odds pré-jogo

    if not odds_start:
        print(f"    -> Sem odds 'start' (pré-jogo) da Bet365 para Event ID: {event_id}")
        return odds_para_inserir, None

    # Timestamp das odds (se disponível, senão usaremos o da coleta)
    # A API V2 pode não fornecer timestamp para 'start' odds facilmente, usar None por agora
    odds_ts = None  # converter_timestamp(odds_start.get('time_str')) se disponível

    # 1. Mercado 1X2 (ID: 1_1)
    if "1_1" in odds_start:
        market_1x2 = odds_start["1_1"]
        odds_data = {
            "home": market_1x2.get("home_od"),
            "draw": market_1x2.get("draw_od"),
            "away": market_1x2.get("away_od"),
            "ss": market_1x2.get("ss"),  # Placar no momento da odd (para live)
            "add_time": market_1x2.get("add_time"),  # Timestamp da odd
        }
        # Remove chaves com valor None antes de salvar
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean:  # Só adiciona se tiver alguma odd válida
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_1x2",
                    "odds_timestamp": converter_timestamp(odds_data_clean.get("add_time")),
                    "odds_data": json.dumps(odds_data_clean),  # Salva como JSON string
                }
            )

    # 2. Mercado Handicap Asiático (ID: 1_2)
    if "1_2" in odds_start:
        market_ah = odds_start["1_2"]
        handicap_val = market_ah.get("handicap")
        odds_data = {
            "handicap": handicap_val,
            "home": market_ah.get("home_od"),
            "away": market_ah.get("away_od"),
            "ss": market_ah.get("ss"),
            "add_time": market_ah.get("add_time"),
        }
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean and "home" in odds_data_clean and "away" in odds_data_clean:
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_asian_handicap",
                    "odds_timestamp": converter_timestamp(odds_data_clean.get("add_time")),
                    "odds_data": json.dumps(odds_data_clean),
                }
            )

    # 3. Mercado Over/Under (Gols) (ID: 1_3)
    if "1_3" in odds_start:
        market_ou = odds_start["1_3"]
        line_val = market_ou.get("handicap")  # Linha Over/Under
        odds_data = {
            "line": line_val,
            "over": market_ou.get("over_od"),
            "under": market_ou.get("under_od"),
            "ss": market_ou.get("ss"),
            "add_time": market_ou.get("add_time"),
        }
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean and "over" in odds_data_clean and "under" in odds_data_clean:
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_over_under",
                    "odds_timestamp": converter_timestamp(odds_data_clean.get("add_time")),
                    "odds_data": json.dumps(odds_data_clean),
                }
            )

    # Extrai o 'last_update' timestamp das odds da Bet365 se disponível
    bet365_last_update_ts = bet365_data.get("last_update")
    last_odds_update_time = converter_timestamp(bet365_last_update_ts)

    return odds_para_inserir, last_odds_update_time


def main():
    global running
    print("Iniciando coletor de dados BetsAPI...")
    api_client = BetsAPIClient()
    fetch_type = "ended_events"  # Poderia ser uma config ou argumento
    max_pages_per_run = 100  # Limite de páginas por execução para evitar rodar indefinidamente

    try:
        with get_db_connection() as conn:
            # 1. Obter estado da última execução
            initial_state = get_fetch_state(conn, fetch_type)
            if not initial_state:
                print("Erro crítico: Não foi possível obter ou criar o estado inicial da coleta.")
                sys.exit(1)  # Sai se não conseguir o estado

            current_page = initial_state.get("last_processed_page", 0) + 1
            last_status = initial_state.get("status", "idle")
            print(f"Estado inicial: Página={current_page-1}, Status={last_status}")

            # Marca como 'running'
            update_fetch_state(conn, fetch_type, status="running")
            conn.commit()  # Garante que o status 'running' seja salvo

            pages_processed_this_run = 0

            while running and pages_processed_this_run < max_pages_per_run:
                # 2. Buscar página de eventos encerrados
                event_data = api_client.get_ended_events(page=current_page, sport_id=TARGET_SPORT_ID)

                if not event_data or not event_data.get("results"):
                    print(
                        f"Nenhum evento encontrado na página {current_page} ou erro na API. Verificando próxima página ou finalizando."
                    )
                    # Se não houver mais páginas ('pager' indica isso), ou erro, parar
                    if (
                        not event_data
                        or not event_data.get("pager")
                        or int(event_data["pager"].get("total", 0))
                        <= current_page * int(event_data["pager"].get("per_page", 50))
                    ):
                        print("Fim dos eventos encontrados ou erro irrecuperável. Finalizando busca.")
                        update_fetch_state(conn, fetch_type, page=current_page - 1, status="completed")
                        running = False
                    else:
                        # Pode ter sido um erro temporário, tenta a próxima página na próxima execução
                        print(f"Erro ao buscar página {current_page}, pulando para a próxima na futura execução.")
                        update_fetch_state(conn, fetch_type, page=current_page - 1, status="error_skipped_page")
                        running = False  # Parar a execução atual
                    break  # Sai do loop while

                jogos = event_data.get("results", [])
                print(f"Processando {len(jogos)} eventos da página {current_page}...")

                # 3. Processar cada jogo
                for jogo in jogos:
                    if not running:
                        break  # Verifica se recebeu sinal de parada

                    event_id = jogo.get("id")
                    if not event_id:
                        print("Aviso: Jogo sem ID encontrado, pulando.")
                        continue

                    print(f"\nProcessando Event ID: {event_id}")

                    # Extrair dados básicos
                    league_data = jogo.get("league", {})
                    home_data = jogo.get("home", {})
                    away_data = jogo.get("away", {})

                    home_team_name, home_player = extrair_time_jogador(home_data.get("name"))
                    away_team_name, away_player = extrair_time_jogador(away_data.get("name"))
                    event_time = converter_timestamp(jogo.get("time"))
                    score = parse_score(jogo.get("ss"))

                    # Monta dict do evento para o DB
                    event_dict = {
                        "event_id": int(event_id),
                        "sport_id": int(jogo.get("sport_id", TARGET_SPORT_ID)),
                        "league_id": int(league_data["id"]) if league_data.get("id") else None,
                        "league_name": league_data.get("name"),
                        "event_timestamp": event_time,
                        "home_team_id": int(home_data["id"]) if home_data.get("id") else None,
                        "home_team_name": home_team_name,
                        "home_player_name": home_player,
                        "away_team_id": int(away_data["id"]) if away_data.get("id") else None,
                        "away_team_name": away_team_name,
                        "away_player_name": away_player,
                        "final_score": score,
                        "has_odds": False,  # Será atualizado após buscar odds
                        "last_odds_update": None,
                    }

                    # 4. Inserir/Atualizar evento no DB
                    try:
                        upsert_event(conn, event_dict)
                        print(f" -> Evento {event_id} salvo/atualizado no DB.")

                        # 5. Buscar e processar Odds
                        odds_summary = api_client.get_event_odds_summary(event_id)
                        if odds_summary:
                            odds_list, last_update_time = processar_odds(odds_summary, event_id)

                            if odds_list:
                                inserted_count = insert_odds(conn, odds_list)
                                print(f"    -> {inserted_count} registros de odds inseridos.")
                                # Atualiza o status do evento para indicar que tem odds
                                if inserted_count > 0:
                                    update_event_odds_status(
                                        conn, event_id, True, last_update_time or datetime.now(pytz.utc)
                                    )  # Usa now se não tiver timestamp da API
                            else:
                                print(f"    -> Nenhuma odd válida processada para evento {event_id}.")
                                # Poderia marcar como 'sem odds encontradas' no evento aqui?

                        else:
                            print(f"    -> Falha ao buscar odds para evento {event_id}.")
                            # Poderia tentar novamente depois ou marcar o evento

                        conn.commit()  # Commit após processar cada evento com sucesso

                    except Exception as e:
                        print(f"Erro ao processar evento {event_id} ou suas odds: {e}")
                        conn.rollback()  # Desfaz alterações do evento atual em caso de erro
                        # Considerar parar ou continuar dependendo do erro
                        # Por segurança, vamos parar nesta execução se um evento falhar
                        update_fetch_state(conn, fetch_type, page=current_page - 1, status="error_processing_event")
                        conn.commit()
                        running = False
                        break  # Sai do loop for jogo

                    # Pequena pausa adicional para garantir
                    time.sleep(0.1)

                # Fim do loop for jogo
                if not running:
                    # Se parou durante o processamento dos jogos, salva a página anterior como última processada
                    print(f"Interrompido durante a página {current_page}. Salvando estado.")
                    update_fetch_state(conn, fetch_type, page=current_page - 1, status="paused")
                    conn.commit()
                    break  # Sai do loop while

                # 6. Atualizar estado após processar a página inteira com sucesso
                print(f"Página {current_page} processada com sucesso.")
                update_fetch_state(conn, fetch_type, page=current_page, status="running")
                conn.commit()  # Salva o progresso da página

                current_page += 1
                pages_processed_this_run += 1

                if pages_processed_this_run >= max_pages_per_run:
                    print(f"Atingido limite de {max_pages_per_run} páginas por execução.")
                    update_fetch_state(conn, fetch_type, status="paused_max_pages")
                    conn.commit()
                    running = False  # Para o loop

            # Fim do loop while
            if running:  # Se saiu do loop sem ser interrompido ou erro
                print("Busca concluída ou todas as páginas disponíveis processadas.")
                final_status = "completed" if pages_processed_this_run < max_pages_per_run else "paused_max_pages"
                update_fetch_state(conn, fetch_type, page=current_page - 1, status=final_status)
                conn.commit()

    except psycopg2.OperationalError:
        # Erro já tratado e logado em get_db_connection
        print("Erro crítico: Falha na conexão com o banco de dados.")
    except Exception as e:
        print(f"Erro inesperado no loop principal: {e}")
        import traceback

        traceback.print_exc()
        # Tenta salvar o estado como erro, se possível
        try:
            with get_db_connection() as conn_err:
                update_fetch_state(conn_err, fetch_type, status="error_unexpected")
                conn_err.commit()
        except Exception as db_err:
            print(f"Não foi possível nem mesmo salvar o estado de erro no DB: {db_err}")
    finally:
        print("Coletor finalizado.")


if __name__ == "__main__":
    main()
