-- Contagem total de eventos no banco
SELECT COUNT(*) AS total_eventos FROM events;

-- Contagem de eventos por liga
SELECT league_id, league_name, COUNT(*) AS total 
FROM events 
GROUP BY league_id, league_name
ORDER BY total DESC;

-- Distribuição por data (últimos 60 dias)
SELECT 
    DATE(event_timestamp AT TIME ZONE 'America/Sao_Paulo') AS data, 
    COUNT(*) AS total_jogos
FROM events
WHERE event_timestamp > NOW() - INTERVAL '60 days'
GROUP BY data
ORDER BY data DESC;

-- Verificar completude dos dados (eventos com placar)
SELECT 
    COUNT(*) AS total,
    COUNT(CASE WHEN final_score IS NOT NULL AND final_score != '' THEN 1 END) AS com_placar,
    ROUND(
        COUNT(CASE WHEN final_score IS NOT NULL AND final_score != '' THEN 1 END) * 100.0 / COUNT(*),
        2
    ) AS percentual_com_placar
FROM events;

-- Verificar quantos eventos são de cada mês
SELECT 
    TO_CHAR(event_timestamp AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM') AS mes,
    COUNT(*) AS total_eventos
FROM events
GROUP BY mes
ORDER BY mes DESC;

-- Verificar eventos mais recentes
SELECT 
    event_id, league_name, 
    home_team_name, home_player_name, 
    away_team_name, away_player_name,
    final_score, 
    event_timestamp AT TIME ZONE 'America/Sao_Paulo' AS hora_local
FROM events
ORDER BY event_timestamp DESC
LIMIT 20;

-- Verificar eventos sem placar que já deveriam ter terminado
SELECT 
    event_id, league_name, 
    home_team_name, home_player_name, 
    away_team_name, away_player_name,
    event_timestamp AT TIME ZONE 'America/Sao_Paulo' AS hora_local
FROM events
WHERE (final_score IS NULL OR final_score = '')
AND event_timestamp < NOW() - INTERVAL '3 hours'
ORDER BY event_timestamp DESC
LIMIT 20; 