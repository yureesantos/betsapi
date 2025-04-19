# main.py
import time
import signal
import sys
import json  # Para salvar odds como JSONB
from datetime import datetime, timedelta, timezone
import pytz
import argparse  # Para argumentos de linha de comando
import concurrent.futures  # Para processamento paralelo
import traceback

from config.settings import TARGET_SPORT_ID, TIMEZONE, REQUEST_DELAY_SECONDS, ESOCCER_LEAGUE_IDS, ESOCCER_LEAGUE_NAMES
from api.client import BetsAPIClient
from db.database import (
    get_db_connection,
    delete_old_events,  # Removido get/update_fetch_state por enquanto
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
    if running:  # Evita múltiplas mensagens se pressionar Ctrl+C várias vezes
        print("\nRecebido sinal de interrupção. Tentando finalizar graciosamente...")
        running = False
    else:
        print("Finalização forçada.")
        sys.exit(1)


# Registra o handler para SIGINT (Ctrl+C) e SIGTERM
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def deve_processar_liga(league_id):
    """Verifica se a liga é de eSoccer com base no ID."""
    # Verifica se o ID da liga está na lista de IDs de eSoccer
    return league_id in ESOCCER_LEAGUE_IDS


def processar_odds(odds_summary_data, event_id):
    """Processa os dados de odds e retorna uma lista de dicts para inserção."""
    odds_para_inserir = []
    if not odds_summary_data or odds_summary_data.get("success") != 1:
        # print(f"    -> Sem dados de odds válidos para Event ID: {event_id}") # Log menos verboso
        return odds_para_inserir, None  # Retorna lista vazia e None timestamp

    results = odds_summary_data.get("results", {})
    # Focar nas odds da Bet365 por enquanto
    bet365_data = results.get("Bet365", {})
    odds_start = bet365_data.get("odds", {}).get("start", {})  # Odds pré-jogo

    if not odds_start:
        # print(f"    -> Sem odds 'start' (pré-jogo) da Bet365 para Event ID: {event_id}") # Log menos verboso
        return odds_para_inserir, None

    # Timestamp das odds (se disponível, senão usaremos o da coleta)
    # A API V2 pode não fornecer timestamp para 'start' odds facilmente, usar None por agora
    # --- Correção: Buscar timestamp dentro de cada mercado ---
    # odds_ts = None # converter_timestamp(odds_start.get('time_str')) se disponível

    # 1. Mercado 1X2 (ID: 1_1)
    if "1_1" in odds_start:
        market_1x2 = odds_start["1_1"]
        add_time_ts = converter_timestamp(market_1x2.get("add_time"))
        odds_data = {
            "home": market_1x2.get("home_od"),
            "draw": market_1x2.get("draw_od"),
            "away": market_1x2.get("away_od"),
            "ss": market_1x2.get("ss"),  # Placar no momento da odd (para live)
            # 'add_time': add_time_ts # Adicionado como timestamp principal
        }
        # Remove chaves com valor None antes de salvar
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean:  # Só adiciona se tiver alguma odd válida
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_1x2",
                    "odds_timestamp": add_time_ts,  # Usar o add_time do mercado se disponível
                    "odds_data": json.dumps(odds_data_clean),  # Salva como JSON string
                }
            )

    # 2. Mercado Handicap Asiático (ID: 1_2)
    if "1_2" in odds_start:
        market_ah = odds_start["1_2"]
        add_time_ts = converter_timestamp(market_ah.get("add_time"))
        handicap_val = market_ah.get("handicap")
        odds_data = {
            "handicap": handicap_val,
            "home": market_ah.get("home_od"),
            "away": market_ah.get("away_od"),
            "ss": market_ah.get("ss"),
            # 'add_time': add_time_ts
        }
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean and "home" in odds_data_clean and "away" in odds_data_clean:
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_asian_handicap",
                    "odds_timestamp": add_time_ts,
                    "odds_data": json.dumps(odds_data_clean),
                }
            )

    # 3. Mercado Over/Under (Gols) (ID: 1_3)
    if "1_3" in odds_start:
        market_ou = odds_start["1_3"]
        add_time_ts = converter_timestamp(market_ou.get("add_time"))
        line_val = market_ou.get("handicap")  # Linha Over/Under
        odds_data = {
            "line": line_val,
            "over": market_ou.get("over_od"),
            "under": market_ou.get("under_od"),
            "ss": market_ou.get("ss"),
            # 'add_time': add_time_ts
        }
        odds_data_clean = {k: v for k, v in odds_data.items() if v is not None}
        if odds_data_clean and "over" in odds_data_clean and "under" in odds_data_clean:
            odds_para_inserir.append(
                {
                    "event_id": event_id,
                    "bookmaker": "Bet365",
                    "odds_market": "prematch_over_under",
                    "odds_timestamp": add_time_ts,
                    "odds_data": json.dumps(odds_data_clean),
                }
            )

    # Extrai o 'last_update' timestamp das odds da Bet365 se disponível
    bet365_last_update_ts = bet365_data.get("last_update")
    last_odds_update_time = converter_timestamp(bet365_last_update_ts)

    return odds_para_inserir, last_odds_update_time


