"""
Match Extractor — supports both raw Riot API and ignacarious export format
===========================================================================
Detects format automatically from the JSON structure.

Raw Riot API format (from fetch_matches.py):
  Pairs of {match_id}_match.json + {match_id}_timeline.json

ignacarious export format:
  Single {match_id}.json per match

Usage:
  python extract_matches.py --dir ./raw_matches --puuid YOUR_PUUID --out output.csv

  --puuid is required for raw Riot API format (to identify you in the match).
  It is ignored for the ignacarious export format.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# ── Riot API format helpers ──────────────────────────────────────────────────

def find_participant(match_data: dict, puuid: str) -> tuple[int, dict]:
    for p in match_data["info"]["participants"]:
        if p["puuid"] == puuid:
            return p["participantId"], p
    raise ValueError(f"PUUID not found in {match_data['metadata']['matchId']}")


def get_opponent_pid(match_data: dict, pid: int) -> int | None:
    participants = match_data["info"]["participants"]
    target = next(p for p in participants if p["participantId"] == pid)
    pos = target.get("teamPosition", "")
    team = target.get("teamId")
    if not pos:
        return None
    for p in participants:
        if p["participantId"] != pid and p.get("teamPosition") == pos and p.get("teamId") != team:
            return p["participantId"]
    return None


def participant_frame(frames: list, minute: int, pid: int) -> dict:
    idx = min(minute, len(frames) - 1)
    return frames[idx].get("participantFrames", {}).get(str(pid), {})


def all_events(frames: list) -> list:
    events = []
    for f in frames:
        events.extend(f.get("events", []))
    return events


def ms_to_min(ms: int) -> float:
    return round(ms / 60_000, 2)


def extract_riot_format(match_path: Path, timeline_path: Path, puuid: str) -> dict | None:
    try:
        with open(match_path, encoding="utf-8") as f:
            match_data = json.load(f)
        with open(timeline_path, encoding="utf-8") as f:
            tl = json.load(f)
    except Exception as e:
        print(f"  [skip] {match_path.name}: {e}")
        return None

    match_id = match_data["metadata"]["matchId"]
    duration_s = match_data["info"].get("gameDuration", 0)

    if duration_s < 180:
        print(f"  [skip] {match_id}: {duration_s}s — too short (remake)")
        return None

    try:
        pid, participant = find_participant(match_data, puuid)
    except ValueError as e:
        print(f"  [skip] {e}")
        return None

    frames = tl["info"]["frames"]
    events = all_events(frames)
    opponent_pid = get_opponent_pid(match_data, pid)
    team_id = participant["teamId"]

    def lane_diff(minute: int, field: str):
        my = participant_frame(frames, minute, pid).get(field, 0)
        if opponent_pid:
            opp = participant_frame(frames, minute, opponent_pid).get(field, 0)
            return my - opp
        return None

    def level_diff(minute: int):
        my = participant_frame(frames, minute, pid).get("level")
        if opponent_pid:
            opp = participant_frame(frames, minute, opponent_pid).get("level")
            if my and opp:
                return my - opp
        return None

    ally_pids = [p["participantId"] for p in match_data["info"]["participants"] if p["teamId"] == team_id]
    enemy_pids = [p["participantId"] for p in match_data["info"]["participants"] if p["teamId"] != team_id]

    def team_gold(minute: int, pids: list) -> int:
        return sum(participant_frame(frames, minute, p).get("totalGold", 0) for p in pids)

    # Kill events
    kills_ev = [e for e in events if e.get("type") == "CHAMPION_KILL"]
    first_death_min, first_kill_min = None, None
    for e in sorted(kills_ev, key=lambda x: x.get("timestamp", 0)):
        ts = e.get("timestamp", 0)
        if e.get("victimId") == pid and first_death_min is None:
            first_death_min = ms_to_min(ts)
        if e.get("killerId") == pid and first_kill_min is None:
            first_kill_min = ms_to_min(ts)

    # Item sequence
    item_ev = sorted(
        [e for e in events if e.get("type") == "ITEM_PURCHASED" and e.get("participantId") == pid],
        key=lambda x: x.get("timestamp", 0)
    )
    items = [e["itemId"] for e in item_ev]

    # Objectives
    dragon_ev = [e for e in events if e.get("type") == "ELITE_MONSTER_KILL" and e.get("monsterType") == "DRAGON"]
    dragon_secured = None
    if dragon_ev:
        first = min(dragon_ev, key=lambda x: x.get("timestamp", 0))
        if "killerTeamId" in first:
            dragon_secured = first["killerTeamId"] == team_id
        else:
            dragon_secured = first.get("killerId") in ally_pids

    tower_ev = [e for e in events if e.get("type") == "BUILDING_KILL" and e.get("buildingType") == "TOWER_BUILDING"]
    first_tower_min = ms_to_min(min(tower_ev, key=lambda x: x["timestamp"])["timestamp"]) if tower_ev else None

    team_dragons = sum(1 for e in dragon_ev if (e.get("killerTeamId") == team_id or e.get("killerId") in ally_pids))
    enemy_dragons = len(dragon_ev) - team_dragons

    k = participant.get("kills", 0)
    de = participant.get("deaths", 0)
    a = participant.get("assists", 0)

    return {
        "match_id": match_id,
        "patch": match_data["info"].get("gameVersion", ""),
        "result": "WIN" if participant.get("win") else "LOSS",
        "role": participant.get("role"),
        "position": participant.get("teamPosition"),
        "player_side": "blue" if team_id == 100 else "red",
        "game_duration_minutes": round(duration_s / 60, 1),
        "gold_diff_at_10": lane_diff(10, "totalGold"),
        "cs_diff_at_10": lane_diff(10, "minionsKilled"),
        "xp_diff_at_10": lane_diff(10, "xp"),
        "level_diff_at_10": level_diff(10),
        "dmg_diff_at_10": None,
        "team_gold_diff_at_10": team_gold(10, ally_pids) - team_gold(10, enemy_pids),
        "kda_at_10": None,
        "gold_diff_at_15": lane_diff(15, "totalGold"),
        "cs_diff_at_15": lane_diff(15, "minionsKilled"),
        "xp_diff_at_15": lane_diff(15, "xp"),
        "level_diff_at_15": level_diff(15),
        "dmg_diff_at_15": None,
        "team_gold_diff_at_15": team_gold(15, ally_pids) - team_gold(15, enemy_pids),
        "kda_at_15": None,
        "kills": k,
        "deaths": de,
        "assists": a,
        "kda": round((k + a) / max(de, 1), 2),
        "first_death_minute": first_death_min,
        "first_kill_minute": first_kill_min,
        "items_purchased": "|".join(str(i) for i in items),
        "first_item": items[0] if len(items) > 0 else None,
        "second_item": items[1] if len(items) > 1 else None,
        "third_item": items[2] if len(items) > 2 else None,
        "dragon_secured": dragon_secured,
        "first_tower_minute": first_tower_min,
        "team_dragons": team_dragons,
        "enemy_dragons": enemy_dragons,
        "dragon_diff": team_dragons - enemy_dragons,
        "team_towers": None,
        "enemy_towers": None,
        "tower_diff": None,
        "team_barons": None,
        "enemy_barons": None,
    }


# ── ignacarious export format helpers ────────────────────────────────────────

def get_snapshot(snapshots: list, minute: int) -> dict | None:
    for s in snapshots:
        if s.get("minute") == minute:
            return s
    return None


def extract_export_format(filepath: Path) -> dict | None:
    try:
        with open(filepath, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        print(f"  [skip] {filepath.name}: {e}")
        return None

    match_id = d.get("match_id", filepath.stem)
    duration_s = d.get("duration_seconds", 0)
    snapshots = d.get("snapshots", [])
    objectives = d.get("objectives", {})

    if duration_s < 180:
        print(f"  [skip] {match_id}: {duration_s}s — too short")
        return None

    snap10 = get_snapshot(snapshots, 10)
    if snap10 is None:
        print(f"  [skip] {match_id}: no minute-10 snapshot")
        return None

    snap15 = get_snapshot(snapshots, 15)

    def micro(snap, field):
        return snap.get("micro", {}).get(field) if snap else None

    def macro(snap, field):
        return snap.get("macro", {}).get(field) if snap else None

    last_snap = snapshots[-1] if snapshots else {}
    kda_raw = last_snap.get("kda", "0/0/0")
    try:
        k, de, a = [int(x) for x in kda_raw.split("/")]
        kda = round((k + a) / max(de, 1), 2)
    except Exception:
        k, de, a, kda = 0, 0, 0, 0.0

    team_obj = objectives.get("team", {})
    enemy_obj = objectives.get("enemy", {})

    return {
        "match_id": match_id,
        "patch": d.get("patch"),
        "result": d.get("result"),
        "role": d.get("role"),
        "position": None,
        "player_side": d.get("player_side"),
        "game_duration_minutes": round(duration_s / 60, 1),
        "gold_diff_at_10": micro(snap10, "gold_diff"),
        "cs_diff_at_10": micro(snap10, "cs_diff"),
        "xp_diff_at_10": micro(snap10, "xp_diff"),
        "level_diff_at_10": micro(snap10, "level_diff"),
        "dmg_diff_at_10": micro(snap10, "dmg_diff"),
        "team_gold_diff_at_10": macro(snap10, "team_gold_diff"),
        "kda_at_10": snap10.get("kda"),
        "gold_diff_at_15": micro(snap15, "gold_diff"),
        "cs_diff_at_15": micro(snap15, "cs_diff"),
        "xp_diff_at_15": micro(snap15, "xp_diff"),
        "level_diff_at_15": micro(snap15, "level_diff"),
        "dmg_diff_at_15": micro(snap15, "dmg_diff"),
        "team_gold_diff_at_15": macro(snap15, "team_gold_diff"),
        "kda_at_15": snap15.get("kda") if snap15 else None,
        "kills": k,
        "deaths": de,
        "assists": a,
        "kda": kda,
        "first_death_minute": None,
        "first_kill_minute": None,
        "items_purchased": None,
        "first_item": None,
        "second_item": None,
        "third_item": None,
        "dragon_secured": None,
        "first_tower_minute": None,
        "team_dragons": team_obj.get("dragons"),
        "enemy_dragons": enemy_obj.get("dragons"),
        "dragon_diff": team_obj.get("dragons", 0) - enemy_obj.get("dragons", 0),
        "team_towers": team_obj.get("towers"),
        "enemy_towers": enemy_obj.get("towers"),
        "tower_diff": team_obj.get("towers", 0) - enemy_obj.get("towers", 0),
        "team_barons": team_obj.get("barons"),
        "enemy_barons": enemy_obj.get("barons"),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def detect_format(folder: Path) -> str:
    """Return 'riot' if folder has _match.json/_timeline.json pairs, else 'export'."""
    if any(folder.glob("*_match.json")):
        return "riot"
    return "export"


def main():
    parser = argparse.ArgumentParser(description="Extract match JSONs to CSV")
    parser.add_argument("--dir", required=True, help="Folder with match JSON files")
    parser.add_argument("--puuid", default=None, help="Your PUUID (required for raw Riot API format)")
    parser.add_argument("--out", default="extracted_matches.csv", help="Output CSV path")
    args = parser.parse_args()

    folder = Path(args.dir)
    if not folder.exists():
        print(f"Error: folder not found: {args.dir}")
        sys.exit(1)

    fmt = detect_format(folder)
    print(f"Detected format: {'Raw Riot API' if fmt == 'riot' else 'ignacarious export'}\n")

    if fmt == "riot" and not args.puuid:
        print("Error: --puuid is required for raw Riot API format.")
        sys.exit(1)

    rows = []

    if fmt == "riot":
        match_files = sorted(folder.glob("*_match.json"))
        print(f"Found {len(match_files)} match files...\n")
        for mf in match_files:
            stem = mf.stem.replace("_match", "")
            tf = folder / f"{stem}_timeline.json"
            if not tf.exists():
                print(f"  [skip] No timeline for {mf.name}")
                continue
            print(f"  Processing {stem}...")
            row = extract_riot_format(mf, tf, args.puuid)
            if row:
                rows.append(row)
    else:
        files = sorted(folder.glob("*.json"))
        print(f"Found {len(files)} match files...\n")
        for fp in files:
            print(f"  Processing {fp.name}...")
            row = extract_export_format(fp)
            if row:
                rows.append(row)

    if not rows:
        print("\nNo matches extracted.")
        sys.exit(1)

    out_path = Path(args.out)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    wins = sum(1 for r in rows if r["result"] == "WIN")
    print(f"\nDone. {len(rows)} matches ({wins}W / {len(rows)-wins}L) → {out_path}")


if __name__ == "__main__":
    main()
