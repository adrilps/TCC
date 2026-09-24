"""
comparar_elos.py — Compara importancias SHAP entre dois elos.

Uso:  py comparar_elos.py [patch]     (padrao: 16.17)

Le dataset/matches.csv (Ouro) e dataset/matches_DIAMOND.csv (Diamante),
treina os modelos por fase em cada elo e compara AUCs e importancias.
Gera outputs/comparacao_elos.csv e outputs/fig_comparacao_elos.png.
"""
import sys
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.models.train import train_phase_models, AUC_MINIMO
from lol_pipeline.explainability.shap_analysis import compute_shap, rotulo
from lol_pipeline.visualization.plots import NOME_FASE
from lol_pipeline.config import OUTPUT_DIR

PATCH = sys.argv[1] if len(sys.argv) > 1 else "16.17"
MINIMO_LINHAS = 400   # abaixo disso a comparacao nao se sustenta

def carregar(caminho, nome):
    df = pd.read_csv(caminho)
    df["patch"] = df["patch"].astype(str)
    df = df[df["patch"] == PATCH].reset_index(drop=True)
    print(f"{nome}: {len(df)} partidas, {df['puuid'].nunique()} jogadores (patch {PATCH})")
    return df

ouro = carregar("dataset/matches.csv", "Ouro")
diam = carregar("dataset/matches_DIAMOND.csv", "Diamante")

if len(diam) < MINIMO_LINHAS:
    print(f"\nAVISO: Diamante tem apenas {len(diam)} partidas no patch {PATCH}.")
    print(f"A comparacao abaixo e PRELIMINAR e nao deve ir para o texto final.")
    print(f"Recomendado: pelo menos {MINIMO_LINHAS} partidas.\n")

resultados, linhas = {}, []
for nome, df in (("Ouro", ouro), ("Diamante", diam)):
    print(f"\n--- {nome} ---")
    modelos = train_phase_models(df)
    shap_res = compute_shap(modelos)
    resultados[nome] = shap_res
    for fase, res in shap_res.items():
        for feat, val in res["importance_norm"].items():
            linhas.append({"elo": nome, "fase": fase, "metrica": rotulo(feat),
                           "importancia": round(float(val), 4),
                           "auc_da_fase": round(res["auc"], 4)})

tab = pd.DataFrame(linhas)
tab.to_csv(Path(OUTPUT_DIR) / "comparacao_elos.csv", index=False, encoding="utf-8")

# ── Tabela lado a lado ───────────────────────────────────────────────────────
print("\n=== IMPORTANCIA NORMALIZADA: OURO vs DIAMANTE ===")
for fase in ("Early", "Mid", "Late"):
    print(f"\n{NOME_FASE[fase]}")
    a = tab[(tab.elo == "Ouro") & (tab.fase == fase)].set_index("metrica")["importancia"]
    b = tab[(tab.elo == "Diamante") & (tab.fase == fase)].set_index("metrica")["importancia"]
    comp = pd.DataFrame({"Ouro": a, "Diamante": b})
    comp["diferenca"] = (comp["Diamante"] - comp["Ouro"]).round(3)
    print(comp.sort_values("Ouro", ascending=False).to_string())

# ── Figura: barras pareadas por fase ─────────────────────────────────────────
fases = ["Early", "Mid", "Late"]
fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharex=True)
for ax, fase in zip(axes, fases):
    a = tab[(tab.elo == "Ouro") & (tab.fase == fase)].set_index("metrica")["importancia"]
    b = tab[(tab.elo == "Diamante") & (tab.fase == fase)].set_index("metrica")["importancia"]
    comp = pd.DataFrame({"Ouro": a, "Diamante": b}).sort_values("Ouro")
    y = range(len(comp))
    ax.barh([i + 0.2 for i in y], comp["Ouro"], height=0.38, color="#B8860B", label="Ouro")
    ax.barh([i - 0.2 for i in y], comp["Diamante"], height=0.38, color="#4A90A4", label="Diamante")
    ax.set_yticks(list(y)); ax.set_yticklabels(comp.index)
    ax.set_title(NOME_FASE[fase], fontsize=12, fontweight="bold")
    ax.set_xlabel("Importância SHAP normalizada")
    ax.grid(axis="x", alpha=.25, linewidth=.6); ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
axes[0].legend(frameon=False, loc="lower right")
fig.suptitle("Importância das métricas por fase: Ouro vs Diamante",
             fontsize=14, fontweight="bold", y=1.02)
fig.tight_layout()
saida = Path(OUTPUT_DIR) / "fig_comparacao_elos.png"
fig.savefig(saida, dpi=200, bbox_inches="tight")
print(f"\nFigura salva: {saida}")
print(f"Tabela salva: {Path(OUTPUT_DIR) / 'comparacao_elos.csv'}")
