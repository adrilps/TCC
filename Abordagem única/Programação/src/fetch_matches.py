"""
Riot API Match Fetcher
=======================
Fetches match detail + timeline for a player and saves raw JSONs
ready for the extract_matches.py pipeline.

Usage:
  python fetch_matches.py --apikey YOUR_KEY --puuid YOUR_PUUID --count 50 --out ./raw_matches

Output folder will contain per-match files:
  {match_id}_match.json
  {match_id}_timeline.json
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests


# BR accounts use americas for match-v5
MATCH_REGION = "americas"
SUMMONER_REGION = "br1"

HEADERS = {}  # api key injected at runtime


def get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        resp = requests.get(url, headers=HEADERS)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"    Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        if resp.status_code == 404:
            raise ValueError(f"404 Not found: {url}")

        print(f"    HTTP {resp.status_code} on attempt {attempt+1}: {url}")
        time.sleep(3)

    raise RuntimeError(f"Failed after {retries} attempts: {url}")


def fetch_match_ids(puuid: str, count: int) -> list[str]:
    url = (
        f"https://{MATCH_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid"
        f"/{puuid}/ids?start=0&count={count}&queue=420"
    )
    print(f"Fetching {count} ranked match IDs...")
    ids = get(url)
    print(f"  Got {len(ids)} match IDs.")
    return ids


def fetch_and_save(match_id: str, out_dir: Path, skip_existing: bool = True):
    match_path = out_dir / f"{match_id}_match.json"
    timeline_path = out_dir / f"{match_id}_timeline.json"

    # Match detail
    if skip_existing and match_path.exists():
        print(f"  [exists] {match_id}_match.json")
    else:
        url = f"https://{MATCH_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        print(f"  Fetching match {match_id}...")
        data = get(url)
        with open(match_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        time.sleep(1.2)  # stay under 100 req/2min dev key rate limit

    # Timeline
    if skip_existing and timeline_path.exists():
        print(f"  [exists] {match_id}_timeline.json")
    else:
        url = f"https://{MATCH_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        print(f"  Fetching timeline {match_id}...")
        data = get(url)
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        time.sleep(1.2)


def main():
    parser = argparse.ArgumentParser(description="Fetch Riot match + timeline JSONs")
    parser.add_argument("--apikey", required=True, help="Your Riot API key (RGAPI-...)")
    parser.add_argument("--puuid", required=True, help="Your player PUUID")
    parser.add_argument("--count", type=int, default=50, help="Number of matches to fetch (max 100)")
    parser.add_argument("--out", default="./raw_matches", help="Output folder")
    args = parser.parse_args()

    HEADERS["X-Riot-Token"] = args.apikey

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    match_ids = fetch_match_ids(args.puuid, args.count)

    print(f"\nFetching {len(match_ids)} matches into '{out_dir}'...\n")
    failed = []
    for i, mid in enumerate(match_ids, 1):
        print(f"[{i}/{len(match_ids)}]")
        try:
            fetch_and_save(mid, out_dir)
        except Exception as e:
            print(f"  [error] {mid}: {e}")
            failed.append(mid)

    print(f"\nDone. {len(match_ids) - len(failed)}/{len(match_ids)} matches saved to '{out_dir}'.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"\nNext step — run the extractor:")
    print(f"  python extract_matches.py --dir \"{out_dir.resolve()}\" --puuid {args.puuid} --out extracted_matches.csv")


if __name__ == "__main__":
    main()
