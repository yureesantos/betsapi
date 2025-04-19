# api/client.py
import requests
import time
import json
from config.settings import (
    BETSAPI_TOKEN,
    BASE_URL_V1,
    BASE_URL_V2,
    REQUEST_DELAY_SECONDS,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
)


class BetsAPIClient:
    def __init__(self):
        self.token = BETSAPI_TOKEN
        self.base_url_v1 = BASE_URL_V1
        self.base_url_v2 = BASE_URL_V2
        self.session = requests.Session()  # Usar sessão para melhor performance e reuso de conexão

    def _make_request(self, url, params=None):
        """Método interno para realizar requisições com tratamento de erros e retries."""
        if params is None:
            params = {}
        params["token"] = self.token  # Adiciona token a todos os requests

        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                # Adiciona um delay antes de cada requisição
                time.sleep(REQUEST_DELAY_SECONDS)

                response = self.session.get(url, params=params, timeout=30)  # Timeout de 30s

                # Verifica erro 429 (Too Many Requests)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", RETRY_DELAY_SECONDS * (attempt + 2)))
                    print(f"Aviso: Rate limit atingido (429). Esperando {retry_after} segundos...")
                    time.sleep(retry_after)
                    last_exception = requests.exceptions.RequestException("Rate limit atingido (429)")
                    continue  # Tenta novamente

                response.raise_for_status()  # Levanta exceção para erros HTTP (4xx, 5xx)

                data = response.json()

                # Verifica a flag 'success' na resposta da API
                if data.get("success") != 1:
                    error_message = data.get("error", "Erro desconhecido da API (success != 1)")
                    print(f"Erro na resposta da API para {url} com params {params}: {error_message}")
                    # Tratar erros específicos da API aqui se necessário
                    if "event not found" in error_message.lower():
                        return None  # Evento não encontrado é um caso esperado, não um erro fatal
                    if "no results" in error_message.lower():  # Tratar "no results for ..." como sucesso vazio
                        print(f"Info: Nenhum resultado encontrado para {url} com params {params} ({error_message})")
                        return {"success": 1, "results": [], "pager": None}  # Retorna estrutura vazia
                    last_exception = ValueError(f"API Error: {error_message}")
                    # Espera antes de tentar novamente em caso de erro da API
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue

                return data

            except requests.exceptions.Timeout:
                print(f"Erro: Timeout na requisição para {url}. Tentativa {attempt + 1}/{MAX_RETRIES}")
                last_exception = requests.exceptions.Timeout("Request timed out")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            except requests.exceptions.RequestException as e:
                print(f"Erro na requisição para {url}: {e}. Tentativa {attempt + 1}/{MAX_RETRIES}")
                last_exception = e
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            except json.JSONDecodeError as e:
                print(f"Erro ao decodificar JSON da resposta de {url}: {e}. Conteúdo: {response.text[:200]}...")
                last_exception = e
                # Não tentar novamente se o JSON for inválido
                break
            except Exception as e:
                print(f"Erro inesperado durante a requisição para {url}: {e}")
                last_exception = e
                # Não tentar novamente para erros muito genéricos
                break

        # Se todas as tentativas falharam
        print(f"Erro: Falha ao realizar requisição para {url} após {MAX_RETRIES} tentativas.")
        if last_exception:
            # Poderia logar a exceção aqui
            pass
        return None  # Retorna None em caso de falha completa

    def get_ended_events(self, page=1, sport_id=1, skip_esports=0, day_str=None):
        """
        Busca eventos encerrados (futebol por padrão).
        Permite filtrar por dia específico (formato YYYYMMDD).
        """
        url = f"{self.base_url_v1}/events/ended"
        params = {"sport_id": sport_id, "skip_esports": skip_esports, "page": page}
        # Adiciona o parâmetro 'day' se fornecido
        if day_str:
            params["day"] = day_str
            print(f"Buscando eventos encerrados - Dia: {day_str}, Página: {page}")
        else:
            print(f"Buscando eventos encerrados recentes - Página: {page}")

        return self._make_request(url, params)

    def get_event_odds_summary(self, event_id):
        """Busca o resumo das odds para um evento específico."""
        if not event_id:
            return None
        url = f"{self.base_url_v2}/event/odds/summary"
        params = {"event_id": event_id}
        # print(f"Buscando odds summary para Event ID: {event_id}")
        return self._make_request(url, params)

    # --- Métodos potenciais para busca histórica (se a API permitir) ---
    # def get_historical_events(self, date_from, date_to, sport_id=1, page=1):
    #     """Busca eventos históricos por data (exemplo, verificar endpoint real)."""
    #     # Verificar documentação da API para o endpoint correto e parâmetros
    #     # url = f"{self.base_url_vX}/events/history" # Exemplo
    #     # params = {'sport_id': sport_id, 'date_from': date_from, 'date_to': date_to, 'page': page}
    #     # return self._make_request(url, params)
    #     print("Funcionalidade de busca histórica por data ainda não implementada.")
    #     return None
