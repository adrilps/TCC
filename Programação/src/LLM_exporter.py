import psycopg2
import config
import os
from datetime import datetime

def get_match_as_text(match_id):
    conn = psycopg2.connect(config.DB_URI)
    cursor = conn.cursor()
    
    # 1. Fetch Summary (Now including Barons and Towers)
    cursor.execute("""
        SELECT game_version, game_duration_sec, role, target_player_won, target_player_team_id, 
               blue_dragons, red_dragons, blue_barons, red_barons, blue_towers, red_towers
        FROM matches WHERE match_id = %s;
    """, (match_id,))
    summary = cursor.fetchone()
    if not summary: return f"Match not found."
    
    version, duration, role, won, team_id, b_drags, r_drags, b_barons, r_barons, b_towers, r_towers = summary
    result = "WON" if won else "LOST"
    
    # Calculate Team Objective Control
    player_drags = b_drags if team_id == 100 else r_drags
    enemy_drags = r_drags if team_id == 100 else b_drags
    
    player_barons = b_barons if team_id == 100 else r_barons
    enemy_barons = r_barons if team_id == 100 else b_barons
    
    player_towers = b_towers if team_id == 100 else r_towers
    enemy_towers = r_towers if team_id == 100 else b_towers
    
    # 2. Fetch Milestones
    cursor.execute("""
        SELECT game_minute, team_100_gold, team_200_gold, player_gold, enemy_gold, player_xp, enemy_xp, player_kills, player_deaths, player_assists
        FROM match_timeline
        WHERE match_id = %s AND (game_minute IN (10, 15) OR game_minute = (SELECT MAX(game_minute) FROM match_timeline WHERE match_id = %s))
        ORDER BY game_minute;
    """, (match_id, match_id))
    
    milestones = cursor.fetchall()
    cursor.close()
    conn.close()

    # 3. Build the Scouting Report
    prompt = f"**Result:** {result} | **Patch:** {version} | **Role:** {role} | **Duration:** {duration//60}m {duration%60}s\n"
    prompt += f"**Final Objectives:**\n"
    prompt += f"  - Team: {player_towers} Towers, {player_drags} Dragons, {player_barons} Barons\n"
    prompt += f"  - Enemy: {enemy_towers} Towers, {enemy_drags} Dragons, {enemy_barons} Barons\n"
    
    for row in milestones:
        minute, b_gold, r_gold, p_gold, e_gold, p_xp, e_xp, kills, deaths, assists = row
        
        gold_delta = p_gold - e_gold
        xp_delta = p_xp - e_xp
        team_delta = b_gold - r_gold if team_id == 100 else r_gold - b_gold
            
        gold_str = f"+{gold_delta}" if gold_delta > 0 else str(gold_delta)
        xp_str = f"+{xp_delta}" if xp_delta > 0 else str(xp_delta)
        team_str = f"+{team_delta}" if team_delta > 0 else str(team_delta)
        
        phase = "Early Game" if minute == 10 else "Mid Game Transition" if minute == 15 else "Final Game State"
        
        prompt += f"\n* **Minute {minute} ({phase}):**\n"
        prompt += f"  - Micro (1v1): {gold_str} Gold, {xp_str} XP\n"
        prompt += f"  - Macro (Team): {team_str} Overall Gold\n"
        prompt += f"  - Player KDA: {kills}/{deaths}/{assists}\n"
        
    return prompt

def export_latest_batch(limit=20):
    """Fetches the latest matches, exports them individually, and creates a Master Digest."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Grab the player name and make it folder-safe
    safe_player_name = config.GAME_NAME.replace(" ", "_")
    batch_folder = os.path.join("exports", f"{safe_player_name}_batch_{timestamp}")
    
    conn = psycopg2.connect(config.DB_URI)
    cursor = conn.cursor()
    cursor.execute("SELECT match_id FROM matches ORDER BY match_id DESC LIMIT %s;", (limit,))
    recent_matches = cursor.fetchall()
    cursor.close()
    conn.close()

    if not recent_matches:
        print("[-] No matches found in the database to export.")
        return

    os.makedirs(batch_folder, exist_ok=True)
    print(f"\n[*] Starting export run: {batch_folder}")
    
    # 1. Initialize the Master Digest Content
    master_digest = f"# League of Legends Match History Analysis\n"
    master_digest += f"**Target Player:** {config.GAME_NAME}#{config.TAG_LINE}\n"
    master_digest += f"**Total Matches Provided:** {len(recent_matches)}\n\n"
    master_digest += "---\n\n"
    master_digest += "### System Instructions for the AI:\n"
    master_digest += "1. Analyze the timeline data across all provided matches.\n"
    master_digest += "2. Identify patterns that correlate with the Target Player winning or losing.\n"
    master_digest += "3. Look for 'turning points' (e.g., massive swings in gold differential or objective control).\n"
    master_digest += "4. Format your output as a data analyst report, highlighting key win-conditions and fail-states.\n\n"
    master_digest += "---\n\n"

    success_count = 0
    for index, (match_id,) in enumerate(recent_matches):
        prompt_text = get_match_as_text(match_id)
        
        if not prompt_text.startswith("Match") and not prompt_text.startswith("Database error"):
            # A. Save individual file (Optional, but good for backup)
            file_path = os.path.join(batch_folder, f"{match_id}.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(prompt_text)
            
            # B. Append to Master Digest
            master_digest += f"## GAME {index + 1}\n"
            master_digest += prompt_text + "\n"
            master_digest += "---\n\n"
            
            success_count += 1
            print(f"  [+] Processed: {match_id}")
        else:
            print(f"  [-] Failed: {match_id} - {prompt_text}")

    # 2. Save the Master Digest File
    digest_path = os.path.join(batch_folder, "MASTER_DIGEST_PROMPT.txt")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(master_digest)

    print("-" * 40)
    print(f"[DONE] Exported {success_count} matches.")
    print(f"[TIP] Feed '{digest_path}' into the AI for the best analysis!")

if __name__ == "__main__":
    # Change limit to 10 if you want to test a smaller batch first
    export_latest_batch(limit=20)