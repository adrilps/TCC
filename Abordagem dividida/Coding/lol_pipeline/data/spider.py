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

import os
import json
import time
import hashlib
import logging
from collections import deque
from pathlib import Path

import requests
import pandas as pd

from lol_pipeline.config import (
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
            elif resp.status_code in (400, 404):
                return None  # Bad/missing resource — skip silently, no retry
            else:
                log.warning(f"  HTTP {resp.status_code} on attempt {attempt+1}: {url}")
                time.sleep(2)
        return None

    # ── Endpoint helpers ──────────────────────────────────────────────────────

    def get_puuid(self, game_name: str, tag_line: str) -> str | None:
        url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        data = self.get(url)
        return data["puuid"] if data else None

    def get_summoner_id(self, puuid: str) -> str | None:
        url = f"https://{REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
        data = self.get(url)
        return data.get("id") if data else None

    def get_rank(self, puuid: str) -> str | None:
        """Returns the tier of a player's ranked solo queue entry, or None."""
        summoner_id = self.get_summoner_id(puuid)
        if not summoner_id:
            return None
        url = f"https://{REGION}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
        entries = self.get(url)
        if not entries:
            return None
        for entry in entries:
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                return entry.get("tier")
        return None

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
    Extract behavioral features for the target mid-laner from a match.

    Phase boundaries are event-driven with time fallbacks:
      Early: match start → first tower kill   (fallback: EARLY_END_MIN minutes)
      Mid:   first tower kill → first Baron   (fallback: MID_END_MIN minutes)
      Late:  first Baron → match end

    All features are computed for target_puuid only, not team aggregates.
    Zero-duration phases (e.g. a 20-min game with no Baron) yield NaN features.

    Returns a feature dict ready to become a DataFrame row, or None if
    the player wasn't playing mid in this match.
    """
    try:
        participants = match_info["info"]["participants"]

        # Find target player and confirm mid lane
        target = next((p for p in participants if p["puuid"] == target_puuid), None)
        if not target or target.get("teamPosition") != TARGET_ROLE:
            return None

        target_id   = target["participantId"]   # 1–10
        target_team = target["teamId"]           # 100 (blue) or 200 (red)
        win         = int(target["win"])
        match_id    = match_info["metadata"]["matchId"]
        game_version = match_info["info"].get("gameVersion", "")
        parts = game_version.split(".")
        patch = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else game_version

        team_of  = {p["participantId"]: p["teamId"] for p in participants}
        team_ids = [pid for pid, tid in team_of.items() if tid == target_team]

        frames = timeline["info"]["frames"]

        # ── Phase boundary detection ──────────────────────────────────────────

        first_tower_ms = None
        first_baron_ms = None

        for frame in frames:
            if first_tower_ms is not None and first_baron_ms is not None:
                break
            for event in frame.get("events", []):
                etype = event.get("type")
                ts    = event.get("timestamp", frame["timestamp"])
                if first_tower_ms is None and etype == "BUILDING_KILL" and event.get("buildingType") == "TOWER_BUILDING":
                    first_tower_ms = ts
                if first_baron_ms is None and etype == "ELITE_MONSTER_KILL" and event.get("monsterType") == "BARON_NASHOR":
                    first_baron_ms = ts

        # Use whichever comes first: the event or the time fallback
        early_end_ms = min(
            first_tower_ms if first_tower_ms is not None else float("inf"),
            EARLY_END_MIN * 60 * 1000,
        )
        mid_end_ms = min(
            first_baron_ms if first_baron_ms is not None else float("inf"),
            MID_END_MIN * 60 * 1000,
        )
        # Guard: Baron before first tower is essentially impossible in SR ranked,
        # but cap mid boundary so it never precedes the early boundary.
        mid_end_ms = max(mid_end_ms, early_end_ms)

        match_end_ms = frames[-1]["timestamp"]

        early_dur_min = early_end_ms / 60_000
        mid_dur_min   = (mid_end_ms - early_end_ms) / 60_000
        late_dur_min  = (match_end_ms - mid_end_ms) / 60_000

        # ── Frame-snapshot helpers ─────────────────────────────────────────────

        def pframe_at(ts_ms: float, pid: int) -> dict:
            """Last participant frame snapshot at or before ts_ms."""
            best: dict = {}
            for frame in frames:
                if frame["timestamp"] <= ts_ms:
                    best = frame["participantFrames"].get(str(pid), {})
                else:
                    break
            return best

        def cs_delta(pid: int, start_ms: float, end_ms: float) -> int:
            def cs(pf): return pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0)
            return cs(pframe_at(end_ms, pid)) - cs(pframe_at(start_ms, pid))

        def damage_delta(pid: int, start_ms: float, end_ms: float) -> float:
            def dmg(pf): return pf.get("damageStats", {}).get("totalDamageDoneToChampions", 0)
            return dmg(pframe_at(end_ms, pid)) - dmg(pframe_at(start_ms, pid))

        # Phase ranges as (start_ms, end_ms) pairs
        phase_ranges = [
            (0,            early_end_ms),
            (early_end_ms, mid_end_ms),
            (mid_end_ms,   match_end_ms),
        ]
        phase_durs = [early_dur_min, mid_dur_min, late_dur_min]

        # ── Snapshot-based per-phase metrics ─────────────────────────────────

        phase_cs  = [cs_delta(target_id, s, e) for s, e in phase_ranges]

        # Damage share: target vs full team (including target) within each phase
        phase_target_dmg = [damage_delta(target_id, s, e) for s, e in phase_ranges]
        phase_team_dmg   = [
            sum(damage_delta(pid, s, e) for pid in team_ids)
            for s, e in phase_ranges
        ]

        # ── Event-based per-phase counters ────────────────────────────────────

        deaths_ph    = [0, 0, 0]
        kp_num_ph    = [0, 0, 0]   # kill-participation numerator
        team_kills_ph= [0, 0, 0]
        solo_kills_ph= [0, 0, 0]
        obj_prox_num = [0, 0, 0]
        obj_prox_den = [0, 0, 0]
        wards_ph     = [0, 0, 0]

        first_blood_involved = 0
        first_blood_found    = False

        def phase_idx(ts_ms: float) -> int:
            if ts_ms < early_end_ms:
                return 0
            elif ts_ms < mid_end_ms:
                return 1
            else:
                return 2

        def target_pos_at(ts_ms: float):
            return pframe_at(ts_ms, target_id).get("position")

        def dist2d(p1: dict, p2: dict) -> float:
            return ((p1["x"] - p2["x"]) ** 2 + (p1["y"] - p2["y"]) ** 2) ** 0.5

        for frame in frames:
            for event in frame.get("events", []):
                ts    = event.get("timestamp", frame["timestamp"])
                etype = event.get("type")
                ph    = phase_idx(ts)

                if etype == "CHAMPION_KILL":
                    killer_id  = event.get("killerId", 0)
                    victim_id  = event.get("victimId", 0)
                    assists    = event.get("assistingParticipantIds") or []
                    killer_team = team_of.get(killer_id, 0)

                    # First blood is match-level; check before any phase filter
                    if not first_blood_found:
                        first_blood_found = True
                        if killer_id == target_id or target_id in assists:
                            first_blood_involved = 1

                    if victim_id == target_id:
                        deaths_ph[ph] += 1

                    if killer_team == target_team:
                        team_kills_ph[ph] += 1
                        if killer_id == target_id or target_id in assists:
                            kp_num_ph[ph] += 1

                    # Solo kill: target is sole killer (no assists)
                    if killer_id == target_id and not assists:
                        solo_kills_ph[ph] += 1

                elif etype == "WARD_PLACED":
                    if event.get("creatorId") == target_id:
                        wards_ph[ph] += 1

                elif etype in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
                    event_pos = event.get("position")
                    if event_pos:
                        t_pos = target_pos_at(ts)
                        if t_pos:
                            obj_prox_den[ph] += 1
                            if dist2d(event_pos, t_pos) <= 2000:
                                obj_prox_num[ph] += 1

        # ── Build output row ──────────────────────────────────────────────────

        NaN = float("nan")

        def per_min(val: float, dur: float) -> float:
            return NaN if dur <= 0 else round(val / dur, 4)

        def ratio(num: float, den: float, zero_den=NaN) -> float:
            return zero_den if den == 0 else round(num / den, 4)

        row: dict = {}
        for i, pname in enumerate(("early", "mid", "late")):
            dur = phase_durs[i]
            row[f"{pname}_cs_per_min"]          = per_min(phase_cs[i], dur)
            row[f"{pname}_vision_per_min"]       = per_min(wards_ph[i], dur)
            row[f"{pname}_deaths_per_min"]       = per_min(deaths_ph[i], dur)
            # Per brief: kill_participation = 0 when team had 0 kills (not NaN)
            row[f"{pname}_kill_participation"]   = (
                NaN if dur <= 0
                else ratio(kp_num_ph[i], team_kills_ph[i], zero_den=0.0)
            )
            row[f"{pname}_damage_share"]         = (
                NaN if dur <= 0
                else ratio(phase_target_dmg[i], phase_team_dmg[i])
            )
            row[f"{pname}_solo_kills"]           = NaN if dur <= 0 else solo_kills_ph[i]
            row[f"{pname}_objective_proximity"]  = (
                NaN if dur <= 0
                else ratio(obj_prox_num[i], obj_prox_den[i])
            )

        row["early_first_blood_involved"] = first_blood_involved
        row["puuid"]              = target_puuid
        row["match_id"]           = match_id
        row["patch"]              = patch
        row["early_duration_min"] = round(early_dur_min, 3)
        row["mid_duration_min"]   = round(mid_dur_min, 3)
        row["late_duration_min"]  = round(late_dur_min, 3)
        row["win"]                = win

        return row

    except Exception as e:
        log.debug(f"  Feature extraction failed: {e}")
        return None


# ── BFS Spider ────────────────────────────────────────────────────────────────

class Spider:
    def __init__(self, client: RiotClient, tiers: set | None = None,
                 max_matches: int = MAX_MATCHES, max_players: int = MAX_PLAYERS_VISITED):
        self.client = client
        self.tiers = tiers if tiers is not None else TARGET_TIERS
        self.max_matches = max_matches
        self.max_players = max_players
        self.visited_players: set[str] = set()
        self.visited_matches: set[str] = set()
        self.queue: deque[str] = deque()
        self.rows: list[dict] = []
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

    def _in_target_tier(self, puuid: str) -> bool:
        tier = self.client.get_rank(puuid)
        return tier in self.tiers if tier else False

    def run(self, seed_puuid: str) -> pd.DataFrame:
        if seed_puuid not in self.visited_players:
            self.queue.appendleft(seed_puuid)

        log.info(f"Starting BFS | target: {self.max_matches} matches, {self.max_players} players")

        while self.queue and len(self.visited_matches) < self.max_matches and len(self.visited_players) < self.max_players:
            puuid = self.queue.popleft()

            if puuid in self.visited_players:
                continue

            if not self._in_target_tier(puuid):
                log.info(f"  Skipping player outside target tier(s)")
                self.visited_players.add(puuid)
                continue

            self.visited_players.add(puuid)
            match_ids = self.client.get_match_ids(puuid)
            log.info(f"  Player {len(self.visited_players)}/{self.max_players} | {len(match_ids)} matches | queue size: {len(self.queue)}")

            for match_id in match_ids:
                if match_id in self.visited_matches:
                    continue
                if len(self.visited_matches) >= self.max_matches:
                    break

                self.visited_matches.add(match_id)

                match_info = self.client.get_match_info(match_id)
                timeline   = self.client.get_match_timeline(match_id)

                if not match_info or not timeline:
                    continue

                row = extract_features(match_info, timeline, puuid)
                if row:
                    self.rows.append(row)
                    log.info(f"    + Match {len(self.rows)} collected ({match_id})")

                # Enqueue all 10 players from this match (BFS expansion)
                for p in match_info["info"]["participants"]:
                    new_puuid = p["puuid"]
                    if new_puuid not in self.visited_players:
                        self.queue.append(new_puuid)

            self._save_progress()

        log.info(f"\nDone. Collected {len(self.rows)} mid-lane matches.")
        return pd.DataFrame(self.rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_spider(
    seed: str | None = None,
    region: str | None = None,
    region_routing: str | None = None,
    tiers: set | None = None,
    max_matches: int | None = None,
    max_players: int | None = None,
    target_patch: str | None = None,
    api_key: str | None = None,
) -> pd.DataFrame:
    api_key = api_key or os.getenv("RIOT_API_KEY")
    if not api_key:
        raise EnvironmentError("RIOT_API_KEY environment variable not set.")

    # Region overrides affect the RiotClient URLs — patch the module-level names
    # used by the client helpers (these are strings, not mutable objects, so we
    # must update the module globals rather than passing them through).
    import lol_pipeline.data.spider as _self
    if region:         _self.REGION         = region
    if region_routing: _self.REGION_ROUTING = region_routing

    cache   = Cache()
    limiter = RateLimiter()
    client  = RiotClient(api_key, cache, limiter)

    seed_riot_id = seed or SEED_RIOT_ID
    game_name, tag_line = seed_riot_id.split("#")
    log.info(f"Resolving seed: {seed_riot_id}")
    seed_puuid = client.get_puuid(game_name, tag_line)
    if not seed_puuid:
        raise ValueError(f"Could not resolve Riot ID: {seed_riot_id}")
    log.info(f"Seed PUUID: {seed_puuid}")

    spider = Spider(
        client,
        tiers=tiers or TARGET_TIERS,
        max_matches=max_matches or MAX_MATCHES,
        max_players=max_players or MAX_PLAYERS_VISITED,
    )
    df = spider.run(seed_puuid)

    if target_patch and "patch" in df.columns:
        before = len(df)
        df = df[df["patch"] == target_patch].reset_index(drop=True)
        log.info(f"Patch filter '{target_patch}': {len(df)}/{before} matches kept")

    # Merge with existing CSV so a resume never loses previously collected rows
    out_path = Path(CACHE_DIR) / "matches.csv"
    if out_path.exists():
        existing = pd.read_csv(out_path)
        if len(df) > 0:
            df = pd.concat([existing, df]).drop_duplicates(subset=["match_id"]).reset_index(drop=True)
            log.info(f"Merged with existing data: {len(df)} total matches")
        else:
            log.info("No new matches collected - existing data unchanged")
            return existing

    df.to_csv(out_path, index=False)
    log.info(f"Saved to {out_path}")

    return df


if __name__ == "__main__":
    df = run_spider()
    print(f"\nDataset shape: {df.shape}")
    print(df.head())
