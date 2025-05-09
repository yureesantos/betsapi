# Dockerfile
# Use uma imagem base oficial do Python
FROM python:3.10-slim

# Instala apenas as dependências essenciais
RUN apt-get update && apt-get install -y \
    cron \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Configura diretório de trabalho
WORKDIR /app

# Copia os requisitos primeiro para aproveitar o cache do Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do projeto
COPY . .

# Configura diretórios necessários
RUN mkdir -p /app/logs

# Torna os scripts executáveis
RUN chmod +x /app/scripts/*.sh

# Configura crontab diretamente no arquivo do sistema
RUN echo "*/2 * * * * /app/scripts/fetch_new_games.sh > /app/logs/fetch_new_games.log 2>&1" > /etc/cron.d/betsapi-cron && \
    echo "*/15 * * * * /app/scripts/update_schedule.sh > /app/logs/cron_execution.log 2>&1" >> /etc/cron.d/betsapi-cron && \
    echo "0 2 * * 0 find /app/logs -name \"*.log\" -type f -mtime +7 -delete" >> /etc/cron.d/betsapi-cron && \
    echo "*/5 * * * * date >> /app/logs/cron_heartbeat.log" >> /etc/cron.d/betsapi-cron && \
    chmod 0644 /etc/cron.d/betsapi-cron && \
    crontab /etc/cron.d/betsapi-cron

# Executa uma verificação inicial para garantir que tudo funciona
RUN echo "Verificando ambiente..." && \
    ls -la /app/scripts && \
    crontab -l

# Comando para iniciar apenas o cron em foreground
CMD ["cron", "-f"]