import psycopg2
from config import DB_URI

def get_connection():
    return psycopg2.connect(DB_URI)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Added Barons and Towers to the schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id VARCHAR(50) PRIMARY KEY,
            game_version VARCHAR(20),
            game_duration_sec INT,
            winner_team_id INT,
            target_player_team_id INT,
            target_player_won BOOLEAN,
            role VARCHAR(20),
            target_pid INT,
            enemy_pid INT,
            blue_total_gold INT,
            red_total_gold INT,
            blue_dragons INT,
            red_dragons INT,
            blue_barons INT,
            red_barons INT,
            blue_towers INT,
            red_towers INT
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS match_timeline (
        id SERIAL PRIMARY KEY,
        match_id VARCHAR(50) REFERENCES matches(match_id) ON DELETE CASCADE,
        game_minute INT,
        team_100_gold INT,
        team_200_gold INT,
        player_gold INT,
        enemy_gold INT,
        player_xp INT,
        enemy_xp INT,
        player_cs INT,
        enemy_cs INT,
        player_level INT,
        enemy_level INT,
        player_current_gold INT,
        player_dmg INT,
        enemy_dmg INT,
        player_pos_x INT,
        player_pos_y INT,
        player_kills INT,
        player_deaths INT,
        player_assists INT,
        UNIQUE(match_id, game_minute)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS match_events (
        match_id VARCHAR REFERENCES matches(match_id) ON DELETE CASCADE,
        minute INT,
        event_type VARCHAR,
        value VARCHAR,
        participant VARCHAR,
        PRIMARY KEY (match_id, minute, event_type, value, participant)
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()

def save_match_summary(conn, match_data, target_puuid):
    """Upserts the high-level match results and identifies the 1v1 matchup."""
    info = match_data['info']
    match_id = match_data['metadata']['matchId']
    duration = info['gameDuration']
    
    raw_version = info.get('gameVersion', 'Unknown')
    game_version = ".".join(raw_version.split('.')[:2]) if raw_version != 'Unknown' else raw_version
    
    teams = info.get('teams', [])
    blue_team = next((t for t in teams if t['teamId'] == 100), None)
    red_team = next((t for t in teams if t['teamId'] == 200), None)
    
    if not blue_team or not red_team:
        return False
    
    winner = 100 if blue_team.get('win') else 200
    
    # --- MACRO STAT EXTRACTION ---
    blue_dragons = blue_team.get('objectives', {}).get('dragon', {}).get('kills', 0)
    red_dragons = red_team.get('objectives', {}).get('dragon', {}).get('kills', 0)
    
    blue_barons = blue_team.get('objectives', {}).get('baron', {}).get('kills', 0)
    red_barons = red_team.get('objectives', {}).get('baron', {}).get('kills', 0)
    
    blue_towers = blue_team.get('objectives', {}).get('tower', {}).get('kills', 0)
    red_towers = red_team.get('objectives', {}).get('tower', {}).get('kills', 0)
    
    blue_gold = sum(p['goldEarned'] for p in info['participants'] if p['teamId'] == 100)
    red_gold = sum(p['goldEarned'] for p in info['participants'] if p['teamId'] == 200)

    # Find Target Player and Enemy Matchup
    target_player = next((p for p in info['participants'] if p['puuid'] == target_puuid), None)
    if not target_player:
        return False

    target_pid = target_player['participantId']
    role = target_player.get('teamPosition', 'UNKNOWN')
    target_player_team_id = target_player['teamId']
    target_player_won = (target_player_team_id == winner)
    
    enemy_player = next((p for p in info['participants'] if p['teamPosition'] == role and p['participantId'] != target_pid), None)
    enemy_pid = enemy_player['participantId'] if enemy_player else None

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO matches 
        (match_id, game_version, game_duration_sec, winner_team_id, target_player_team_id, target_player_won, 
         role, target_pid, enemy_pid, blue_total_gold, red_total_gold, blue_dragons, red_dragons,
         blue_barons, red_barons, blue_towers, red_towers)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (match_id) DO NOTHING;
    """, (match_id, game_version, duration, winner, target_player_team_id, target_player_won, 
          role, target_pid, enemy_pid, blue_gold, red_gold, blue_dragons, red_dragons,
          blue_barons, red_barons, blue_towers, red_towers))
    
    cursor.close()
    return {'target_pid': target_pid, 'enemy_pid': enemy_pid}