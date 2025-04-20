#!/bin/bash
# Script para buscar apenas novos jogos a cada 2 minutos
# Este script é executado pelo cron a cada 2 minutos

# Configuração de caminhos
APP_DIR="/app"
LOG_DIR="/app/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Verifica se o diretório de logs existe, se não, cria
mkdir -p $LOG_DIR

# Função para registrar mensagens de log
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Vai para o diretório do aplicativo
cd $APP_DIR || { log "Erro: Não foi possível mudar para o diretório $APP_DIR"; exit 1; }

# Garantir que o arquivo principal está presente
if [ ! -f "$APP_DIR/main.py" ]; then
    log "Erro: Arquivo main.py não encontrado em $APP_DIR"
    exit 1
fi

# Inicia o log
log "Iniciando busca por novos jogos"

# Execute o comando python com o modo especial para buscar apenas jogos novos
# Este modo não atualiza placares nem faz limpeza, apenas busca jogos novos
/usr/local/bin/python3 main.py --mode fetch-new-games

log "Busca por novos jogos concluída"
exit 0 