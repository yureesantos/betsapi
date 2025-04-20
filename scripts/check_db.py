#!/usr/bin/env python3
"""
Script para verificar o estado do banco de dados
"""
from db.database import get_db_connection
import datetime


def check_database():
    """Verifica estatísticas básicas do banco de dados"""
    print("=== Verificação do Banco de Dados ===")

    try:
        with get_db_connection() as conn:
            cur = conn.cursor()

            # Total de eventos
            cur.execute("SELECT COUNT(*) FROM events")
            total = cur.fetchone()[0]
            print(f"Total de eventos: {total}")

            # Eventos das últimas 24 horas
            cur.execute("SELECT COUNT(*) FROM events WHERE event_timestamp > NOW() - INTERVAL '1 day'")
            last_day = cur.fetchone()[0]
            print(f"Eventos das últimas 24 horas: {last_day}")

            # Eventos sem placar
            cur.execute("SELECT COUNT(*) FROM events WHERE (final_score IS NULL OR final_score = '')")
            no_score = cur.fetchone()[0]
            print(f"Eventos sem placar: {no_score}")

            # Eventos por liga
            print("\nEventos por liga:")
            cur.execute(
                """
                SELECT league_name, COUNT(*) 
                FROM events 
                GROUP BY league_name 
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """
            )
            for league, count in cur.fetchall():
                print(f"  {league}: {count}")

            # Eventos mais recentes
            print("\nEventos mais recentes:")
            cur.execute(
                """
                SELECT event_id, league_name, home_team_name, away_team_name, 
                       final_score, event_timestamp
                FROM events
                ORDER BY event_timestamp DESC
                LIMIT 3
            """
            )
            for event in cur.fetchall():
                print(
                    f"  ID: {event[0]} | {event[1]} | {event[2]} vs {event[3]} | Placar: {event[4] or 'N/A'} | Data: {event[5]}"
                )

            print("\n=== Verificação concluída ===")

    except Exception as e:
        print(f"Erro ao verificar banco de dados: {e}")


if __name__ == "__main__":
    check_database()
