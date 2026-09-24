"""
comparacao.py — Metodo de comparacao de desempenho ponderado por importancia.

Este e o objetivo especifico 4: comparar o desempenho de um jogador com a
distribuicao de jogadores da mesma funcao e elo, ponderando cada desvio pela
importancia que aquela metrica tem naquela fase.

FORMULACAO
  Para o jogador j, a fase f e a metrica m:

  1. Percentil populacional, de rank medio
       p = [ P(X < x) + P(X <= x) ] / 2
     em que F e a distribuicao empirica da metrica na populacao de referencia
     (mid lane, Ouro, mesmo patch). O percentil e usado em vez do escore-z
     porque varias metricas tem cauda longa: na fase final, por exemplo, o
     farm por minuto chega a 105 em partidas muito curtas, e uma padronizacao
     por media e desvio seria dominada por esses extremos.

  2. Orientacao
       s_{f,m} in {+1, -1, 0}
     obtida do proprio modelo, pela correlacao entre o valor da metrica e seu
     valor SHAP no conjunto de teste. s = +1 quando valores maiores empurram a
     predicao para a vitoria, -1 no caso contrario. Quando |r| < LIMIAR_DIRECAO
     a metrica nao apresenta direcao consistente naquela fase e recebe s = 0:
     ela e descrita, mas nao entra na priorizacao, porque prescrever "aumente"
     ou "reduza" sem direcao estavel seria recomendar ruido.

     Percentil orientado:  q = p se s = +1;  q = 1 - p se s = -1.

  3. Lacuna
       d = max(0, 0,5 - q)
     Apenas o que esta abaixo da mediana constitui lacuna. Estar acima nao
     gera prioridade de melhoria, ainda que seja reportado.

  4. Ponderacao
       g = w_{f,m} * d
     em que w e a importancia SHAP normalizada dentro da fase (soma 1 por
     fase). Como os pesos sao normalizados intra-fase, g fica na mesma escala
     nas tres fases sem que valores SHAP de modelos distintos sejam comparados
     diretamente, o que a metodologia veda.

  5. Escore da fase
       G_f = 2 * soma_m g_{f,m}   in [0, 1]
     Zero indica desempenho na mediana ou acima em todas as metricas com
     direcao definida; um indica o pior percentil em todas elas.

Uso:
    py comparacao.py                  -> exemplo com um jogador do conjunto
    py comparacao.py <puuid>          -> jogador especifico
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import shap
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.config import PHASE_FEATURES, XGB_PARAMS, TEST_SIZE, OUTPUT_DIR
from lol_pipeline.explainability.shap_analysis import rotulo

CAMINHO_DATASET = "dataset/dataset_congelado_16_17.csv"
LIMIAR_DIRECAO = 0.50     # |r| minimo para a metrica ter direcao prescritiva
FASES = (("Early", "early", "inicial"), ("Mid", "mid", "intermediaria"),
         ("Late", "late", "final"))


# ── Pesos e orientacoes, derivados do modelo ─────────────────────────────────

def pesos_e_orientacoes(df, seed=42):
    """
    Treina os modelos por fase e devolve, para cada fase:
      importancia normalizada de cada metrica (soma 1)
      orientacao s em {+1, -1, 0}
      forca da direcao |r|, para transparencia
    """
    saida = {}
    for fase, pre, _ in FASES:
        feats = PHASE_FEATURES[fase]
        sub = df[df[f"{pre}_duration_min"] > 0].reset_index(drop=True)
        X, y, g = sub[feats], sub["win"], sub["puuid"]
        tr, te = next(GroupShuffleSplit(1, test_size=TEST_SIZE,
                                        random_state=seed).split(X, y, g))
        modelo = xgb.XGBClassifier(**{**XGB_PARAMS, "random_state": seed})
        modelo.fit(X.iloc[tr], y.iloc[tr])

        sv = shap.TreeExplainer(modelo).shap_values(X.iloc[te])
        imp = pd.Series(np.abs(sv).mean(axis=0), index=feats)
        imp = imp / imp.sum()

        orient, forca = {}, {}
        Xte = X.iloc[te]
        for i, c in enumerate(feats):
            v, s_ = Xte[c].to_numpy(), sv[:, i]
            ok = ~np.isnan(v)
            r = np.corrcoef(v[ok], s_[ok])[0, 1] if ok.sum() > 20 else np.nan
            if np.isnan(r) or abs(r) < LIMIAR_DIRECAO:
                orient[c], forca[c] = 0, (0.0 if np.isnan(r) else abs(r))
            else:
                orient[c], forca[c] = int(np.sign(r)), abs(r)
        saida[fase] = {"peso": imp, "orientacao": orient, "forca": forca}
    return saida


# ── Comparacao de um jogador ─────────────────────────────────────────────────

def comparar(valores_jogador, df, modelo_fases):
    """
    valores_jogador: dict {nome_da_coluna: valor} com as metricas do jogador.
    df:              populacao de referencia.
    Devolve um DataFrame com uma linha por metrica avaliada.
    """
    linhas = []
    for fase, pre, nome_fase in FASES:
        info = modelo_fases[fase]
        pop_fase = df[df[f"{pre}_duration_min"] > 0]
        for c in PHASE_FEATURES[fase]:
            if c not in valores_jogador or pd.isna(valores_jogador[c]):
                continue
            x = float(valores_jogador[c])
            col = pop_fase[c].dropna()
            if len(col) < 50:
                continue
            # Percentil de rank medio: a media entre a proporcao estritamente
            # menor e a menor ou igual. Sem isso, metricas com muitos empates
            # (proximidade de objetivos tem mais de 75% de zeros na fase
            # inicial) colocam no percentil zero um jogador que esta exatamente
            # na mediana da populacao, gerando lacuna onde nao ha.
            p = float(((col < x).mean() + (col <= x).mean()) / 2.0)
            s = info["orientacao"][c]
            w = float(info["peso"][c])
            q = p if s >= 0 else 1.0 - p
            d = max(0.0, 0.5 - q) if s != 0 else np.nan
            linhas.append({
                "fase": nome_fase,
                "metrica": rotulo(c),
                "valor": x,
                "mediana_pop": float(col.median()),
                "percentil": round(p * 100, 1),
                "direcao": {1: "maior e melhor", -1: "menor e melhor",
                            0: "sem direcao definida"}[s],
                "forca_direcao": round(info["forca"][c], 2),
                "peso": round(w, 3),
                "lacuna": round(d, 3) if s != 0 else np.nan,
                "lacuna_ponderada": round(w * d, 4) if s != 0 else np.nan,
            })
    return pd.DataFrame(linhas)


def escores_por_fase(tab):
    out = {}
    for f in tab["fase"].unique():
        s = tab[tab.fase == f]["lacuna_ponderada"].sum(skipna=True)
        out[f] = round(min(1.0, 2 * s), 3)
    return out


def relatorio(tab, escores, identificacao=""):
    L = []
    P = L.append
    P("=" * 86)
    P(f"COMPARACAO DE DESEMPENHO PONDERADA POR IMPORTANCIA  {identificacao}")
    P("=" * 86)
    P("")
    P("Escore de lacuna por fase (0 = mediana ou acima em tudo; 1 = pior caso)")
    for f, v in escores.items():
        barra = "#" * int(round(v * 40))
        P(f"  {f:<16}{v:>6.3f}  {barra}")
    P("")
    for f in tab["fase"].unique():
        s = tab[tab.fase == f].sort_values("lacuna_ponderada", ascending=False,
                                           na_position="last")
        P("-" * 86)
        P(f"FASE {f.upper()}")
        P("-" * 86)
        P(f"{'metrica':<30}{'valor':>10}{'mediana':>10}{'perc.':>8}"
          f"{'peso':>8}{'lacuna pond.':>14}")
        for _, r in s.iterrows():
            lp = "—" if pd.isna(r.lacuna_ponderada) else f"{r.lacuna_ponderada:.4f}"
            P(f"{r.metrica:<30}{r.valor:>10.2f}{r.mediana_pop:>10.2f}"
              f"{r.percentil:>7.0f}%{r.peso:>8.3f}{lp:>14}")
        sem = s[s.direcao == "sem direcao definida"]
        if len(sem):
            P(f"  sem direcao consistente nesta fase: "
              f"{', '.join(sem.metrica.tolist())}")
        P("")
    pri = (tab.dropna(subset=["lacuna_ponderada"])
              .sort_values("lacuna_ponderada", ascending=False).head(5))
    P("-" * 86)
    P("PRIORIDADES DE MELHORIA")
    P("-" * 86)
    for i, (_, r) in enumerate(pri.iterrows(), 1):
        if r.lacuna_ponderada <= 0:
            break
        P(f"  {i}. {r.metrica} na fase {r.fase} — percentil {r.percentil:.0f}, "
          f"peso {r.peso:.3f}, lacuna ponderada {r.lacuna_ponderada:.4f}")
    if pri.empty or pri.iloc[0].lacuna_ponderada <= 0:
        P("  Nenhuma metrica com direcao definida abaixo da mediana.")
    P("=" * 86)
    return "\n".join(L)


def main():
    df = pd.read_csv(CAMINHO_DATASET)
    print(f"Populacao de referencia: {len(df)} partidas, "
          f"{df['puuid'].nunique()} jogadores\n")
    modelo_fases = pesos_e_orientacoes(df)

    for fase, _pre, nome in FASES:
        info = modelo_fases[fase]
        sem = [rotulo(c) for c, s in info["orientacao"].items() if s == 0]
        print(f"  {nome:<16} metricas sem direcao consistente: "
              f"{', '.join(sem) if sem else 'nenhuma'}")
    print()

    if len(sys.argv) > 1:
        alvo = sys.argv[1]
        linhas = df[df["puuid"] == alvo]
        if linhas.empty:
            print(f"PUUID nao encontrado no conjunto: {alvo}")
            return
        ident = f"(jogador {alvo[:12]}..., {len(linhas)} partidas)"
    else:
        # Exemplo: o jogador com mais partidas no conjunto
        alvo = df["puuid"].value_counts().index[0]
        linhas = df[df["puuid"] == alvo]
        ident = f"(exemplo: jogador com mais partidas, n={len(linhas)})"

    # O perfil do jogador e a mediana das suas partidas, o que reduz o peso
    # de uma partida atipica.
    todas = [c for fase, _, _ in FASES for c in PHASE_FEATURES[fase]]
    perfil = linhas[todas].median(numeric_only=True).to_dict()

    tab = comparar(perfil, df, modelo_fases)
    esc = escores_por_fase(tab)
    txt = relatorio(tab, esc, ident)
    print(txt)

    out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out / "comparacao_exemplo.csv", index=False, encoding="utf-8")
    (out / "comparacao_exemplo.txt").write_text(txt, encoding="utf-8")
    print(f"\nSalvo em {out}")


if __name__ == "__main__":
    main()
