#!/bin/bash
# Script para configurar o cron no ambiente Fly.io

set -e  # Sai imediatamente se algum comando falhar

echo "=== INICIANDO CONFIGURAÇÃO DO CRON ==="

# Configuração de caminhos
SCRIPTS_DIR="/app/scripts"
LOG_DIR="/app/logs"

# Verifica se o diretório de scripts existe, senão cria
echo "Criando diretórios..."
mkdir -p $SCRIPTS_DIR
mkdir -p $LOG_DIR

# Torna todos os scripts executáveis
echo "Tornando scripts executáveis..."
chmod +x $SCRIPTS_DIR/*.sh

# Verifica se o cron está instalado
if ! command -v crontab &> /dev/null; then
    echo "Cron não está instalado. Instalando..."
    apt-get update && apt-get install -y cron
fi

# Cria um pequeno servidor HTTP para manter o processo vivo
echo "Criando servidor HTTP mínimo..."
cat > $SCRIPTS_DIR/http_server.py << 'EOF'
import http.server
import socketserver
import os
import datetime

# Configuração do servidor
PORT = int(os.environ.get('PORT', 8080))
Handler = http.server.SimpleHTTPRequestHandler

class CustomHandler(Handler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # Página básica com informações de status
        html = f"""
        <html>
        <head><title>BetsAPI Status</title></head>
        <body>
            <h1>BetsAPI Status</h1>
            <p>Servidor ativo em: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>O cron deve estar funcionando em segundo plano.</p>
            <p>Última atualização: <span id="last-update">{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span></p>
            <script>
                // Atualiza a hora a cada segundo
                setInterval(() => {{
                    document.getElementById("last-update").textContent = 
                        new Date().toLocaleString();
                }}, 1000);
            </script>
        </body>
        </html>
        """
        
        self.wfile.write(html.encode())

print(f"Servidor iniciado na porta {PORT}. Use ctrl+c para parar.")
with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Servidor encerrado.")
EOF

chmod +x $SCRIPTS_DIR/http_server.py

# Inicia o serviço cron se não estiver rodando
if ! pgrep cron > /dev/null; then
    echo "Iniciando serviço cron..."
    service cron start || /etc/init.d/cron start
fi

# Instala a configuração do crontab
echo "Instalando configuração do crontab..."
cat > $SCRIPTS_DIR/crontab-config.txt << 'EOF'
# Crontab para execução dos scripts de atualização

# Executa a cada 15 minutos
*/15 * * * * /app/scripts/update_schedule.sh >> /app/logs/cron_execution.log 2>&1

# Executa o serviço de limpeza de logs uma vez por semana (domingo às 2h da manhã)
0 2 * * 0 find /app/logs -name "*.log" -type f -mtime +7 -delete

# Mantém um registro de que o cron está funcionando
*/5 * * * * date >> /app/logs/cron_heartbeat.log
EOF

# Instala o crontab
crontab $SCRIPTS_DIR/crontab-config.txt

# Verifica se a instalação foi bem-sucedida
if [ $? -eq 0 ]; then
    echo "✅ Crontab instalado com sucesso!"
    crontab -l
else
    echo "❌ Erro ao instalar crontab!"
    exit 1
fi

# Executa a primeira atualização imediatamente
echo "Executando primeira atualização..."
$SCRIPTS_DIR/update_schedule.sh >> $LOG_DIR/initial_update.log 2>&1 &

echo "✅ Configuração concluída. O script de atualização será executado a cada 15 minutos."
echo "=== PROCESSO DE CONFIGURAÇÃO FINALIZADO ==="
exit 0 