def processar_jogo(conn, api_client, jogo_data):
    """Processa os dados de um único jogo e suas odds."""
    global running
    if not running:
        return False  # Sai se a flag de parada foi acionada

    event_id = jogo_data.get("id")
    if not event_id:
        print("Aviso: Jogo sem ID encontrado, pulando.")
        return True  # Continua processando outros jogos

    # Verificar se o jogo é de eSoccer
    league_data = jogo_data.get("league", {})
    league_id = league_data.get("id")

    if not league_id or not deve_processar_liga(league_id):
        # Pulamos silenciosamente jogos que não são de eSoccer
        return True  # Continua processando outros jogos

    print(f"  -> Processando Event ID: {event_id} (eSoccer)")

    # Extrair dados básicos
    home_data = jogo_data.get("home", {})
    away_data = jogo_data.get("away", {})

    home_team_name, home_player = extrair_time_jogador(home_data.get("name"))
    away_team_name, away_player = extrair_time_jogador(away_data.get("name"))
    event_time = converter_timestamp(jogo_data.get("time"))
    score = parse_score(jogo_data.get("ss"))

    # Monta dict do evento para o DB
    event_dict = {
        "event_id": event_id,  # Será convertido para int em upsert_event
        "sport_id": jogo_data.get("sport_id", TARGET_SPORT_ID),
        "league_id": league_id,
        "league_name": league_data.get("name"),
        "event_timestamp": event_time,
        "home_team_id": home_data.get("id"),
        "home_team_name": home_team_name,
        "home_player_name": home_player,
        "away_team_id": away_data.get("id"),
        "away_team_name": away_team_name,
        "away_player_name": away_player,
        "final_score": score,
        "has_odds": None,  # Não definir aqui, deixar o DB manter o valor ou atualizar após buscar odds
        "last_odds_update": None,
    }

    try:
        # 1. Inserir/Atualizar evento no DB
        upsert_event(conn, event_dict)
        # print(f"     Evento {event_id} salvo/atualizado.") # Log menos verboso

        # 2. Buscar e processar Odds
        odds_summary = api_client.get_event_odds_summary(event_id)
        if odds_summary:
            odds_list, last_update_time = processar_odds(odds_summary, event_id)

            if odds_list:
                inserted_count = insert_odds(conn, odds_list)
                # print(f"     {inserted_count} odds inseridas.") # Log menos verboso
                # Atualiza o status do evento para indicar que tem odds
                if inserted_count > 0:
                    # Usa now() se last_update_time não veio da API
                    update_time = last_update_time if last_update_time else datetime.now(pytz.utc)
                    update_event_odds_status(conn, event_id, True, update_time)
            # else:
            # print(f"     Nenhuma odd válida processada.") # Log menos verboso
        # else:
        # print(f"     Falha ao buscar odds.") # Log menos verboso

        conn.commit()  # Commit após processar este evento com sucesso
        return True  # Indica sucesso

    except Exception as e:
        print(f"Erro ao processar evento {event_id} ou suas odds: {e}")
        conn.rollback()  # Desfaz alterações deste evento
        # Considerar parar ou continuar? Para um job diário, talvez seja melhor
        # registrar o erro e continuar com os outros jogos/dias.
        # Se for um erro crítico (ex: DB inacessível), a exceção vai subir.
        return False  # Indica falha no processamento deste jogo


