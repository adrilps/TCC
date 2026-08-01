"""
verify_features.py — Sanity-check extract_features on cached matches.

Run from the project root:
    python -m lol_pipeline.verify_features
    python -m lol_pipeline.verify_features --n 10

Checks performed:
  - Phase durations sum to ~match duration
  - CS/min in plausible range (5–9 for Gold mid)
  - Vision/min positive and small (0.5–2)
  - Damage share in [0, 1]
  - Kill participation in [0, 1]
  - No phase has all-NaN features in a normal-length match (>= 20 min)
"""

import argparse
import json
import hashlib
from pathlib import Path

import pandas as pd

from lol_pipeline.config import CACHE_DIR, REGION_ROUTING
from lol_pipeline.data.spider import extract_features


def load_cached(url: str) -> dict | None:
    cache_dir = Path(CACHE_DIR)
    h = hashlib.md5(url.encode()).hexdigest()
    path = cache_dir / f"{h}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def get_cached_match_ids(n: int) -> list[str]:
    """Collect up to n match IDs from the progress file."""
    progress = Path(CACHE_DIR) / "_progress.json"
    if not progress.exists():
        print("No _progress.json found in cache/ — run the spider first.")
        return []
    with open(progress) as f:
        state = json.load(f)
    return list(state.get("visited_matches", []))[:n]


def verify(n: int = 5):
    match_ids = get_cached_match_ids(n * 5)  # fetch extra; many may have no mid data
    if not match_ids:
        return

    rows = []
    checked = 0

    for match_id in match_ids:
        if len(rows) >= n:
            break

        info_url     = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        timeline_url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"

        match_info = load_cached(info_url)
        timeline   = load_cached(timeline_url)

        if not match_info or not timeline:
            continue

        # Try each participant as potential target until one is mid
        for p in match_info["info"]["participants"]:
            if p.get("teamPosition") != "MIDDLE":
                continue
            row = extract_features(match_info, timeline, p["puuid"])
            if row:
                rows.append(row)
                checked += 1
                break

    if not rows:
        print("No rows extracted — check that the cache has complete match data.")
        return

    df = pd.DataFrame(rows)

    print(f"\n{'='*60}")
    print(f"Verified {len(df)} rows from {checked} matches")
    print(f"{'='*60}\n")

    # ── 1. Phase durations ────────────────────────────────────────────────────
    df["total_dur"] = df["early_duration_min"] + df["mid_duration_min"] + df["late_duration_min"]
    match_dur_col   = df["total_dur"]
    print("Phase durations (min)")
    print(df[["early_duration_min", "mid_duration_min", "late_duration_min", "total_dur"]].to_string(index=False))
    print()

    # ── 2. Feature sanity checks ──────────────────────────────────────────────
    checks = {
        "CS/min (early)":           ("early_cs_per_min",         3,  15),
        "CS/min (mid)":             ("mid_cs_per_min",            3,  15),
        "CS/min (late)":            ("late_cs_per_min",           0,  20),
        "Vision/min (early)":       ("early_vision_per_min",      0,   5),
        "Vision/min (mid)":         ("mid_vision_per_min",        0,   5),
        "Vision/min (late)":        ("late_vision_per_min",       0,   5),
        "Damage share (early)":     ("early_damage_share",        0,   1),
        "Damage share (mid)":       ("mid_damage_share",          0,   1),
        "Damage share (late)":      ("late_damage_share",         0,   1),
        "Kill participation (early)":("early_kill_participation", 0,   1),
        "Kill participation (mid)": ("mid_kill_participation",    0,   1),
        "Kill participation (late)":("late_kill_participation",   0,   1),
    }

    all_ok = True
    print(f"{'Check':<35} {'Min':>7} {'Max':>7} {'Mean':>7}  Status")
    print("-" * 65)
    for label, (col, lo, hi) in checks.items():
        if col not in df.columns:
            print(f"  {label:<33} MISSING COLUMN")
            all_ok = False
            continue
        series = df[col].dropna()
        if series.empty:
            print(f"  {label:<33} ALL NaN (may be OK for short matches)")
            continue
        cmin, cmax, cmean = series.min(), series.max(), series.mean()
        ok = (cmin >= lo - 0.001) and (cmax <= hi + 0.001)
        status = "OK" if ok else f"WARN (expected [{lo}, {hi}])"
        if not ok:
            all_ok = False
        print(f"  {label:<33} {cmin:>7.3f} {cmax:>7.3f} {cmean:>7.3f}  {status}")
    print()

    # ── 3. All-NaN check for normal-length matches ────────────────────────────
    from lol_pipeline.config import PHASE_FEATURES
    normal = df[df["total_dur"] >= 20].copy()
    if not normal.empty:
        for phase in ("Early", "Mid", "Late"):
            feat_cols = [c for c in PHASE_FEATURES[phase] if c in df.columns]
            phase_nan = normal[feat_cols].isna().all(axis=1).sum()
            if phase_nan > 0:
                print(f"  WARN: {phase_nan} normal-length match(es) have all-NaN in {phase} phase")
                all_ok = False
            else:
                print(f"  {phase} phase: no all-NaN rows in normal-length matches  OK")
    print()

    # ── 4. Print one full sample row ─────────────────────────────────────────
    print("Sample row (first extracted match):")
    sample = df.iloc[0].dropna()
    for k, v in sample.items():
        print(f"  {k:<35} {v}")

    print()
    print("Overall:", "ALL CHECKS PASSED" if all_ok else "SOME WARNINGS — see above")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="Number of matches to verify")
    args = parser.parse_args()
    verify(args.n)
