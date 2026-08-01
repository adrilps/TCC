"""
benchmarking/player.py — Player performance comparison against rank distribution.
"""

import pandas as pd
from lol_pipeline.config import PHASE_FEATURES


def benchmark_player(player_stats: dict, df: pd.DataFrame, shap_results: dict) -> pd.DataFrame:
    """
    Compares a single player's game stats against the population distribution,
    weighted by SHAP-derived phase importances.

    player_stats: { feature_name: value } for a single game
    df:           the full match dataset (used as the population baseline)
    shap_results: output of compute_shap()

    Returns a DataFrame sorted by weighted_gap (largest gap = highest priority).
    weighted_gap > 0 means the player is below median for an important metric.
    """
    rows = []
    for phase, res in shap_results.items():
        for feat in PHASE_FEATURES[phase]:
            if feat not in player_stats:
                continue
            player_val = player_stats[feat]
            population = df[feat]
            percentile = (population < player_val).mean() * 100
            shap_weight = res["importance"][feat] / res["importance"].sum()
            rows.append({
                "phase": phase,
                "feature": feat,
                "player_value": round(player_val, 1),
                "percentile": round(percentile, 1),
                "shap_weight": round(shap_weight, 3),
                "weighted_gap": round((50 - percentile) / 100 * shap_weight, 4),
            })

    return pd.DataFrame(rows).sort_values("weighted_gap", ascending=False)


def print_benchmark(gaps: pd.DataFrame, top_n: int = 8):
    """Prints the top improvement areas for a player."""
    top = gaps[gaps["weighted_gap"] > 0].head(top_n)
    print(top[["phase", "feature", "percentile", "shap_weight", "weighted_gap"]].to_string(index=False))