def fetch_and_process_day(conn, api_client, target_date):
    """Busca e processa todos os eventos encerrados para um dia específico."""
    global running
    day_str = target_date.strftime("%Y%m%d")
    print(f"\nIniciando busca para o dia: {day_str}")

    current_page = 1
    total_jogos_dia = 0
    total_esoccer_dia = 0  # Contador para jogos de eSoccer
    falhas_dia = 0

    while running:
        event_data = api_client.get_ended_events(page=current_page, sport_id=TARGET_SPORT_ID, day_str=day_str)

        if not running:
            break  # Verifica após a chamada de API também

        if not event_data:
            print(f"Erro crítico ao buscar dados para {day_str}, página {current_page}. Abortando dia.")
            # Poderia implementar retry aqui antes de desistir
            break

        jogos = event_data.get("results", [])
        pager = event_data.get("pager")

        if not jogos:
            if current_page == 1:
                print(f"Nenhum jogo encontrado para o dia {day_str}.")
            else:
                print(f"Fim dos jogos para o dia {day_str} na página {current_page-1}.")
            break  # Sai do loop de páginas para este dia

        # Contagem de jogos de eSoccer na página atual
        esoccer_na_pagina = sum(1 for jogo in jogos if jogo.get("league", {}).get("id") in ESOCCER_LEAGUE_IDS)

        print(
            f"Processando {len(jogos)} eventos da página {current_page} para {day_str} (sendo {esoccer_na_pagina} de eSoccer)..."
        )

        processados = 0
        falhas = 0

        for jogo in jogos:
            if not running:
                break  # Verifica antes de cada jogo

            result = processar_jogo(conn, api_client, jogo)
            # A função processar_jogo já filtra e processa apenas jogos de eSoccer
            # Se não for eSoccer, ela retorna True sem fazer nada

            if jogo.get("league", {}).get("id") in ESOCCER_LEAGUE_IDS:
                if result:
                    processados += 1
                else:
                    falhas += 1

        total_jogos_dia += len(jogos)
        total_esoccer_dia += esoccer_na_pagina
        falhas_dia += falhas

        # Verificar se há mais páginas
        if pager and "page" in pager and "total_pages" in pager:
            current_page = int(pager["page"]) + 1
            if current_page > int(pager["total_pages"]):
                print(f"Fim das páginas para o dia {day_str}.")
                break
        else:
            print(f"Aviso: Informações de paginação ausentes ou inválidas. Abortando após primeira página.")
            break

        # Pausa para evitar problemas de rate limit
        time.sleep(REQUEST_DELAY_SECONDS)

    # Resumo do dia
    print(f"\nResumo para {day_str}:")
    print(f"  Total de jogos buscados: {total_jogos_dia}")
    print(
        f"  Jogos de eSoccer: {total_esoccer_dia} ({(total_esoccer_dia/total_jogos_dia*100) if total_jogos_dia > 0 else 0:.1f}%)"
    )
    print(f"  Jogos de eSoccer processados com sucesso: {total_esoccer_dia - falhas_dia}")
    print(f"  Falhas: {falhas_dia}")

    return total_esoccer_dia - falhas_dia  # Retorna apenas jogos de eSoccer processados com sucesso


def run_daily_update(conn, api_client):
    """Executa a limpeza e busca dos últimos 2 dias."""
    global running
    print("\n===== Iniciando Atualização Diária =====")

    # 1. Deletar dados antigos (sempre executa)
    try:
        delete_old_events(conn, days_to_keep=60)
        conn.commit()  # Commit após delete bem-sucedido
    except Exception as e_del:
        print(f"Erro crítico durante a limpeza de eventos antigos: {e_del}")
        # Parar a execução se a limpeza falhar pode ser mais seguro
        running = False
        return  # Sai da função

    # 2. Buscar dados de ontem e hoje
    local_tz = pytz.timezone(TIMEZONE)
    hoje = datetime.now(local_tz)
    ontem = hoje - timedelta(days=1)

    # Processa ontem primeiro
    if running:
        fetch_and_process_day(conn, api_client, ontem)

    # Processa hoje
    if running:
        fetch_and_process_day(conn, api_client, hoje)

    print("\n===== Atualização Diária Finalizada =====")


