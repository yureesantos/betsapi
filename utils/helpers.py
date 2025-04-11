import re
import pytz
from datetime import datetime
from config.settings import TIMEZONE


def extrair_time_jogador(nome_completo):
    """
    Extrai o nome do time e do jogador de uma string como 'Time (Jogador)'.
    Retorna (time, jogador) ou (nome_completo, None) se não houver parênteses.
    """
    if not isinstance(nome_completo, str):
        return str(nome_completo), None  # Garante que seja string, retorna sem jogador

    match = re.search(r"(.*?)\s*\((.*?)\)\s*$", nome_completo)  # Procura no final
    if match:
        time = match.group(1).strip()
        jogador = match.group(2).strip()
        # Evitar casos como "(Feminino)" ou "(Sub-20)"
        if len(jogador) > 3 and not any(kw in jogador.lower() for kw in ["feminino", "sub-", "reserva"]):
            return time, jogador
        else:
            # Se o conteúdo entre parênteses não parece ser um jogador, retorna como parte do time
            return nome_completo, None
    return nome_completo.strip(), None  # Retorna o nome completo como time se não houver jogador


def inverter_handicap(handicap_str):
    """
    Inverte o sinal de um valor de handicap.
    Retorna 'N/A' se a entrada for inválida ou '0' se a entrada for '0'.
    """
    if handicap_str is None or handicap_str == "N/A":
        return "N/A"
    try:
        # Tenta converter diretamente, comum em JSON
        valor = float(handicap_str)
        # Lida com o caso -0.0
        return str(-valor) if valor != 0 else "0.0"
    except (ValueError, TypeError):
        # Se falhar, tenta tratar como string "0.5,-1" -> pega o primeiro?
        # Por ora, vamos simplificar e retornar N/A se não for um número simples.
        return "N/A"


def converter_timestamp(timestamp_unix):
    """
    Converte um timestamp Unix para um objeto datetime com timezone.
    Retorna None se o timestamp for inválido.
    """
    if timestamp_unix is None:
        return None
    try:
        ts = int(timestamp_unix)
        tz = pytz.timezone(TIMEZONE)
        dt_utc = datetime.fromtimestamp(ts, pytz.utc)
        return dt_utc.astimezone(tz)
    except (ValueError, TypeError, OverflowError):
        # OverflowError pode ocorrer para timestamps muito grandes/inválidos
        print(f"Aviso: Timestamp inválido ou fora do intervalo: {timestamp_unix}")
        return None


def parse_score(score_string):
    """
    Valida e retorna a string de placar.
    Retorna None se o placar for inválido ou ausente.
    """
    if not score_string or not isinstance(score_string, str):
        return None
    # Verifica se parece um placar (ex: "2-1", "0-0")
    if re.match(r"^\d+-\d+$", score_string):
        return score_string
    return None  # Retorna None se não corresponder ao padrão
