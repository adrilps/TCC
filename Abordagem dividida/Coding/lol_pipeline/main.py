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
    # Jogador de exemplo: mediana da populacao com um deficit deliberado
    # nas metricas sociais, para ilustrar a saida do metodo.
    from lol_pipeline.config import PHASE_FEATURES
    todas = [f for fs in PHASE_FEATURES.values() for f in fs]
    example_player = df[todas].median(numeric_only=True).to_dict()
    for k in list(example_player):
        if "participacoes" in k or "solo_kills" in k:
            example_player[k] = example_player[k] * 0.6

    gaps = benchmark_player(example_player, df, shap_results)
    print_benchmark(gaps)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
