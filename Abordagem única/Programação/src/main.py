import time
import config
import database
from riot_api import RiotAPIClient

def process_timeline_advanced(timeline_payload, match_id, db_connection, target_pid, enemy_pid):
    frames = timeline_payload['info']['frames']
    cursor = db_connection.cursor()
    
    p_kills = 0; p_deaths = 0; p_assists = 0
    
    # Event-level table (separate from per-minute aggregates)
    significant_events = []

    for minute, frame in enumerate(frames):
        b_gold = 0; r_gold = 0
        p_gold = 0; e_gold = 0
        p_xp = 0; e_xp = 0
        p_cs = 0; e_cs = 0
        p_level = 0; e_level = 0
        p_current_gold = 0
        p_dmg = 0; e_dmg = 0
        p_pos = None

        for pid_str, p_data in frame['participantFrames'].items():
            pid = int(pid_str)
            if pid <= 5: b_gold += p_data['totalGold']
            else:        r_gold += p_data['totalGold']

            if pid == target_pid:
                p_gold        = p_data['totalGold']
                p_xp          = p_data['xp']
                p_cs          = p_data['minionsKilled'] + p_data.get('jungleMinionsKilled', 0)
                p_level       = p_data['level']
                p_current_gold= p_data['currentGold']
                p_dmg         = p_data['damageStats'].get('totalDamageDoneToChampions', 0)
                p_pos         = p_data.get('position')  # {'x': int, 'y': int}
            elif pid == enemy_pid:
                e_gold  = p_data['totalGold']
                e_xp    = p_data['xp']
                e_cs    = p_data['minionsKilled'] + p_data.get('jungleMinionsKilled', 0)
                e_level = p_data['level']
                e_dmg   = p_data['damageStats'].get('totalDamageDoneToChampions', 0)

        for event in frame.get('events', []):
            etype = event['type']
            ts_min = event['timestamp'] // 60000  # ms to minutes

            if etype == 'CHAMPION_KILL':
                if event.get('killerId') == target_pid:
                    p_kills += 1
                elif event.get('victimId') == target_pid:
                    p_deaths += 1
                elif target_pid in event.get('assistingParticipantIds', []):
                    p_assists += 1

            elif etype == 'ITEM_PURCHASED' and event.get('participantId') == target_pid:
                significant_events.append({
                    'match_id': match_id, 'minute': ts_min,
                    'event_type': 'ITEM_PURCHASED', 'value': event['itemId'],
                    'participant': 'player'
                })

            elif etype == 'LEVEL_UP' and event.get('participantId') in [target_pid, enemy_pid]:
                who = 'player' if event['participantId'] == target_pid else 'enemy'
                significant_events.append({
                    'match_id': match_id, 'minute': ts_min,
                    'event_type': 'LEVEL_UP', 'value': event['level'],
                    'participant': who
                })

            elif etype == 'ELITE_MONSTER_KILL':
                significant_events.append({
                    'match_id': match_id, 'minute': ts_min,
                    'event_type': 'ELITE_MONSTER_KILL',
                    'value': event.get('monsterType'),
                    'participant': 'team' if event.get('killerId', 0) <= 5 else 'enemy_team'
                })

            elif etype == 'BUILDING_KILL':
                significant_events.append({
                    'match_id': match_id, 'minute': ts_min,
                    'event_type': 'BUILDING_KILL',
                    'value': event.get('buildingType'),
                    'participant': 'team' if event.get('teamId') == 200 else 'enemy_team'
                    # note: teamId here is the team that LOST the building
                })

        cursor.execute("""
            INSERT INTO match_timeline 
            (match_id, game_minute,
             team_100_gold, team_200_gold,
             player_gold, enemy_gold,
             player_xp, enemy_xp,
             player_cs, enemy_cs,
             player_level, enemy_level,
             player_current_gold,
             player_dmg, enemy_dmg,
             player_pos_x, player_pos_y,
             player_kills, player_deaths, player_assists)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (match_id, game_minute) DO NOTHING;
        """, (
            match_id, minute,
            b_gold, r_gold,
            p_gold, e_gold,
            p_xp, e_xp,
            p_cs, e_cs,
            p_level, e_level,
            p_current_gold,
            p_dmg, e_dmg,
            p_pos['x'] if p_pos else None,
            p_pos['y'] if p_pos else None,
            p_kills, p_deaths, p_assists
        ))

    # Insert events separately
    for ev in significant_events:
        cursor.execute("""
            INSERT INTO match_events
            (match_id, minute, event_type, value, participant)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;
        """, (ev['match_id'], ev['minute'], ev['event_type'], str(ev['value']), ev['participant']))

    cursor.close()

def run_pipeline():
    database.init_db()
    api = RiotAPIClient()
    
    puuid = api.get_puuid(config.GAME_NAME, config.TAG_LINE)
    if not puuid: return
        
    match_ids = api.get_recent_matches(puuid, count=50)
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