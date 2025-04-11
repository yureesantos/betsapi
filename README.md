    # BetsAPI Data Collector

    Este projeto coleta dados de jogos e odds da BetsAPI e os armazena em um banco de dados PostgreSQL (Supabase) para análises futuras.

    ## Funcionalidades

    *   Busca jogos encerrados da API.
    *   Busca odds pré-jogo (1X2, Handicap Asiático, Over/Under) para cada jogo.
    *   Armazena os dados em tabelas estruturadas no Supabase.
    *   Gerencia o estado da busca para permitir pausa e retomada.
    *   Tratamento básico de erros e limites da API.

    ## Configuração

    1.  **Clone o repositório:**
        ```bash
        git clone <url_do_repositorio>
        cd betsapi
        ```

    2.  **Crie e ative um ambiente virtual (recomendado):**
        ```bash
        python -m venv venv
        source venv/bin/activate  # Linux/macOS
        # venv\Scripts\activate  # Windows
        ```

    3.  **Instale as dependências:**
        ```bash
        pip install -r requirements.txt
        ```

    4.  **Configure as variáveis de ambiente:**
        *   Crie um arquivo chamado `.env` na raiz do projeto.
        *   Adicione suas credenciais:
          ```dotenv
          BETSAPI_TOKEN=SUA_CHAVE_API_AQUI
          DATABASE_URL=SUA_URL_DE_CONEXAO_SUPABASE_AQUI # Formato: postgresql://user:password@host:port/database
          ```

    5.  **Crie as tabelas no banco de dados:**
        *   Conecte-se ao seu banco de dados Supabase.
        *   Execute o script SQL encontrado em `db/schema.sql`. Você pode fazer isso através da interface SQL do Supabase.

    ## Uso

    Execute o script principal:

    ```bash
    python main.py
    ```

    O script começará a buscar os jogos a partir da última página processada (ou da página 1, se for a primeira execução). Pressione `Ctrl+C` para parar o script. Ele tentará salvar o estado atual antes de sair.

    ## Estrutura do Projeto

    *   `main.py`: Ponto de entrada principal.
    *   `config/`: Configurações (leitura do `.env`).
    *   `db/`: Interação com o banco de dados (conexão, queries, schema).
    *   `api/`: Cliente para a BetsAPI.
    *   `utils/`: Funções auxiliares.
    *   `.env`: Arquivo de variáveis de ambiente (NÃO versionar).
    *   `requirements.txt`: Dependências.
