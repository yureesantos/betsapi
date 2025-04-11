# config/settings.py
import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env na raiz do projeto
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=dotenv_path)

# Configurações da API
BETSAPI_TOKEN = os.getenv("BETSAPI_TOKEN")
BASE_URL_V1 = "https://api.b365api.com/v1"
BASE_URL_V2 = "https://api.b365api.com/v2"

# Configurações do Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")

# Configurações Gerais
TARGET_SPORT_ID = 1  # Futebol
TIMEZONE = "America/Sao_Paulo"
REQUEST_DELAY_SECONDS = 1.1  # Tempo de espera entre requisições API (evitar rate limit)
MAX_RETRIES = 3  # Máximo de tentativas para requisições falhas
RETRY_DELAY_SECONDS = 5  # Tempo de espera antes de tentar novamente

# Validações básicas
if not BETSAPI_TOKEN:
    raise ValueError("Erro: A variável de ambiente BETSAPI_TOKEN não está definida.")
if not DATABASE_URL:
    raise ValueError("Erro: A variável de ambiente DATABASE_URL não está definida.")
