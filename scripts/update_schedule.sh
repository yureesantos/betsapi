#!/bin/bash
# Script para atualização periódica de placares e limpeza
# Este script é executado pelo cron a cada 15 minutos

# Configuração de caminhos
APP_DIR="/app"
LOG_DIR="/app/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Verifica se o diretório de logs existe, se não, cria
mkdir -p $LOG_DIR

# Função para registrar mensagens de log
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/update_$TIMESTAMP.log"
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
log "Iniciando atualização de placares e manutenção"

# Verifica qual tipo de atualização executar baseado na hora do dia
HOUR=$(date +"%H")
MINUTE=$(date +"%M")

# Se for meia-noite (entre 00:00 e 00:10), executa a rotina de manutenção diária
if [ "$HOUR" == "00" ] && [ "$MINUTE" -lt "10" ]; then
    log "Executando manutenção diária (00h)"
    
    # Limpa dados antigos e atualiza placares
    log "Realizando manutenção de banco de dados"
    /usr/local/bin/python3 main.py --mode daily --update-scores-after >> "$LOG_DIR/daily_$TIMESTAMP.log" 2>&1
    
    log "Manutenção diária concluída"

# Nos outros horários, apenas atualiza placares pendentes
else
    log "Executando atualização de placares pendentes"
    /usr/local/bin/python3 main.py --mode update-scores >> "$LOG_DIR/update_scores_$TIMESTAMP.log" 2>&1
    log "Atualização de placares concluída"
fi

# Limpa logs antigos (mantém últimos 7 dias)
find "$LOG_DIR" -name "*.log" -type f -mtime +7 -delete

log "Processamento concluído"
exit 0 