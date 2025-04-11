import os
import requests
import time
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import pandas as pd
import keyboard
import sys
import re

def extrair_time_jogador(nome_completo):
    # Procura por texto entre parênteses
    match = re.search(r'(.*?)\s*\((.*?)\)', nome_completo)
    if match:
        time = match.group(1).strip()
        jogador = match.group(2).strip()
        return time, jogador
    return nome_completo, ''  # Retorna o nome completo como time se não houver jogador

def inverter_handicap(handicap):
    try:
        if handicap == 'N/A':
            return 'N/A'
        valor = float(handicap)
        return str(-valor) if valor != 0 else '0'
    except:
        return 'N/A'

def buscar_ultimos_jogos(limite_jogos=10):
    # Carrega as variáveis de ambiente
    load_dotenv()
    
    # Configurações da API
    token = os.getenv('BETSAPI_TOKEN')
    base_url_v1 = 'https://api.b365api.com/v1'
    base_url_v2 = 'https://api.b365api.com/v2'
    
    # Configuração do timezone
    tz = pytz.timezone('America/Sao_Paulo')
    
    # Lista para armazenar os jogos
    todos_jogos = []
    
    print(f"Buscando os últimos {limite_jogos} jogos...")
    print("Pressione 'q' para parar a busca a qualquer momento.")
    
    try:
        # Primeiro busca os jogos encerrados
        params = {
            'token': token,
            'sport_id': 1,  # Soccer
            'skip_esports': 0,  # Inclui E-sports
            'page': 1
        }
        
        response = requests.get(f"{base_url_v1}/events/ended", params=params)
        time.sleep(1)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success') == 1:
                jogos = data.get('results', [])[:limite_jogos]
                
                if not jogos:
                    print("Nenhum jogo encontrado.")
                    return
                
                print(f"Processando {len(jogos)} jogos...")
                
                for jogo in jogos:
                    if keyboard.is_pressed('q'):
                        print("\nBusca interrompida pelo usuário.")
                        break
                    
                    # Extrai o event_id do jogo
                    jogo_id = jogo.get('id')
                    
                    # Inicializa as odds para todos os mercados
                    odds_1x2 = {
                        'casa': 'N/A',
                        'empate': 'N/A',
                        'fora': 'N/A'
                    }
                    odds_handicap = {
                        'casa': 'N/A',
                        'fora': 'N/A',
                        'linha_casa': 'N/A',
                        'linha_fora': 'N/A'
                    }
                    odds_over_under = {
                        'over': 'N/A',
                        'under': 'N/A',
                        'linha': 'N/A'
                    }
                    
                    # Extrai os dados básicos do jogo
                    league_data = jogo.get('league', {})
                    home_data = jogo.get('home', {})
                    away_data = jogo.get('away', {})
                    liga_nome = league_data.get('name', 'N/A')
                    
                    # Extrai time e jogador para casa e visitante
                    time_casa, jogador_casa = extrair_time_jogador(home_data.get('name', 'N/A'))
                    time_fora, jogador_fora = extrair_time_jogador(away_data.get('name', 'N/A'))
                    
                    print(f"\nProcessando jogo ID: {jogo_id}")
                    print(f"Times: {time_casa} ({jogador_casa}) vs {time_fora} ({jogador_fora})")
                    
                    # Busca as odds usando o endpoint de summary
                    try:
                        odds_url = f"{base_url_v2}/event/odds/summary?token={token}&event_id={jogo_id}"
                        odds_response = requests.get(odds_url)
                        time.sleep(1)
                        
                        if odds_response.status_code == 200:
                            odds_data = odds_response.json()
                            
                            if odds_data.get('success') == 1:
                                results = odds_data.get('results', {})
                                bet365_data = results.get('Bet365', {})
                                odds_start = bet365_data.get('odds', {}).get('start', {})
                                
                                # Processa o mercado 1_1 (1X2)
                                if '1_1' in odds_start:
                                    market_1x2 = odds_start['1_1']
                                    odds_1x2 = {
                                        'casa': market_1x2.get('home_od', 'N/A'),
                                        'empate': market_1x2.get('draw_od', 'N/A'),
                                        'fora': market_1x2.get('away_od', 'N/A')
                                    }
                                
                                # Processa o mercado 1_2 (Handicap Asiático)
                                if '1_2' in odds_start:
                                    market_handicap = odds_start['1_2']
                                    handicap_casa = market_handicap.get('handicap', 'N/A')
                                    odds_handicap = {
                                        'casa': market_handicap.get('home_od', 'N/A'),
                                        'fora': market_handicap.get('away_od', 'N/A'),
                                        'linha_casa': handicap_casa,
                                        'linha_fora': inverter_handicap(handicap_casa)
                                    }
                                
                                # Processa o mercado 1_3 (Over/Under)
                                if '1_3' in odds_start:
                                    market_over_under = odds_start['1_3']
                                    odds_over_under = {
                                        'over': market_over_under.get('over_od', 'N/A'),
                                        'under': market_over_under.get('under_od', 'N/A'),
                                        'linha': market_over_under.get('handicap', 'N/A')
                                    }
                                
                                print(f"Odds 1X2 - Casa: {odds_1x2['casa']}, Empate: {odds_1x2['empate']}, Fora: {odds_1x2['fora']}")
                                print(f"Handicap Asiático - Casa ({odds_handicap['linha_casa']}): {odds_handicap['casa']}, Fora ({odds_handicap['linha_fora']}): {odds_handicap['fora']}")
                                print(f"Over/Under - Over: {odds_over_under['over']}, Under: {odds_over_under['under']}, Linha: {odds_over_under['linha']}")
                    
                    except Exception as e:
                        print(f"Erro ao buscar odds: {str(e)}")
                        print(f"URL que falhou: {odds_url}")
                    
                    # Converte o timestamp
                    timestamp = jogo.get('time')
                    if timestamp and str(timestamp).isdigit():
                        dt = datetime.fromtimestamp(int(timestamp), tz)
                        data = dt.strftime('%d/%m/%Y')
                        hora = dt.strftime('%H:%M:%S')
                    else:
                        data = "N/A"
                        hora = "N/A"
                    
                    # Obtém o placar
                    ss = jogo.get('ss', '')
                    placar = ss if ss else "N/A"
                    
                    # Adiciona os dados do jogo à lista
                    todos_jogos.append({
                        'ID': jogo_id,
                        'Liga': liga_nome,
                        'Jogador Casa': jogador_casa,
                        'Time Casa': time_casa,
                        'Jogador Fora': jogador_fora,
                        'Time Fora': time_fora,
                        'Placar': placar,
                        'Data': data,
                        'Hora': hora,
                        # Odds 1X2
                        '1X2 Casa': odds_1x2['casa'],
                        '1X2 Empate': odds_1x2['empate'],
                        '1X2 Fora': odds_1x2['fora'],
                        # Handicap Asiático
                        'Handicap Casa': odds_handicap['casa'],
                        'Handicap Fora': odds_handicap['fora'],
                        'Handicap Linha Casa': odds_handicap['linha_casa'],
                        'Handicap Linha Fora': odds_handicap['linha_fora'],
                        # Over/Under
                        'Over': odds_over_under['over'],
                        'Under': odds_over_under['under'],
                        'Over/Under Linha': odds_over_under['linha']
                    })
                    
                    print("-" * 50)
        
        if todos_jogos:
            # Cria o DataFrame
            df = pd.DataFrame(todos_jogos)
            
            # Reordena as colunas para manter jogador antes do time e data/hora juntos
            colunas_ordenadas = [col for col in df.columns if col not in ['ID', 'Liga', 'Jogador Casa', 'Time Casa', 'Jogador Fora', 'Time Fora', 'Data', 'Hora']]
            nova_ordem = ['ID', 'Liga', 'Jogador Casa', 'Time Casa', 'Jogador Fora', 'Time Fora', 'Data', 'Hora'] + colunas_ordenadas
            df = df[nova_ordem]
            
            # Salva em Excel
            data_hora_atual = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            nome_arquivo = f'ultimos_{limite_jogos}_jogos_{data_hora_atual}.xlsx'
            df.to_excel(nome_arquivo, index=False)
            print(f"\nTotal de jogos encontrados: {len(todos_jogos)}")
            print(f"Dados salvos em {nome_arquivo}")
            
            # Exibe os dados no console
            print("\nÚltimos jogos:")
            for jogo in todos_jogos:
                print(f"\nID: {jogo['ID']}")
                print(f"Liga: {jogo['Liga']}")
                print(f"Jogador Casa: {jogo['Jogador Casa']} | Time: {jogo['Time Casa']}")
                print(f"Jogador Fora: {jogo['Jogador Fora']} | Time: {jogo['Time Fora']}")
                print(f"Placar: {jogo['Placar']}")
                print(f"Data: {jogo['Data']}")
                print(f"Hora: {jogo['Hora']}")
                print("\nOdds 1X2:")
                print(f"Casa: {jogo['1X2 Casa']} | Empate: {jogo['1X2 Empate']} | Fora: {jogo['1X2 Fora']}")
                print("\nHandicap Asiático:")
                print(f"Casa ({jogo['Handicap Linha Casa']}): {jogo['Handicap Casa']}")
                print(f"Fora ({jogo['Handicap Linha Fora']}): {jogo['Handicap Fora']}")
                print("\nOver/Under:")
                print(f"Over: {jogo['Over']} | Under: {jogo['Under']} | Linha: {jogo['Over/Under Linha']}")
                print("-" * 50)
        else:
            print("Nenhum jogo encontrado.")
            
    except Exception as e:
        print(f"Erro ao buscar jogos: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        keyboard.unhook_all()

if __name__ == "__main__":
    buscar_ultimos_jogos(10)