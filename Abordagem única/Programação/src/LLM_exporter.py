import psycopg2
import config
import os
import json
import statistics
from datetime import datetime


def preaggregate_matches(matches: list) -> dict:
    """Computes cross-match statistics in Python, keeping AI input minimal."""

    def safe_mean(values):
        values = [v for v in values if v is not None]
        return round(statistics.mean(values), 1) if values else None

    def safe_stdev(values):
        values = [v for v in values if v is not None]
        return round(statistics.stdev(values), 1) if len(values) >= 2 else None

    def get_snapshot(match, phase):
        return next((s for s in match["snapshots"] if s["phase"] == phase), None)

    wins  = [m for m in matches if m["result"] == "WIN"]
    losses= [m for m in matches if m["result"] == "LOSS"]

    # --- Laning phase arrays ---
    def extract(matches, phase, field):
        return [get_snapshot(m, phase)["micro"][field]
                for m in matches if get_snapshot(m, phase)]

    gold_at_10_all   = extract(matches, "early_game",          "gold_diff")
    cs_at_10_all     = extract(matches, "early_game",          "cs_diff")
    level_at_10_all  = extract(matches, "early_game",          "level_diff")
    gold_at_15_all   = extract(matches, "mid_game_transition", "gold_diff")
    team_at_15_all   = [get_snapshot(m, "mid_game_transition")["macro"]["team_gold_diff"]
                        for m in matches if get_snapshot(m, "mid_game_transition")]

    gold_at_10_wins  = extract(wins,   "early_game", "gold_diff")
    gold_at_10_loss  = extract(losses, "early_game", "gold_diff")

    # --- First death timing from events ---
    first_deaths = []
    for m in matches:
        death_events = [e for e in m["events"]
                        if e["type"] == "CHAMPION_KILL" and e["participant"] == "player"]
        # We don't have victim info in events — use snapshot KDA delta as proxy
        snap_10 = get_snapshot(m, "early_game")
        if snap_10:
            kda = snap_10["kda"].split("/")
            if len(kda) == 3 and int(kda[1]) > 0:
                first_deaths.append(10)  # died before or at min 10
            else:
                snap_f = get_snapshot(m, "final_state")
                if snap_f and int(snap_f["kda"].split("/")[1]) > 0:
                    first_deaths.append(15)  # survived laning, died later

    # --- Win correlation for team gold at 15 ---
    if len(team_at_15_all) == len(matches) and len(matches) >= 3:
        win_binary = [1 if m["result"] == "WIN" else 0 for m in matches]
        mean_t = safe_mean(team_at_15_all)
        mean_w = safe_mean(win_binary)
        cov = safe_mean([(t - mean_t) * (w - mean_w)
                         for t, w in zip(team_at_15_all, win_binary)])
        std_t = safe_stdev(team_at_15_all)
        std_w = safe_stdev(win_binary)
        win_corr = round(cov / (std_t * std_w), 2) if std_t and std_w else None
    else:
        win_corr = None

    # --- Outlier detection (>2 std from player's own mean) ---
    outliers = []
    mean_gold = safe_mean(gold_at_10_all)
    std_gold  = safe_stdev(gold_at_10_all)
    if mean_gold is not None and std_gold and std_gold > 0:
        for m in matches:
            snap = get_snapshot(m, "early_game")
            if not snap: continue
            z = (snap["micro"]["gold_diff"] - mean_gold) / std_gold
            if abs(z) > 2:
                outliers.append({
                    "match_id": m["match_id"],
                    "gold_diff_at_10": snap["micro"]["gold_diff"],
                    "z_score": round(z, 2),
                    "result": m["result"]
                })

    # --- Item spike events (count occurrences per item ID near kill events) ---
    item_kill_correlations = {}
    for m in matches:
        kill_minutes = {e["minute"] for e in m["events"]
                        if e["type"] == "CHAMPION_KILL" and e["participant"] == "player"}
        for e in m["events"]:
            if e["type"] == "ITEM_PURCHASED" and e["participant"] == "player":
                item_id = e["value"]
                nearby_kill = any(abs(e["minute"] - k) <= 2 for k in kill_minutes)
                if item_id not in item_kill_correlations:
                    item_kill_correlations[item_id] = {"purchases": 0, "near_kills": 0}
                item_kill_correlations[item_id]["purchases"] += 1
                if nearby_kill:
                    item_kill_correlations[item_id]["near_kills"] += 1

    return {
        "sample_size": len(matches),
        "win_rate": round(len(wins) / len(matches), 2) if matches else 0,
        "laning_phase": {
            "gold_diff_at_10":  {"mean": safe_mean(gold_at_10_all),  "stdev": safe_stdev(gold_at_10_all),
                                 "mean_wins": safe_mean(gold_at_10_wins), "mean_losses": safe_mean(gold_at_10_loss)},
            "cs_diff_at_10":    {"mean": safe_mean(cs_at_10_all),    "stdev": safe_stdev(cs_at_10_all)},
            "level_diff_at_10": {"mean": safe_mean(level_at_10_all), "stdev": safe_stdev(level_at_10_all)},
            "gold_diff_at_15":  {"mean": safe_mean(gold_at_15_all),  "stdev": safe_stdev(gold_at_15_all)},
        },
        "macro": {
            "team_gold_diff_at_15": {"mean": safe_mean(team_at_15_all), "win_correlation": win_corr}
        },
        "outliers": outliers,
        "item_kill_proximity": item_kill_correlations,
        "first_death_proxy": {
            "died_by_min_10_count": first_deaths.count(10),
            "died_after_min_10_count": first_deaths.count(15)
        }
    }


