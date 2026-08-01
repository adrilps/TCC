"""
main.py — Orchestrates the full pipeline. Should stay as thin as possible.
"""

from lol_pipeline.data.loader import load_data
from lol_pipeline.models.train import train_phase_models
from lol_pipeline.explainability.shap_analysis import compute_shap, print_importances
from lol_pipeline.benchmarking.player import benchmark_player, print_benchmark
from lol_pipeline.visualization.plots import plot_importance_comparison, plot_shap_beeswarm


def main(source: str = "csv", patch: str | None = None):
    print("=== LoL SHAP Pipeline ===\n")

    print("[1] Loading data...")
    df = load_data(source=source)
    if patch and "patch" in df.columns:
        df = df[df["patch"] == patch].reset_index(drop=True)
    print(f"    {len(df)} matches, {len(df.columns)-1} features + win label\n")

    print("[2] Training per-phase models...")
    models = train_phase_models(df)

    print("\n[3] Computing SHAP values...")
    shap_results = compute_shap(models)

    print("\n[4] Plotting results...")
    plot_importance_comparison(shap_results)
    plot_shap_beeswarm(shap_results)

    print("\n[5] Phase importances (normalized):")
    print_importances(shap_results)

    print("[6] Example player benchmark...")
    # A slightly below-average Gold mid-laner: weak early vision and kill participation,
    # decent CS, low objective proximity — representative of a typical improvement case.
    example_player = {
        "early_cs_per_min":           6.0,
        "early_vision_per_min":       0.7,
        "early_deaths_per_min":       0.12,
        "early_kill_participation":   0.35,
        "early_damage_share":         0.21,
        "early_solo_kills":           0,
        "early_objective_proximity":  0.25,
        "early_first_blood_involved": 0,
        "mid_cs_per_min":             6.5,
        "mid_vision_per_min":         1.0,
        "mid_deaths_per_min":         0.10,
        "mid_kill_participation":     0.50,
        "mid_damage_share":           0.25,
        "mid_solo_kills":             1,
        "mid_objective_proximity":    0.35,
        "late_cs_per_min":            5.5,
        "late_vision_per_min":        1.2,
        "late_deaths_per_min":        0.08,
        "late_kill_participation":    0.55,
        "late_damage_share":          0.26,
        "late_solo_kills":            0,
        "late_objective_proximity":   0.30,
    }
    gaps = benchmark_player(example_player, df, shap_results)
    print_benchmark(gaps)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