def run_backfill_parallel(conn, api_client, days_back=60, workers=4):
    """
    Executa um backfill paralelo para os últimos N dias.
    Utiliza um ThreadPoolExecutor para processar múltiplos dias simultaneamente.
    """
    global running

    # Calcula as datas de início e fim do período de backfill
    end_date = datetime.now(pytz.timezone(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days_back)

    print(f"\n===== Iniciando Backfill para os últimos {days_back} dias =====")
    print(f"Período: {start_date.strftime('%Y-%m-%d')} até {end_date.strftime('%Y-%m-%d')}")
    print(f"Usando {workers} workers para processamento paralelo")
    print(f"Buscando apenas ligas de eSoccer: {ESOCCER_LEAGUE_IDS}")

    # Cria uma lista das datas a processar (mais recentes primeiro)
    days_to_process = []
    current_date = end_date
    while current_date >= start_date and running:
        days_to_process.append(current_date)
        current_date -= timedelta(days=1)

    # Cria uma lista de tarefas combinando dias e ligas
    tasks = []
    for day in days_to_process:
        for league_id in ESOCCER_LEAGUE_IDS:
            tasks.append({"day": day, "league_id": league_id})

    print(f"Total de tarefas a processar: {len(tasks)} (dias × ligas)")

    # Criar uma conexão separada para cada worker
    def get_connection():
        return get_db_connection()  # Função que cria uma nova conexão com o banco

    # Cria um executor de threads com o número solicitado de workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # Função que será executada para cada tarefa
        def process_task(task):
            if not running:
                return None

            day = task["day"]
            league_id = task["league_id"]

            # Cria uma conexão separada para esta thread
            thread_conn = get_connection()
            try:
                # Cria um novo cliente API para esta thread (opcional, mas pode ajudar a evitar problemas)
                thread_api = BetsAPIClient()

                # Invoca a função que busca e processa os dados para um dia e liga específicos
                return fetch_and_process_league_day(thread_conn, thread_api, day, league_id)
            except Exception as e:
                print(f"Erro ao processar dia {day.strftime('%Y%m%d')} e liga {league_id}: {e}")
                print(traceback.format_exc())
                thread_conn.rollback()
                return None
            finally:
                thread_conn.close()

        # Mapeia as tarefas para execução paralela
        results = list(executor.map(process_task, tasks))

    # Calcula estatísticas do processamento
    total_processed = sum([r for r in results if r is not None])
    print("\n===== Backfill Concluído =====")
    print(f"Total de jogos processados: {total_processed}")
    return total_processed


def fetch_and_process_league_day(conn, api_client, target_date, league_id):
    """Busca e processa todos os eventos de uma liga específica para um dia específico."""
    global running
    day_str = target_date.strftime("%Y%m%d")
    league_name = next(
        (name for id, name in zip(ESOCCER_LEAGUE_IDS, ESOCCER_LEAGUE_NAMES) if id == league_id), league_id
    )

    print(f"\nIniciando busca para o dia {day_str}, liga {league_name} (ID: {league_id})")

    current_page = 1
    total_jogos = 0
    falhas = 0

    while running:
        event_data = api_client.get_ended_events(
            page=current_page,
            sport_id=TARGET_SPORT_ID,
            day_str=day_str,
            league_id=league_id,  # Filtra diretamente pela liga na API
        )

        if not running:
            break

        if not event_data:
            print(f"Erro crítico ao buscar dados para {day_str}, liga {league_id}, página {current_page}.")
            break

        jogos = event_data.get("results", [])
        pager = event_data.get("pager")

        if not jogos:
            if current_page == 1:
                print(f"Nenhum jogo encontrado para o dia {day_str}, liga {league_id}.")
            else:
                print(f"Fim dos jogos para o dia {day_str}, liga {league_id} na página {current_page-1}.")
            break

        print(
            f"Processando {len(jogos)} eventos de eSoccer da página {current_page} para {day_str}, liga {league_id}..."
        )

        processados = 0
        falhas_pagina = 0

        for jogo in jogos:
            if not running:
                break

            result = processar_jogo(conn, api_client, jogo)
            if result:
                processados += 1
            else:
                falhas_pagina += 1

        total_jogos += processados
        falhas += falhas_pagina

        # Verificar se há mais páginas
        if pager and "page" in pager and "total_pages" in pager:
            current_page = int(pager["page"]) + 1
            if current_page > int(pager["total_pages"]):
                print(f"Fim das páginas para o dia {day_str}, liga {league_id}.")
                break
        else:
            print(
                f"Aviso: Informações de paginação ausentes. Abortando após primeira página para {day_str}, liga {league_id}."
            )
            break

        # Pausa para evitar problemas de rate limit
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Concluído dia {day_str}, liga {league_id}: {total_jogos} jogos processados, {falhas} falhas.")
    return total_jogos


def main():
    parser = argparse.ArgumentParser(description="Coletor de dados da BetsAPI com janela de 60 dias.")
    parser.add_argument(
        "--mode",
        choices=["daily", "backfill"],
        default="daily",
        help="Modo de execução: 'daily' (padrão) para atualização diária, 'backfill' para busca histórica de 60 dias.",
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Número de workers para execução paralela (somente no modo backfill)."
    )
    parser.add_argument(
        "--days", type=int, default=60, help="Número de dias para buscar no backfill (padrão: 60 dias)."
    )
    args = parser.parse_args()

    print(f"Executando em modo: {args.mode}")
    if args.mode == "backfill":
        print(f"Configuração: {args.days} dias com {args.workers} workers em paralelo.")

    api_client = BetsAPIClient()

    try:
        # Usar a conexão gerenciada para toda a operação (daily ou backfill)
        with get_db_connection() as conn:
            if args.mode == "daily":
                run_daily_update(conn, api_client)
            elif args.mode == "backfill":
                # Use o modo paralelo com o número de workers especificado
                run_backfill_parallel(conn, api_client, days_back=args.days, workers=args.workers)

    except Exception as e:
        print(f"Erro inesperado não tratado na execução principal ({args.mode}): {e}")
        traceback.print_exc()
        sys.exit(1)  # Sai com erro
    finally:
        status = "concluído" if running else "interrompido"
        print(f"Coletor ({args.mode}) {status}.")


if __name__ == "__main__":
    main()
