import time
import config
import database
from riot_api import RiotAPIClient

def process_timeline_advanced(timeline_payload, match_id, db_connection):
    """Processes structured raw JSON timeline data into fine-grained relational metrics."""
    frames = timeline_payload['info']['frames']
    cursor = db_connection.cursor()
    
    # Track accumulated kills dynamically as we iterate sequentially through frames
    blue_kills = 0
    red_kills = 0

    for minute, frame in enumerate(frames):
        blue_gold = 0; red_gold = 0
        blue_xp = 0;   red_xp = 0
        
        # 1. Parse player frames to calculate aggregated assets per team
        for pid_str, p_data in frame['participantFrames'].items():
            pid = int(pid_str)
            if pid <= 5:
                blue_gold += p_data['totalGold']
                blue_xp += p_data['xp']
            else:
                red_gold += p_data['totalGold']
                red_xp += p_data['xp']
                
        # 2. Parse discrete frame event lists for active combat kills
        for event in frame.get('events', []):
            if event['type'] == 'CHAMPION_KILL':
                killer_id = event.get('killerId', 0)
                if 0 < killer_id <= 5:
                    blue_kills += 1
                elif killer_id > 5:
                    red_kills += 1

        gold_diff = blue_gold - red_gold

        # 3. Store high-fidelity telemetry metrics inside relational layout
        cursor.execute("""
            INSERT INTO match_timeline 
            (match_id, game_minute, team_100_gold, team_200_gold, gold_diff, team_100_xp, team_200_xp, team_100_kills, team_200_kills)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, game_minute) DO NOTHING;
        """, (match_id, minute, blue_gold, red_gold, gold_diff, blue_xp, red_xp, blue_kills, red_kills))
        
    cursor.close()

def run_pipeline():
    """Main execution lifecycle routing raw telemetry payloads directly into the active TSDB matrix."""
    # Ensure system structures exist
    database.init_db()
    api = RiotAPIClient()
    
    # 1. Identity Verification
    print(f"[RUN] Querying player identification signature for: {config.GAME_NAME}#{config.TAG_LINE}")
    puuid = api.get_puuid(config.GAME_NAME, config.TAG_LINE)
    if not puuid:
        print("[-] Pipeline canceled: Unable to verify target player identity.")
        return
        
    # 2. History Mining Vector
    print(f"[RUN] Mining history catalog. Extracting latest 20 match vectors...")
    match_ids = api.get_recent_matches(puuid, count=20)
    print(f"[RUN] Found {len(match_ids)} candidate games for telemetry sync.")
    
    db_conn = database.get_connection()
    
    try:
        for mid in match_ids:
            print(f"\n[*] Syncing vector: {mid}")
            
            # Phase A: Get high-level summary metadata & record personal win parameters
            summary_payload = api.get_match_summary(mid)
            if not summary_payload:
                print(f"[-] Failed to access master record for {mid}. Skipping target.")
                continue
                
            # Store summary metadata matrix and test format validity
            is_standard_game = database.save_match_summary(db_conn, summary_payload, puuid)
            if not is_standard_game:
                # Silently skips processing the timeline for custom maps or Arena variants
                continue
            
            # Phase B: Get time-series frame arrays
            timeline_payload = api.get_match_timeline(mid)
            if timeline_payload:
                process_timeline_advanced(timeline_payload, mid, db_conn)
                
            # Safely commit transaction block down the database pipe
            db_conn.commit()
            print(f"[+] Successfully structured and indexed match: {mid}")
            
            # Safe data rate limits throttle buffer on active dev keys
            time.sleep(2.0)
            
    except Exception as e:
        print(f"\n[CRITICAL FAILURE] Pipeline execution ruptured unexpectedly: {e}")
        db_conn.rollback()
    finally:
        db_conn.close()
        print("\n[RUN] Synchronization loop executed completely. Database pool safely returned.")

if __name__ == "__main__":
    run_pipeline()