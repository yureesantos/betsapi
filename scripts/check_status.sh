#!/bin/bash
# Script para verificar o status do sistema

# Configuração
APP_DIR="/app"
LOG_DIR="/app/logs"
DB_URL=$(grep -o 'DATABASE_URL=.*' "$APP_DIR/.env" | cut -d '=' -f 2-)

echo "=================================================="
echo "       VERIFICAÇÃO DE STATUS DO SISTEMA"
echo "=================================================="
echo ""

# Verifica status do cron
echo "1. Status do serviço cron:"
if pgrep cron > /dev/null; then
    echo "   ✓ Cron está em execução"
else
    echo "   ✗ Cron não está em execução"
fi

# Verifica últimas execuções dos scripts
echo ""
echo "2. Últimas execuções (logs mais recentes):"
find "$LOG_DIR" -name "*.log" -type f -mtime -1 | sort -r | head -5 | while read log_file; do
    echo "   - $(basename "$log_file"): $(head -1 "$log_file" | grep -o '\[.*\]')"
done

# Verifica estatísticas do banco de dados
echo ""
echo "3. Estatísticas do banco de dados:"
if [ -n "$DB_URL" ]; then
    # Instala o cliente psql se necessário
    if ! command -v psql &> /dev/null; then
        echo "   Instalando cliente PostgreSQL..."
        apt-get update && apt-get install -y postgresql-client
    fi
    
    # Total de eventos
    echo "   - Total de eventos: $(PGPASSWORD=$DB_URL psql -h $(echo $DB_URL | cut -d '@' -f 2 | cut -d '/' -f 1) -U $(echo $DB_URL | cut -d ':' -f 2 | cut -d '@' -f 1) -d $(echo $DB_URL | cut -d '/' -f 4) -t -c "SELECT COUNT(*) FROM events;")"
    
    # Eventos do último dia
    echo "   - Eventos das últimas 24h: $(PGPASSWORD=$DB_URL psql -h $(echo $DB_URL | cut -d '@' -f 2 | cut -d '/' -f 1) -U $(echo $DB_URL | cut -d ':' -f 2 | cut -d '@' -f 1) -d $(echo $DB_URL | cut -d '/' -f 4) -t -c "SELECT COUNT(*) FROM events WHERE event_timestamp > NOW() - INTERVAL '24 hours';")"
    
    # Eventos sem placar
    echo "   - Eventos sem placar: $(PGPASSWORD=$DB_URL psql -h $(echo $DB_URL | cut -d '@' -f 2 | cut -d '/' -f 1) -U $(echo $DB_URL | cut -d ':' -f 2 | cut -d '@' -f 1) -d $(echo $DB_URL | cut -d '/' -f 4) -t -c "SELECT COUNT(*) FROM events WHERE (final_score IS NULL OR final_score = '');")"
else
    echo "   ✗ Variável DATABASE_URL não encontrada no arquivo .env"
fi

# Verifica uso de disco
echo ""
echo "4. Uso de disco:"
df -h / | tail -1 | awk '{print "   - Total: "$2", Usado: "$3" ("$5"), Disponível: "$4}'

# Verifica uso de memória
echo ""
echo "5. Uso de memória:"
free -h | grep Mem | awk '{print "   - Total: "$2", Usado: "$3", Livre: "$4}'

echo ""
echo "=================================================="
echo "" 