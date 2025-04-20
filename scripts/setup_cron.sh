#!/bin/bash
# Script para configurar o cron no ambiente Fly.io

# Configuração de caminhos
SCRIPTS_DIR="/app/scripts"
LOG_DIR="/app/logs"

# Verifica se o diretório de scripts existe, senão cria
mkdir -p $SCRIPTS_DIR
mkdir -p $LOG_DIR

# Torna o script de atualização executável
chmod +x $SCRIPTS_DIR/update_schedule.sh

# Verifica se o cron está instalado
if ! command -v crontab &> /dev/null; then
    echo "Cron não está instalado. Instalando..."
    apt-get update && apt-get install -y cron
fi

# Inicia o serviço cron se não estiver rodando
if ! pgrep cron > /dev/null; then
    echo "Iniciando serviço cron..."
    service cron start || /etc/init.d/cron start
fi

# Instala a configuração do crontab
echo "Instalando configuração do crontab..."
crontab $SCRIPTS_DIR/crontab-config.txt

# Verifica se a instalação foi bem-sucedida
if [ $? -eq 0 ]; then
    echo "Crontab instalado com sucesso!"
    crontab -l
else
    echo "Erro ao instalar crontab!"
    exit 1
fi

echo "Configuração concluída. O script de atualização será executado a cada 15 minutos."
exit 0 