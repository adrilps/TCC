"""
visualization/plots.py — Figuras do capitulo de resultados (rotulos em PT-BR).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap

from lol_pipeline.config import OUTPUT_DIR
from lol_pipeline.explainability.shap_analysis import rotulo

NOME_FASE = {"Early": "Fase inicial", "Mid": "Fase intermediária", "Late": "Fase final"}
CORES = {"Early": "#33628F", "Mid": "#7C5296", "Late": "#2E7D6E"}


def _salvar(fig, nome):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    caminho = os.path.join(OUTPUT_DIR, nome)
    fig.savefig(caminho, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figura salva: {caminho}")
    return caminho


def plot_importance_comparison(shap_results: dict):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharex=True)
    for ax, (fase, res) in zip(axes, shap_results.items()):
        imp = res["importance_norm"].sort_values()
        ax.barh([rotulo(f) for f in imp.index], imp.values,
                color=CORES.get(fase, "#555"), edgecolor="none")
        titulo = NOME_FASE.get(fase, fase)
        if res.get("auc"):
            titulo += f"\n(AUC = {res['auc']:.3f})"
        ax.set_title(titulo, fontsize=12, fontweight="bold")
        ax.set_xlabel("Importância SHAP normalizada")
        ax.grid(axis="x", alpha=.25, linewidth=.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
    fig.suptitle("Importância empírica das métricas comportamentais por fase da partida",
                 fontsize=14, fontweight="bold", y=1.03)
    fig.tight_layout()
    return _salvar(fig, "fig_importancia_por_fase.png")


def plot_shap_beeswarm(shap_results: dict):
    """
    Beeswarm por fase. Cada ponto e uma partida do conjunto de teste:
    a posicao horizontal e o impacto daquela metrica sobre a predicao e
    a cor indica se o valor da metrica era alto ou baixo naquela partida.
    """
    import matplotlib as mpl
    try:
        cmap = shap.plots.colors.red_blue
    except Exception:
        cmap = mpl.colors.LinearSegmentedColormap.from_list(
            "rb", ["#1E88E5", "#8E44AD", "#E5194B"])

    fig, axes = plt.subplots(1, 3, figsize=(19, 6.4))
    for ax, (fase, res) in zip(axes, shap_results.items()):
        plt.sca(ax)
        X = res["X_test"].rename(columns={c: rotulo(c) for c in res["X_test"].columns})
        shap.summary_plot(res["shap_values"], X, show=False,
                          plot_size=None, color_bar=False, cmap=cmap)
        ax.set_title(NOME_FASE.get(fase, fase), fontsize=12, fontweight="bold")
        ax.set_xlabel("Valor SHAP", fontsize=10)

    fig.suptitle("Direção e magnitude do impacto de cada métrica sobre a predição (TreeSHAP)",
                 fontsize=14, fontweight="bold", y=1.0)
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))

    # Barra de cor unica, com rotulos em portugues
    eixo_cor = fig.add_axes((0.35, 0.015, 0.30, 0.022))
    barra = mpl.colorbar.ColorbarBase(
        eixo_cor, cmap=cmap, orientation="horizontal",
        norm=mpl.colors.Normalize(vmin=0, vmax=1))
    barra.set_ticks([0, 1])
    barra.set_ticklabels(["valor baixo da métrica", "valor alto da métrica"])
    barra.ax.tick_params(labelsize=9, length=0)
    barra.outline.set_visible(False)

    fig.text(0.5, 0.055,
             "Valores SHAP positivos empurram a predição para a vitória; negativos, para a derrota.",
             ha="center", fontsize=9.5, color="#444444")
    return _salvar(fig, "fig_beeswarm_por_fase.png")


def plot_evolucao_importancia(shap_results: dict):
    """Como a importancia de cada metrica evolui entre as fases — figura-sintese."""
    fases = list(shap_results.keys())
    metricas = {}
    for fase, res in shap_results.items():
        for feat, val in res["importance_norm"].items():
            metricas.setdefault(rotulo(feat), {})[fase] = val
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for nome, vals in sorted(metricas.items(), key=lambda kv: -max(kv[1].values())):
        xs = [f for f in fases if f in vals]
        if len(xs) < 2:
            continue
        ax.plot([NOME_FASE.get(f, f) for f in xs], [vals[f] for f in xs],
                marker="o", linewidth=2, label=nome)
    ax.set_ylabel("Importância SHAP normalizada")
    ax.set_title("Evolução da importância das métricas ao longo da partida",
                 fontsize=13, fontweight="bold")
    ax.grid(alpha=.25, linewidth=.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    return _salvar(fig, "fig_evolucao_importancia.png")
