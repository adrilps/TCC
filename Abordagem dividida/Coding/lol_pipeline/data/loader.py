"""
data/loader.py — Data ingestion layer.
"""

import numpy as np
import pandas as pd
from lol_pipeline.config import N_MATCHES, RANDOM_SEED


def generate_synthetic_data(n_matches: int = N_MATCHES, seed: int = RANDOM_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    skill_gap = rng.normal(0, 1, n_matches)
    win = (skill_gap + rng.normal(0, 0.8, n_matches) > 0).astype(int)

    def signed(base, noise, gap_weight):
        return base + rng.normal(0, noise, n_matches) + gap_weight * skill_gap

    data = pd.DataFrame({
        "early_gold_diff":      signed(0, 800,  600),
        "early_cs_diff":        signed(0, 20,   15),
        "early_xp_diff":        signed(0, 500,  400),
        "early_kill_diff":      signed(0, 2,    1.5),
        "early_first_blood":    (rng.random(n_matches) < (0.5 + 0.15 * skill_gap.clip(-1, 1))).astype(int),
        "early_tower_diff":     signed(0, 0.8,  0.5),
        "early_dragon":         (rng.random(n_matches) < (0.5 + 0.1 * skill_gap.clip(-1, 1))).astype(int),
        "mid_gold_diff":        signed(0, 1500, 1000),
        "mid_cs_diff":          signed(0, 30,   20),
        "mid_kill_diff":        signed(0, 3,    2.5),
        "mid_tower_diff":       signed(0, 1.2,  0.9),
        "mid_dragon_count":     (rng.integers(0, 4, n_matches) + (skill_gap > 0).astype(int)).clip(0, 4),
        "mid_herald":           (rng.random(n_matches) < (0.5 + 0.12 * skill_gap.clip(-1, 1))).astype(int),
        "mid_vision_diff":      signed(0, 15,   10),
        "late_gold_diff":       signed(0, 3000, 2500),
        "late_kill_diff":       signed(0, 5,    4),
        "late_tower_diff":      signed(0, 2,    1.5),
        "late_baron":           (rng.random(n_matches) < (0.5 + 0.2 * skill_gap.clip(-1, 1))).astype(int),
        "late_dragon_soul":     (rng.random(n_matches) < (0.5 + 0.25 * skill_gap.clip(-1, 1))).astype(int),
        "late_vision_diff":     signed(0, 20,   12),
        "late_inhibitor_diff":  signed(0, 0.8,  0.6),
        "win": win
    })
    return data


def load_data(source: str = "synthetic", **kwargs) -> pd.DataFrame:
    """
    Entry point for data loading.

    source:
      "synthetic" — generated fake data (for testing the pipeline)
      "csv"       — load already-collected data from cache/matches.csv
      "api"       — run the BFS spider live (needs RIOT_API_KEY env var)
    """
    if source == "synthetic":
        return generate_synthetic_data(**kwargs)
    elif source == "csv":
        from pathlib import Path
        from lol_pipeline.config import CACHE_DIR
        path = kwargs.get("path", str(Path(CACHE_DIR) / "matches.csv"))
        return pd.read_csv(path)
    elif source == "api":
        from lol_pipeline.data.spider import run_spider
        return run_spider()
    else:
        raise ValueError(f"Unknown data source: '{source}'. Add it to data/loader.py.")
