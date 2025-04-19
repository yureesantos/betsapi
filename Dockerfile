# Dockerfile
# Use uma imagem base oficial do Python
FROM python:3.10-slim-bookworm

# Define variáveis de ambiente para Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Variáveis de ambiente para otimização de performance
ENV PSYCOPG_CLIENT_MIN_MESSAGES=WARNING
ENV PSYCOPG_POOL_MIN_SIZE=4
ENV PSYCOPG_POOL_MAX_SIZE=20
ENV PYTHONDEVMODE=0

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Instala dependências de sistema necessárias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Cria um ambiente virtual (opcional, mas boa prática)
# RUN python -m venv /opt/venv
# ENV PATH="/opt/venv/bin:$PATH"

# Copia apenas o arquivo de dependências primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação para o diretório de trabalho
COPY . .

# O comando que será executado quando o contêiner iniciar para a tarefa agendada
# O agendador do Fly.io executará este comando.
CMD ["python", "main.py", "--mode", "daily"]

# Comando para backfill (será sobrescrito ao iniciar com --app backfill)
# CMD ["python", "main.py", "--mode", "backfill", "--workers", "4"]