#!/bin/bash
# Script para verificar o status do cron e das tarefas agendadas

echo "=== Verificação do Status do Cron ==="

# Verifica se o cron está em execução
if pgrep cron > /dev/null; then
    echo "✅ Cron está em execução"
else
    echo "❌ Cron NÃO está em execução"
fi

# Verifica as tarefas configuradas
echo -e "\nTarefas agendadas:"
crontab -l

# Verifica os logs de heartbeat
echo -e "\nVerificando logs de heartbeat:"
if [ -f "/app/logs/cron_heartbeat.log" ]; then
    echo "✅ Arquivo de heartbeat encontrado"
    echo "Últimas 5 entradas:"
    tail -5 /app/logs/cron_heartbeat.log
else
    echo "❌ Arquivo de heartbeat não encontrado"
fi

# Verificar logs de execução
echo -e "\nVerificando logs de execução:"
LOGS=$(find /app/logs -name "update_*.log" -type f -mtime -1 | sort -r)
if [ -n "$LOGS" ]; then
    echo "✅ Logs de execução encontrados"
    echo "Arquivos de log recentes:"
    echo "$LOGS" | head -5
    
    echo -e "\nConteúdo do log mais recente:"
    head -10 "$(echo "$LOGS" | head -1)"
else
    echo "❌ Nenhum log de execução recente encontrado"
fi

# Verifica se o diretório de scripts está correto
echo -e "\nVerificando scripts:"
if [ -d "/app/scripts" ]; then
    echo "✅ Diretório de scripts encontrado"
    echo "Arquivos no diretório:"
    ls -la /app/scripts/
    
    # Verifica se os scripts têm permissão de execução
    if [ -x "/app/scripts/update_schedule.sh" ]; then
        echo "✅ Script update_schedule.sh é executável"
    else
        echo "❌ Script update_schedule.sh NÃO é executável"
    fi
else
    echo "❌ Diretório de scripts não encontrado"
fi

echo -e "\n=== Verificação concluída ===" 