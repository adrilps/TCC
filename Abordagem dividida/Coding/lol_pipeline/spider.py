"""
data/spider.py — BFS match collector using the Riot Games API.

Strategy: breadth-first search starting from a seed player.
  1. Resolve seed Riot ID → PUUID
  2. Fetch their recent ranked solo mid-lane matches
  3. For each match, extract the mid-laner's phase stats → save to cache
  4. Enqueue all 10 players from that match as new BFS seeds
  5. Repeat until MAX_MATCHES or MAX_PLAYERS_VISITED is reached

Rate limiting: Riot dev key = 100 requests / 2 min.
  We track every request timestamp and sleep when approaching the limit.

Caching: every API response is saved as a JSON file keyed by its URL.
  Restarting the spider resumes from where it left off — no re-fetching.

To run:
  export RIOT_API_KEY=your_key_here
  python -m lol_pipeline.data.spider
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
import hashlib
import logging
from collections import deque
from pathlib import Path

import requests
import pandas as pd

from config import (
    REGION, REGION_ROUTING, SEED_RIOT_ID, QUEUE_ID,
    TARGET_ROLE, TARGET_TIERS, MATCHES_PER_PLAYER,
    MAX_MATCHES, MAX_PLAYERS_VISITED,
    RATE_LIMIT_CALLS, RATE_LIMIT_WINDOW,
    CACHE_DIR, EARLY_END_MIN, MID_END_MIN,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ── Cache ─────────────────────────────────────────────────────────────────────

class Cache:
    """
    Simple file-based cache. Each URL maps to a JSON file on disk.
    This means a crashed/interrupted spider resumes instantly with no lost work.
    """
    def __init__(self, directory: str = CACHE_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, url: str) -> Path:
        h = hashlib.md5(url.encode()).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, url: str):
        path = self._key(url)
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def set(self, url: str, data):
        with open(self._key(url), "w") as f:
            json.dump(data, f)


# ── Rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Tracks request timestamps and sleeps when approaching the Riot rate limit.
    Conservative by design — better to wait a second than get a 429.
    """
    def __init__(self, max_calls: int = RATE_LIMIT_CALLS, window: int = RATE_LIMIT_WINDOW):
        self.max_calls = max_calls
        self.window = window
        self.timestamps = []

    def wait(self):
        now = time.time()
        # Drop timestamps outside the current window
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.max_calls:
            sleep_for = self.window - (now - self.timestamps[0]) + 1
            log.info(f"  Rate limit approaching — sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        self.timestamps.append(time.time())


# ── API client ────────────────────────────────────────────────────────────────

class RiotClient:
    """
    Thin wrapper around requests that handles auth headers,
    caching, rate limiting, and retries on 429/503.
    """
    def __init__(self, api_key: str, cache: Cache, limiter: RateLimiter):
        self.headers = {"X-Riot-Token": api_key}
        self.cache = cache
        self.limiter = limiter

    def get(self, url: str) -> dict | None:
        # Try cache first — no API call needed
        cached = self.cache.get(url)
        if cached is not None:
            return cached

        self.limiter.wait()
        for attempt in range(3):
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.cache.set(url, data)
                return data
            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                log.warning(f"  429 received — sleeping {retry_after}s")
                time.sleep(retry_after)
            elif resp.status_code == 404:
                return None  # Player not found, skip silently
            else:
                log.warning(f"  HTTP {resp.status_code} on attempt {attempt+1}: {url}")
                time.sleep(2)
        return None

    # ── Endpoint helpers ──────────────────────────────────────────────────────

    def get_puuid(self, game_name: str, tag_line: str) -> str | None:
        url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        data = self.get(url)
        return data["puuid"] if data else None

    def get_rank(self, puuid: str) -> str | None:
        url = f"https://{REGION}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        entries = self.get(url)
        if not entries:
            return None
        for entry in entries:
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                return entry.get("tier")
        return None

    def get_summoner_id(self, puuid: str) -> str | None:
        # Summoner ID no longer returned — use PUUID directly for rank lookup
        return puuid

    def get_match_ids(self, puuid: str, count: int = MATCHES_PER_PLAYER) -> list[str]:
        url = (
            f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid"
            f"/{puuid}/ids?queue={QUEUE_ID}&count={count}"
        )
        data = self.get(url)
        return data if data else []

    def get_match_timeline(self, match_id: str) -> dict | None:
        url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        return self.get(url)

    def get_match_info(self, match_id: str) -> dict | None:
        url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self.get(url)


# ── Feature extraction ────────────────────────────────────────────────────────

def extract_features(match_info: dict, timeline: dict, target_puuid: str) -> dict | None:
    """
    Given a match and its timeline, extract phase-aggregated features
    for the mid-laner identified by target_puuid.

    Returns a feature dict ready to become a DataFrame row, or None if
    the player wasn't playing mid in this match.

    The "diff" features are always from the perspective of the target player's team:
      positive = target team is ahead, negative = target team is behind.
    """
    try:
        participants = match_info["info"]["participants"]

        # Find our player and confirm they played mid
        target = next((p for p in participants if p["puuid"] == target_puuid), None)
        if not target or target.get("teamPosition") != TARGET_ROLE:
            return None

        target_id = target["participantId"]          # 1–10
        target_team = target["teamId"]               # 100 (blue) or 200 (red)
        win = int(target["win"])

        # Build participant lookup: id → teamId
        team_of = {p["participantId"]: p["teamId"] for p in participants}

        # Accumulate per-minute frame stats
        frames = timeline["info"]["frames"]

        # We'll accumulate totals per phase window for the target player's team vs enemy
        def empty_phase():
            return {
                "gold_diff": 0, "cs_diff": 0, "xp_diff": 0,
                "kills": 0, "deaths": 0,
                "tower_kills": 0, "tower_deaths": 0,
                "dragon": 0, "herald": 0, "baron": 0,
                "vision_diff": 0,
                "frame_count": 0,
            }

        early, mid, late = empty_phase(), empty_phase(), empty_phase()

        def phase_for(minute: int):
            if minute <= EARLY_END_MIN:
                return early
            elif minute <= MID_END_MIN:
                return mid
            else:
                return late

        for frame in frames:
            minute = frame["timestamp"] // 60000
            phase = phase_for(minute)
            phase["frame_count"] += 1

            pf = frame.get("participantFrames", {})

            # Gold, CS, XP diffs (target player vs their lane opponent)
            # Lane opponent = same participantId offset on other team
            # Simpler: compare target to average of enemy team mid (not available directly),
            # so we use target vs their direct counterpart by position
            target_frame = pf.get(str(target_id), {})
            target_stats = target_frame.get("totalGold", 0), target_frame.get("minionsKilled", 0) + target_frame.get("jungleMinionsKilled", 0), target_frame.get("xp", 0)

            # Enemy team aggregate for normalisation
            enemy_ids = [pid for pid, tid in team_of.items() if tid != target_team]
            ally_ids  = [pid for pid, tid in team_of.items() if tid == target_team and pid != target_id]

            enemy_gold = sum(pf.get(str(pid), {}).get("totalGold", 0) for pid in enemy_ids)
            ally_gold  = sum(pf.get(str(pid), {}).get("totalGold", 0) for pid in ally_ids)
            team_gold  = target_stats[0] + ally_gold

            phase["gold_diff"] += team_gold - enemy_gold
            phase["cs_diff"]   += target_stats[1]  # raw CS for target (diff computed later vs population)
            phase["xp_diff"]   += target_stats[2]

            # Vision score diff (team vs enemy)
            team_vision  = sum(pf.get(str(pid), {}).get("wardScore", 0) for pid in [target_id] + ally_ids)
            enemy_vision = sum(pf.get(str(pid), {}).get("wardScore", 0) for pid in enemy_ids)
            phase["vision_diff"] += team_vision - enemy_vision

        # Events: kills, towers, objectives
        for frame in frames:
            minute = frame["timestamp"] // 60000
            phase = phase_for(minute)
            for event in frame.get("events", []):
                etype = event.get("type")

                if etype == "CHAMPION_KILL":
                    killer_team = team_of.get(event.get("killerId"), 0)
                    if killer_team == target_team:
                        phase["kills"] += 1
                    else:
                        phase["deaths"] += 1

                elif etype == "BUILDING_KILL":
                    killer_team = team_of.get(event.get("killerId"), 0)
                    if killer_team == target_team:
                        phase["tower_kills"] += 1
                    else:
                        phase["tower_deaths"] += 1

                elif etype == "ELITE_MONSTER_KILL":
                    monster = event.get("monsterType", "")
                    killer_team = event.get("killerTeamId", 0)
                    if monster == "DRAGON":
                        phase["dragon"] += int(killer_team == target_team)
                    elif monster == "RIFTHERALD":
                        phase["herald"] += int(killer_team == target_team)
                    elif monster == "BARON_NASHOR":
                        phase["baron"] += int(killer_team == target_team)

        # Normalize accumulated diffs by frame count to get per-minute averages
        def avg(phase, key):
            fc = phase["frame_count"] or 1
            return round(phase[key] / fc, 2)

        row = {
            # Early
            "early_gold_diff":   avg(early, "gold_diff"),
            "early_cs_diff":     avg(early, "cs_diff"),
            "early_xp_diff":     avg(early, "xp_diff"),
            "early_kill_diff":   early["kills"] - early["deaths"],
            "early_first_blood": int(early["kills"] > 0 and early["deaths"] == 0),
            "early_tower_diff":  early["tower_kills"] - early["tower_deaths"],
            "early_dragon":      int(early["dragon"] > 0),
            # Mid
            "mid_gold_diff":     avg(mid, "gold_diff"),
            "mid_cs_diff":       avg(mid, "cs_diff"),
            "mid_kill_diff":     mid["kills"] - mid["deaths"],
            "mid_tower_diff":    mid["tower_kills"] - mid["tower_deaths"],
            "mid_dragon_count":  mid["dragon"],
            "mid_herald":        int(mid["herald"] > 0),
            "mid_vision_diff":   avg(mid, "vision_diff"),
            # Late
            "late_gold_diff":    avg(late, "gold_diff"),
            "late_kill_diff":    late["kills"] - late["deaths"],
            "late_tower_diff":   late["tower_kills"] - late["tower_deaths"],
            "late_baron":        int(late["baron"] > 0),
            "late_dragon_soul":  int((early["dragon"] + mid["dragon"] + late["dragon"]) >= 4),
            "late_vision_diff":  avg(late, "vision_diff"),
            "late_inhibitor_diff": late["tower_kills"] - late["tower_deaths"],  # proxy
            "win": win,
        }
        return row

    except Exception as e:
        log.debug(f"  Feature extraction failed: {e}")
        return None


# ── BFS Spider ────────────────────────────────────────────────────────────────

class Spider:
    def __init__(self, client: RiotClient):
        self.client = client
        self.visited_players: set[str] = set()   # PUUIDs already processed
        self.visited_matches: set[str] = set()   # match IDs already processed
        self.queue: deque[str] = deque()          # BFS queue of PUUIDs
        self.rows: list[dict] = []                # collected feature rows
        self._load_progress()

    def _progress_path(self) -> Path:
        return Path(CACHE_DIR) / "_progress.json"

    def _load_progress(self):
        """Resume a previous run if progress file exists."""
        path = self._progress_path()
        if path.exists():
            with open(path) as f:
                state = json.load(f)
            self.visited_players = set(state["visited_players"])
            self.visited_matches = set(state["visited_matches"])
            self.queue = deque(state["queue"])
            log.info(f"  Resumed: {len(self.visited_matches)} matches, {len(self.visited_players)} players, {len(self.queue)} in queue")

    def _save_progress(self):
        with open(self._progress_path(), "w") as f:
            json.dump({
                "visited_players": list(self.visited_players),
                "visited_matches": list(self.visited_matches),
                "queue": list(self.queue),
            }, f)

    def _is_gold(self, puuid: str) -> bool:
        summoner_id = self.client.get_summoner_id(puuid)
        if not summoner_id:
            return False
        tier = self.client.get_rank(summoner_id)
        return tier in TARGET_TIERS if tier else False

    def run(self, seed_puuid: str) -> pd.DataFrame:
        if seed_puuid not in self.visited_players:
            self.queue.appendleft(seed_puuid)

        log.info(f"Starting BFS | target: {MAX_MATCHES} matches, {MAX_PLAYERS_VISITED} players")

        while self.queue and len(self.visited_matches) < MAX_MATCHES and len(self.visited_players) < MAX_PLAYERS_VISITED:
            puuid = self.queue.popleft()

            if puuid in self.visited_players:
                continue

            # Rank gate — only process Gold players
            if not self._is_gold(puuid):
                log.info(f"  Skipping non-Gold player")
                self.visited_players.add(puuid)
                continue

            self.visited_players.add(puuid)
            match_ids = self.client.get_match_ids(puuid)
            log.info(f"  Player {len(self.visited_players)}/{MAX_PLAYERS_VISITED} | {len(match_ids)} matches | queue size: {len(self.queue)}")

            for match_id in match_ids:
                if match_id in self.visited_matches:
                    continue
                if len(self.visited_matches) >= MAX_MATCHES:
                    break

                self.visited_matches.add(match_id)

                match_info = self.client.get_match_info(match_id)
                timeline   = self.client.get_match_timeline(match_id)

                if not match_info or not timeline:
                    continue

                row = extract_features(match_info, timeline, puuid)
                if row:
                    self.rows.append(row)
                    log.info(f"    ✓ Match {len(self.rows)} collected ({match_id})")

                # Enqueue all 10 players from this match (BFS expansion)
                for p in match_info["info"]["participants"]:
                    new_puuid = p["puuid"]
                    if new_puuid not in self.visited_players:
                        self.queue.append(new_puuid)

            self._save_progress()

        log.info(f"\nDone. Collected {len(self.rows)} mid-lane matches.")
        return pd.DataFrame(self.rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_spider() -> pd.DataFrame:
    api_key = os.getenv("RIOT_API_KEY")
    if not api_key:
        raise EnvironmentError("RIOT_API_KEY environment variable not set.")

    cache   = Cache()
    limiter = RateLimiter()
    client  = RiotClient(api_key, cache, limiter)

    # Resolve seed player
    game_name, tag_line = SEED_RIOT_ID.split("#")
    log.info(f"Resolving seed: {SEED_RIOT_ID}")
    seed_puuid = client.get_puuid(game_name, tag_line)
    if not seed_puuid:
        raise ValueError(f"Could not resolve Riot ID: {SEED_RIOT_ID}")
    log.info(f"Seed PUUID: {seed_puuid}")

    spider = Spider(client)
    df = spider.run(seed_puuid)

    # Save collected data
    out_path = Path(CACHE_DIR) / "matches.csv"
    df.to_csv(out_path, index=False)
    log.info(f"Saved to {out_path}")

    return df


if __name__ == "__main__":
    df = run_spider()
    print(f"\nDataset shape: {df.shape}")
    print(df.head())
