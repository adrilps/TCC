"""
explainability/shap_analysis.py — SHAP value computation per phase.
"""

import numpy as np
import pandas as pd
import shap


def compute_shap(models: dict) -> dict:
    """
    Runs SHAP TreeExplainer on each phase model.
    mean(|SHAP values|) across the test set = empirical feature importance.
    This replaces manually assigned weights with data-derived ones.

    Returns a dict: { phase_name: { shap_values, importance (Series), X_test } }
    """
    shap_results = {}
    for phase, obj in models.items():
        explainer = shap.TreeExplainer(obj["model"])
        shap_values = explainer.shap_values(obj["X_test"])
        mean_abs = np.abs(shap_values).mean(axis=0)
        importance = pd.Series(mean_abs, index=obj["features"]).sort_values(ascending=False)
        shap_results[phase] = {
            "shap_values": shap_values,
            "importance": importance,
            "X_test": obj["X_test"],
        }

    return shap_results


def print_importances(shap_results: dict):
    """Prints normalized feature importances per phase to stdout."""
    for phase, res in shap_results.items():
        print(f"  {phase}")
        norm = res["importance"] / res["importance"].sum()
        for feat, val in norm.items():
            print(f"    {feat:<30} {val:.3f}")
        print()
