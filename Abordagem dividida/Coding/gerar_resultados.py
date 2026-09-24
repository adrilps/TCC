"""
gerar_resultados.py — Regenera, em um comando, todos os resultados centrais.

Ate agora, as metricas, a estabilidade, as importancias e as figuras vinham de
trechos avulsos de codigo, o que impedia reproduzir o capitulo de resultados a
partir de um unico ponto. Este script fecha essa lacuna.

Escreve em outputs/:
    metricas_modelos.csv          AUC por fase, baseline e tamanhos
    auc_estabilidade.csv          AUC em 10 particoes independentes
    importancias_shap.csv         importancia normalizada por fase
    fig_importancia_por_fase.png
    fig_evolucao_importancia.png
    fig_beeswarm_por_fase.png
    resultados_consolidados.txt   resumo legivel de tudo acima

Nao regenera: o experimento de fronteiras (experimento_fronteiras.py e
validacao_fronteiras.py) nem o metodo de comparacao (comparacao.py), que sao
mais lentos e tem scripts proprios.

Uso, a partir da pasta Coding:
    py gerar_resultados.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.config import OUTPUT_DIR
from lol_pipeline.models.train import (train_phase_models, tabela_metricas,
                                       avaliar_estabilidade, AUC_MINIMO)
from lol_pipeline.explainability.shap_analysis import (compute_shap,
                                                       tabela_importancias, rotulo)
from lol_pipeline.visualization.plots import (plot_importance_comparison,
                                              plot_evolucao_importancia,
                                              plot_shap_beeswarm)

CAMINHO = "dataset/dataset_congelado_16_17.csv"
SEMENTES = (42, 7, 13, 99, 2024, 101, 2718, 31337, 555, 888)

# Valores de referencia da execucao documentada em RESULTADOS.md. Servem para
# detectar divergencia: se o script deixar de reproduzi-los, algo mudou no
# pipeline e os numeros do texto precisam ser revistos antes de qualquer uso.
REFERENCIA = {
    "linhas": 2045,
    "jogadores": 933,
    "auc": {"Early": 0.667, "Mid": 0.733, "Late": 0.809},
}
NOME = {"Early": "inicial", "Mid": "intermediaria", "Late": "final"}


def main():
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CAMINHO)
    n, njog = len(df), df["puuid"].nunique()
    print(f"Conjunto: {n} partidas, {njog} jogadores\n")

    # ── Modelos e metricas ───────────────────────────────────────────────────
    print("Treinando modelos por fase (particao principal, semente 42)...")
    modelos = train_phase_models(df)
    met = tabela_metricas(modelos)
    met.to_csv(out / "metricas_modelos.csv", index=False)

    # ── Interpretabilidade ───────────────────────────────────────────────────
    print("\nCalculando valores SHAP...")
    shap_res = compute_shap(modelos)
    imp = tabela_importancias(shap_res)
    imp.to_csv(out / "importancias_shap.csv", index=False, encoding="utf-8")

    # ── Figuras ──────────────────────────────────────────────────────────────
    print("\nGerando figuras...")
    plot_importance_comparison(shap_res)
    plot_evolucao_importancia(shap_res)
    plot_shap_beeswarm(shap_res)

    # ── Estabilidade ─────────────────────────────────────────────────────────
    print(f"\nAvaliando estabilidade em {len(SEMENTES)} particoes independentes...")
    est = avaliar_estabilidade(df, seeds=SEMENTES)
    est.to_csv(out / "auc_estabilidade.csv", index=False)
    resumo_est = est.groupby("fase")["auc"].agg(["mean", "std", "min", "max"])
    resumo_est["baseline"] = est.groupby("fase")["auc_baseline"].mean()
    resumo_est["atinge"] = est.groupby("fase")["auc"].apply(
        lambda s: f"{(s >= AUC_MINIMO).sum()}/{len(s)}")

    # ── Verificacao contra a referencia ──────────────────────────────────────
    alertas = []
    if n != REFERENCIA["linhas"] or njog != REFERENCIA["jogadores"]:
        alertas.append(f"conjunto mudou: {n} partidas / {njog} jogadores "
                       f"(referencia: {REFERENCIA['linhas']} / {REFERENCIA['jogadores']})")
    for fase, esperado in REFERENCIA["auc"].items():
        obtido = modelos[fase]["auc"]
        if abs(obtido - esperado) > 0.01:
            alertas.append(f"AUC da fase {NOME[fase]}: {obtido:.3f} "
                           f"(referencia {esperado:.3f})")

    # ── Relatorio consolidado ────────────────────────────────────────────────
    L = []
    P = L.append
    P("=" * 78)
    P("RESULTADOS CONSOLIDADOS")
    P("=" * 78)
    P("")
    P(f"Conjunto: {n} partidas, {njog} jogadores, patch 16.17")
    P(f"Taxa de vitoria: {df['win'].mean()*100:.2f}%")
    P("")
    P("-" * 78)
    P("DESEMPENHO PREDITIVO — particao principal")
    P("-" * 78)
    P(f"{'fase':<16}{'AUC':>8}{'baseline':>10}{'treino':>9}{'teste':>8}{'jogadores':>12}")
    for _, r in met.iterrows():
        P(f"{NOME.get(r.fase, r.fase):<16}{r.auc_xgboost:>8.3f}{r.auc_baseline_lr:>10.3f}"
          f"{r.n_treino:>9}{r.n_teste:>8}"
          f"{str(r.jogadores_treino)+'/'+str(r.jogadores_teste):>12}")
    P("")
    P("-" * 78)
    P(f"ESTABILIDADE — {len(SEMENTES)} particoes independentes por jogador")
    P("-" * 78)
    P(f"{'fase':<16}{'media':>8}{'dp':>8}{'minimo':>9}{'maximo':>9}"
      f"{'baseline':>10}{'>=0,65':>9}")
    for fase in ("Early", "Mid", "Late"):
        if fase not in resumo_est.index:
            continue
        r = resumo_est.loc[fase]
        P(f"{NOME[fase]:<16}{r['mean']:>8.3f}{r['std']:>8.3f}{r['min']:>9.3f}"
          f"{r['max']:>9.3f}{r['baseline']:>10.3f}{r['atinge']:>9}")
    P("")
    P("-" * 78)
    P("IMPORTANCIA SHAP NORMALIZADA")
    P("-" * 78)
    pivo = imp.pivot_table(index="rotulo", columns="fase",
                           values="importancia_normalizada")
    ordem = [c for c in ("Early", "Mid", "Late") if c in pivo.columns]
    pivo = pivo[ordem].sort_values(ordem[-1], ascending=False)
    P(f"{'metrica':<32}" + "".join(f"{NOME[c]:>16}" for c in ordem))
    for met_nome, linha in pivo.iterrows():
        P(f"{met_nome:<32}" + "".join(f"{linha[c]:>16.3f}" for c in ordem))
    P("")
    if alertas:
        P("-" * 78)
        P("ATENCAO — divergencia em relacao a RESULTADOS.md")
        P("-" * 78)
        for a in alertas:
            P(f"  {a}")
        P("  Revise antes de usar estes numeros no texto.")
    else:
        P("Verificacao: os valores reproduzem os documentados em RESULTADOS.md.")
    P("=" * 78)

    txt = "\n".join(L)
    (out / "resultados_consolidados.txt").write_text(txt, encoding="utf-8")
    print("\n" + txt)
    print(f"\nArquivos escritos em {out.resolve()}")


if __name__ == "__main__":
    main()
