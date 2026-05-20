import psycopg2
from config import DB_URI

def get_connection():
    return psycopg2.connect(DB_URI)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # TABLE 1: Added target_player_team_id and target_player_won
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id VARCHAR(50) PRIMARY KEY,
            game_duration_sec INT,
            winner_team_id INT,
            target_player_team_id INT,
            target_player_won BOOLEAN,
            blue_total_gold INT,
            red_total_gold INT,
            blue_total_kills INT,
            red_total_kills INT,
            blue_dragons INT,
            red_dragons INT
        );
    """)

    # TABLE 2: Minute-by-Minute Telemetry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_timeline (
            id SERIAL PRIMARY KEY,
            match_id VARCHAR(50) REFERENCES matches(match_id) ON DELETE CASCADE,
            game_minute INT,
            team_100_gold INT,
            team_200_gold INT,
            gold_diff INT,
            team_100_xp INT,
            team_200_xp INT,
            team_100_kills INT,
            team_200_kills INT,
            UNIQUE(match_id, game_minute)
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("[DB] Advanced storage matrix initialized.")

def save_match_summary(conn, match_data, target_puuid):
    """Upserts the high-level match results and identifies the target player."""
    info = match_data['info']
    match_id = match_data['metadata']['matchId']
    duration = info['gameDuration']
    
    # Safely extract teams
    teams = info.get('teams', [])
    blue_team = next((t for t in teams if t['teamId'] == 100), None)
    red_team = next((t for t in teams if t['teamId'] == 200), None)
    
    # If the game doesn't have standard Blue/Red teams (like Arena mode), skip it
    if not blue_team or not red_team:
        print(f"[-] Skipping {match_id}: Not a standard 5v5 mode.")
        return False
    
    winner = 100 if blue_team.get('win') else 200
    
    # Safe objective extraction (ARAM doesn't have dragons)
    blue_dragons = blue_team.get('objectives', {}).get('dragon', {}).get('kills', 0)
    red_dragons = red_team.get('objectives', {}).get('dragon', {}).get('kills', 0)
    
    blue_gold = sum(p['goldEarned'] for p in info['participants'] if p['teamId'] == 100)
    red_gold = sum(p['goldEarned'] for p in info['participants'] if p['teamId'] == 200)
    blue_kills = sum(p['kills'] for p in info['participants'] if p['teamId'] == 100)
    red_kills = sum(p['kills'] for p in info['participants'] if p['teamId'] == 200)

    # Find the target player's team and if they won
    target_player_team_id = None
    target_player_won = False
    
    for player in info['participants']:
        if player['puuid'] == target_puuid:
            target_player_team_id = player['teamId']
            target_player_won = (target_player_team_id == winner)
            break

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO matches 
        (match_id, game_duration_sec, winner_team_id, target_player_team_id, target_player_won, 
         blue_total_gold, red_total_gold, blue_total_kills, red_total_kills, blue_dragons, red_dragons)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (match_id) DO NOTHING;
    """, (match_id, duration, winner, target_player_team_id, target_player_won, 
          blue_gold, red_gold, blue_kills, red_kills, blue_dragons, red_dragons))
    
    cursor.close()
    return True