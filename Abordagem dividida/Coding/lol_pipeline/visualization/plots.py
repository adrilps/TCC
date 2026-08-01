"""
visualization/plots.py — All plotting functions for the pipeline.
"""

import matplotlib.pyplot as plt
import shap
import os
from lol_pipeline.config import OUTPUT_DIR


def plot_importance_comparison(shap_results: dict):
    """Bar chart comparing normalized feature importances across phases."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    colors = ["#4C9BE8", "#E8A24C", "#4CE87A"]

    for ax, (phase, res), color in zip(axes, shap_results.items(), colors):
        imp = res["importance"]
        imp_norm = imp / imp.sum()
        imp_norm.plot(kind="barh", ax=ax, color=color)
        ax.set_title(phase, fontsize=13, fontweight="bold")
        ax.set_xlabel("Normalized SHAP importance")
        ax.invert_yaxis()
        ax.axvline(0, color="black", linewidth=0.5)

    plt.suptitle("Feature Importance per Game Phase (SHAP)", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "shap_importance_by_phase.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_shap_beeswarm(shap_results: dict):
    """SHAP beeswarm plots — shows direction of impact, not just magnitude."""
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))

    for ax, (phase, res) in zip(axes, shap_results.items()):
        plt.sca(ax)
        shap.summary_plot(res["shap_values"], res["X_test"], show=False, plot_size=None, color_bar=False)
        ax.set_title(phase, fontsize=12, fontweight="bold")

    plt.suptitle("SHAP Beeswarm — Direction & Magnitude of Feature Impact", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "shap_beeswarm_by_phase.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")
