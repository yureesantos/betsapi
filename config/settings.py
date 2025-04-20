# config/settings.py
import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env na raiz do projeto se existir
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)

# Configurações da API
BETSAPI_TOKEN = os.getenv("BETSAPI_TOKEN")
BASE_URL_V1 = os.getenv("API_BASE_URL", "https://api.b365api.com/v1")
BASE_URL_V2 = "https://api.b365api.com/v2"

# Configurações do Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")

# Configurações Gerais
TARGET_SPORT_ID = int(os.getenv("SPORT_ID", 3))  # Buscar sport_id do ambiente ou usar 3 (esports)
TIMEZONE = "America/Sao_Paulo"
REQUEST_DELAY_SECONDS = 1.1  # Tempo de espera entre requisições API (evitar rate limit)
MAX_RETRIES = 3  # Máximo de tentativas para requisições falhas
RETRY_DELAY_SECONDS = 5  # Tempo de espera antes de tentar novamente

# IDs das ligas de eSoccer
# Lista extraída da análise do arquivo futebol_data_skip_esports_0.json
ESOCCER_LEAGUE_IDS = [
    "38439",  # Esoccer Battle Volta - 6 mins play
    "37298",  # Esoccer H2H GG League - 8 mins play
    "22614",  # Esoccer Battle - 8 mins play
    "23114",  # Esoccer GT Leagues – 12 mins play
    "33440",  # Esoccer Adriatic League - 10 mins play
]

# Nomes das ligas correspondentes aos IDs acima
ESOCCER_LEAGUE_NAMES = [
    "Esoccer Battle Volta - 6 mins play",
    "Esoccer H2H GG League - 8 mins play",
    "Esoccer Battle - 8 mins play",
    "Esoccer GT Leagues – 12 mins play",
    "Esoccer Adriatic League - 10 mins play",
]

# Validações básicas
if not BETSAPI_TOKEN:
    raise ValueError("Erro: A variável de ambiente BETSAPI_TOKEN não está definida.")
if not DATABASE_URL:
    raise ValueError("Erro: A variável de ambiente DATABASE_URL não está definida.")