def compress_match(m: dict) -> list:
    """
    Converts a match dict to a minimal positional array.
    Schema (defined once in prompt):
    [match_id, result, duration_sec, role,
     [min, gold_diff, xp_diff, cs_diff, level_diff, dmg_diff, team_gold_diff, kda], ...snapshots,
     [[minute, type, value, participant], ...events]]
    """
    snapshots = [
        [s["minute"],
         s["micro"]["gold_diff"],
         s["micro"]["xp_diff"],
         s["micro"]["cs_diff"],
         s["micro"]["level_diff"],
         s["micro"]["dmg_diff"],
         s["macro"]["team_gold_diff"],
         s["kda"]]
        for s in m["snapshots"]
    ]
    events = [
        [e["minute"], e["type"], e["value"], e["participant"]]
        for e in m["events"]
    ]
    return [m["match_id"], m["result"], m["duration_seconds"], m["role"],
            snapshots, events]


def build_digest(game_name, tag_line, matches: list) -> str:
    aggregated = preaggregate_matches(matches)
    compressed = [compress_match(m) for m in matches]

    prompt = f"""You are a quantitative performance analyst reviewing League of Legends data for a researcher. You have no reliable meta knowledge — flag domain inferences as hypotheses explicitly.

## Compressed Data Schema
Each match is a positional array:
[match_id, result, duration_sec, role, snapshots, events]

Snapshots: [minute, gold_diff, xp_diff, cs_diff, level_diff, dmg_diff, team_gold_diff, kda]
  - All diff values: player minus direct lane opponent. Positive = player ahead.
  - team_gold_diff: player_team minus enemy_team total gold.

Events: [minute, type, value, participant]
  - Types: ITEM_PURCHASED, LEVEL_UP, ELITE_MONSTER_KILL, BUILDING_KILL, CHAMPION_KILL
  - participant: "player" | "enemy" | "team" | "enemy_team"
  - ITEM_PURCHASED value = item ID (integer, do not interpret)

## Pre-Aggregated Statistics
Python has already computed the following. Use these as your numerical foundation — do not recompute from raw match data.

{json.dumps(aggregated, indent=2)}

## Raw Match Data (compressed)
Use only to identify outlier game details or event-level patterns not captured above.

{json.dumps(compressed)}

## Analytical Task
Identify trends across matches, not within them. A trend requires at least 3 matches showing the same directional pattern to be reportable.

## Strict Rules
1. Never infer causality. Use "correlates with" not "causes"
2. Never interpret item IDs — report them as numbers only
3. Flag conclusions from fewer than 5 matches as low confidence
4. Only reference individual games if they appear in pre-aggregated outliers
5. Be terse. No preamble, no closing remarks, no restating the question
6. Output the JSON block only. Use null for fields with insufficient data

## Output — JSON only

{{
  "sample_size": <int>,
  "win_rate": <float>,
  "laning_phase": {{
    "gold_diff_at_10":  {{"mean": <float>, "trend": "improving|declining|stable", "confidence": "low|medium|high"}},
    "cs_diff_at_10":    {{"mean": <float>, "trend": "improving|declining|stable", "confidence": "low|medium|high"}},
    "level_diff_at_10": {{"mean": <float>, "trend": "improving|declining|stable", "confidence": "low|medium|high"}},
    "first_death_timing": {{"mean_minute": <float>, "note": "<hypothesis if inferential>"}}
  }},
  "power_spike_patterns": [
    {{"observation": "<str>", "confidence": "low|medium|high", "supporting_games": <int>}}
  ],
  "macro_patterns": {{
    "team_gold_diff_at_15": {{"mean": <float>, "win_correlation": <float>}},
    "objective_control": "<str or null>",
    "tower_timing": "<str or null>"
  }},
  "outlier_games": [
    {{"match_id": "<str>", "reason": "<str>", "direction": "positive|negative"}}
  ],
  "hypotheses": ["<str>"],
  "data_flags": ["<str>"]
}}
"""
    return prompt


# --- Unchanged below this line ---

