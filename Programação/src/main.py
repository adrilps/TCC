import time
import config
import database
from riot_api import RiotAPIClient

def process_timeline_advanced(timeline_payload, match_id, db_connection, target_pid, enemy_pid):
    frames = timeline_payload['info']['frames']
    cursor = db_connection.cursor()
    
    p_kills = 0; p_deaths = 0; p_assists = 0

    for minute, frame in enumerate(frames):
        b_gold = 0; r_gold = 0
        p_gold = 0; e_gold = 0
        p_xp = 0; e_xp = 0
        
        # 1. Parse participant stats
        for pid_str, p_data in frame['participantFrames'].items():
            pid = int(pid_str)
            if pid <= 5: b_gold += p_data['totalGold']
            else:        r_gold += p_data['totalGold']
                
            if pid == target_pid:
                p_gold = p_data['totalGold']
                p_xp = p_data['xp']
            elif pid == enemy_pid:
                e_gold = p_data['totalGold']
                e_xp = p_data['xp']
                
        # 2. Parse combat events
        for event in frame.get('events', []):
            if event['type'] == 'CHAMPION_KILL':
                if event.get('killerId') == target_pid:
                    p_kills += 1
                elif event.get('victimId') == target_pid:
                    p_deaths += 1
                elif target_pid in event.get('assistingParticipantIds', []):
                    p_assists += 1

        cursor.execute("""
            INSERT INTO match_timeline 
            (match_id, game_minute, team_100_gold, team_200_gold, player_gold, enemy_gold, player_xp, enemy_xp, player_kills, player_deaths, player_assists)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, game_minute) DO NOTHING;
        """, (match_id, minute, b_gold, r_gold, p_gold, e_gold, p_xp, e_xp, p_kills, p_deaths, p_assists))
        
    cursor.close()

def run_pipeline():
    database.init_db()
    api = RiotAPIClient()
    
    puuid = api.get_puuid(config.GAME_NAME, config.TAG_LINE)
    if not puuid: return
        
    match_ids = api.get_recent_matches(puuid, count=20)
    db_conn = database.get_connection()
    
    try:
        for mid in match_ids:
            summary_payload = api.get_match_summary(mid)
            if not summary_payload: continue
                
            # Now save_match_summary returns the IDs we need
            matchup_data = database.save_match_summary(db_conn, summary_payload, puuid)
            if not matchup_data or not matchup_data['enemy_pid']:
                print(f"[-] Skipping {mid}: No direct lane opponent found.")
                continue 
            
            timeline_payload = api.get_match_timeline(mid)
            if timeline_payload:
                process_timeline_advanced(timeline_payload, mid, db_conn, matchup_data['target_pid'], matchup_data['enemy_pid'])
                
            db_conn.commit()
            print(f"[+] Saved 1v1 detailed dataset for {mid}")
            time.sleep(2)
            
    finally:
        db_conn.close()

if __name__ == "__main__":
    run_pipeline()