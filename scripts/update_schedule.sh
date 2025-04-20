#!/bin/bash
# Script para atualização periódica dos dados da BetsAPI
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
log "Iniciando atualização periódica de dados"

# Verifica qual tipo de atualização executar baseado na hora do dia
HOUR=$(date +"%H")
MINUTE=$(date +"%M")

# Se for meia-noite (entre 00:00 e 00:10), executa a rotina de manutenção diária
if [ "$HOUR" == "00" ] && [ "$MINUTE" -lt "10" ]; then
    log "Executando manutenção diária (00h)"
    
    # 1. Atualiza todos os jogos do dia
    log "Atualizando jogos do dia"
    python main.py --mode daily --update-scores-after >> "$LOG_DIR/daily_$TIMESTAMP.log" 2>&1
    
    # 2. Atualiza a janela deslizante (remove d-60 e adiciona d+1)
    log "Atualizando janela deslizante (removendo dados antigos e adicionando novos)"
    
    # Calcular data para backfill (amanhã)
    TOMORROW=$(date -d "tomorrow" +"%Y%m%d")
    
    # Executa backfill somente para amanhã
    python main.py --mode backfill --days 1 --start-date $TOMORROW --update-scores-after >> "$LOG_DIR/backfill_$TIMESTAMP.log" 2>&1
    
    log "Manutenção diária concluída"

# Atualização a cada hora (executa nos minutos 0-5 de cada hora)
elif [ "$MINUTE" -lt "5" ]; then
    log "Executando atualização horária"
    python main.py --mode daily >> "$LOG_DIR/hourly_$TIMESTAMP.log" 2>&1
    log "Atualização horária concluída"

# Atualização a cada 15 minutos (só atualiza placares)
else
    log "Executando atualização rápida (apenas placares pendentes)"
    python main.py --mode update-scores >> "$LOG_DIR/quick_$TIMESTAMP.log" 2>&1
    log "Atualização rápida concluída"
fi

# Limpa logs antigos (mantém últimos 7 dias)
find "$LOG_DIR" -name "*.log" -type f -mtime +7 -delete

log "Processamento concluído"
exit 0 