def get_match_as_dict(match_id):
    conn = psycopg2.connect(config.DB_URI)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT game_version, game_duration_sec, role, target_player_won, target_player_team_id,
               blue_dragons, red_dragons, blue_barons, red_barons, blue_towers, red_towers
        FROM matches WHERE match_id = %s;
    """, (match_id,))
    summary = cursor.fetchone()
    if not summary:
        cursor.close(); conn.close()
        return None

    version, duration, role, won, team_id, b_drags, r_drags, b_barons, r_barons, b_towers, r_towers = summary

    cursor.execute("""
        SELECT game_minute,
               team_100_gold, team_200_gold,
               player_gold, enemy_gold,
               player_xp, enemy_xp,
               player_cs, enemy_cs,
               player_level, enemy_level,
               player_current_gold,
               player_dmg, enemy_dmg,
               player_pos_x, player_pos_y,
               player_kills, player_deaths, player_assists
        FROM match_timeline
        WHERE match_id = %s
          AND (game_minute IN (10, 15)
           OR game_minute = (SELECT MAX(game_minute) FROM match_timeline WHERE match_id = %s))
        ORDER BY game_minute;
    """, (match_id, match_id))
    milestones = cursor.fetchall()

    cursor.execute("""
        SELECT minute, event_type, value, participant
        FROM match_events WHERE match_id = %s ORDER BY minute;
    """, (match_id,))
    events = cursor.fetchall()

    cursor.close()
    conn.close()

    snapshots = []
    for row in milestones:
        (minute, b_gold, r_gold, p_gold, e_gold, p_xp, e_xp,
         p_cs, e_cs, p_level, e_level, p_current_gold,
         p_dmg, e_dmg, p_pos_x, p_pos_y, kills, deaths, assists) = row

        team_gold = b_gold if team_id == 100 else r_gold
        enemy_gold_team = r_gold if team_id == 100 else b_gold

        phase = ("early_game"          if minute == 10 else
                 "mid_game_transition" if minute == 15 else
                 "final_state")

        snapshots.append({
            "minute": minute, "phase": phase,
            "micro": {
                "gold_diff":  (p_gold  or 0) - (e_gold  or 0),
                "xp_diff":    (p_xp    or 0) - (e_xp    or 0),
                "cs_diff":    (p_cs    or 0) - (e_cs    or 0),
                "level_diff": (p_level or 0) - (e_level or 0),
                "dmg_diff":   (p_dmg   or 0) - (e_dmg   or 0),
                "player_current_gold": p_current_gold,
                "player_position": {"x": p_pos_x, "y": p_pos_y} if p_pos_x else None
            },
            "macro": {"team_gold_diff": team_gold - enemy_gold_team},
            "kda": f"{kills}/{deaths}/{assists}"
        })

    return {
        "match_id": match_id, "patch": version,
        "duration_seconds": duration, "role": role,
        "result": "WIN" if won else "LOSS",
        "player_side": "blue" if team_id == 100 else "red",
        "objectives": {
            "team":  {"towers": b_towers if team_id == 100 else r_towers,
                      "dragons": b_drags if team_id == 100 else r_drags,
                      "barons": b_barons if team_id == 100 else r_barons},
            "enemy": {"towers": r_towers if team_id == 100 else b_towers,
                      "dragons": r_drags if team_id == 100 else b_drags,
                      "barons": r_barons if team_id == 100 else b_barons}
        },
        "snapshots": snapshots,
        "events": [{"minute": e[0], "type": e[1], "value": e[2], "participant": e[3]} for e in events]
    }


def export_latest_batch(limit=50):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = config.GAME_NAME.replace(" ", "_")
    batch_folder = os.path.join("exports", f"{safe_name}_batch_{timestamp}")

    conn = psycopg2.connect(config.DB_URI)
    cursor = conn.cursor()
    cursor.execute("SELECT match_id FROM matches ORDER BY match_id DESC LIMIT %s;", (limit,))
    recent_matches = cursor.fetchall()
    cursor.close()
    conn.close()

    if not recent_matches:
        print("[-] No matches found.")
        return

    os.makedirs(batch_folder, exist_ok=True)
    matches_payload = []

    for match_id, in recent_matches:
        data = get_match_as_dict(match_id)
        if data:
            matches_payload.append(data)
            with open(os.path.join(batch_folder, f"{match_id}.json"), "w") as f:
                json.dump(data, f, indent=2)
            print(f"  [+] {match_id}")
        else:
            print(f"  [-] {match_id} — not found")

    digest = build_digest(config.GAME_NAME, config.TAG_LINE, matches_payload)
    digest_path = os.path.join(batch_folder, "MASTER_DIGEST_PROMPT.txt")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(digest)

    print(f"\n[DONE] {len(matches_payload)} matches → {digest_path}")


if __name__ == "__main__":
    export_latest_batch(limit=50)