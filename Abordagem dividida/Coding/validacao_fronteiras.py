"""
validacao_fronteiras.py — Etapa final, com protocolo corrigido.

O QUE MUDOU EM RELACAO A PRIMEIRA EXECUCAO
  No experimento anterior, a etapa de validacao treinava os modelos usando
  apenas os jogadores de validacao (280) e testava dentro deles, enquanto a
  etapa de selecao treinava com 653. As AUCs finais sairam deprimidas por
  tamanho de amostra, nao por sobreajuste, e por isso nao eram comparaveis
  entre si nem com a etapa de selecao.

  Aqui o protocolo e o correto: treina com TODOS os jogadores de selecao e
  testa com TODOS os de validacao. A particao de jogadores e reproduzida
  exatamente (mesma semente), de modo que os conjuntos sao os mesmos.

  Acrescenta tambem intervalo de confianca por bootstrap sobre os JOGADORES
  da validacao, e a diferenca pareada entre configuracoes no mesmo reamostreio,
  que e a forma correta de comparar: se o intervalo da diferenca contem zero,
  as configuracoes sao estatisticamente indistinguiveis.

Uso (no Windows, a partir da pasta Coding):
    py validacao_fronteiras.py

Saida:
    outputs/validacao_fronteiras.txt
"""
import sys, json, time, hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.config import (CACHE_DIR, MATCHES_CSV, REGION_ROUTING,
                                 XGB_PARAMS, OUTPUT_DIR)
from lol_pipeline.data.spider import extract_features

# As tres configuracoes que interessam. As duas primeiras foram escolhidas
# olhando APENAS o conjunto de selecao, na execucao anterior.
CONFIGS = {
    "atual (hibrido 14/25)":      ("hibrido",    True,  14, 25),
    "melhor hibrido (16/31)":     ("hibrido",    True,  16, 31),
    "melhor tempo fixo (14/28)":  ("tempo_fixo", False, 14, 28),
}

METRICAS = ["cs_per_min", "vision_per_min", "deaths_per_min", "solo_kills",
            "dano_por_min", "trocas_por_min", "presenca_lutas_por_min",
            "objective_proximity"]
FASES = (("inicial", "early"), ("intermediaria", "mid"), ("final", "late"))
SEEDS = (42, 7, 13)
PROP_SELECAO = 0.70
SEED_PARTICAO = 20260913     # identica a da primeira execucao
N_BOOTSTRAP = 1000
ESPERADO_LINHAS = 2045

cache = Path(CACHE_DIR)
base_url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches"
CACHE_FEATURES = Path(OUTPUT_DIR) / "_features_configs.pkl"


def do_cache(url):
    f = cache / f"{hashlib.md5(url.encode()).hexdigest()}.json"
    if not f.exists():
        return None
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return None


def extrair():
    if CACHE_FEATURES.exists():
        print("Reaproveitando features ja extraidas.")
        return pd.read_pickle(CACHE_FEATURES)

    src = pd.read_csv(MATCHES_CSV)
    src["patch"] = src["patch"].astype(str)
    src = src[src["patch"] == "16.17"][["match_id", "puuid"]].drop_duplicates()
    print(f"Extraindo {len(src)} partidas em {len(CONFIGS)} configuracoes...")

    linhas = {k: [] for k in CONFIGS}
    t0 = time.time()
    for i, (mid, pu) in enumerate(src.itertuples(index=False), 1):
        info = do_cache(f"{base_url}/{mid}")
        tl = do_cache(f"{base_url}/{mid}/timeline")
        if not info or not tl:
            continue
        for nome, (_modo, usar_ev, ce, cm) in CONFIGS.items():
            row = extract_features(info, tl, pu, early_cap_min=ce,
                                   mid_cap_min=cm, usar_eventos=usar_ev)
            if row:
                linhas[nome].append(row)
        if i % 400 == 0:
            dec = time.time() - t0
            print(f"  {i}/{len(src)} — {dec/60:.1f} min, faltam ~{dec/i*(len(src)-i)/60:.1f} min",
                  flush=True)
    dfs = {k: pd.DataFrame(v) for k, v in linhas.items()}
    CACHE_FEATURES.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(dfs, CACHE_FEATURES)
    return dfs


def prever(df, sel, val, pre):
    """
    Treina com os jogadores de selecao e devolve as predicoes para os de
    validacao. As probabilidades sao a media de tres sementes, o que remove
    a variacao do estimador sem alterar o conjunto de treino.
    """
    s = df[df[f"{pre}_duration_min"] > 0]
    feats = [f"{pre}_{m}" for m in METRICAS]
    tr = s[s["puuid"].isin(sel)]
    te = s[s["puuid"].isin(val)]
    if len(tr) < 200 or len(te) < 100 or te["win"].nunique() < 2:
        return None
    probs = np.zeros(len(te))
    for seed in SEEDS:
        m = xgb.XGBClassifier(**{**XGB_PARAMS, "random_state": seed})
        m.fit(tr[feats], tr["win"])
        probs += m.predict_proba(te[feats])[:, 1]
    probs /= len(SEEDS)
    return te["win"].to_numpy(), probs, te["puuid"].to_numpy(), len(tr), len(te)


def main():
    dfs = extrair()

    atual = dfs["atual (hibrido 14/25)"]
    print(f"\nVerificacao: configuracao atual gerou {len(atual)} linhas "
          f"(esperado {ESPERADO_LINHAS})")
    if abs(len(atual) - ESPERADO_LINHAS) > 5:
        print("  ATENCAO: divergencia. Nao use estes resultados sem checar.")
    else:
        print("  OK.\n")

    # Particao identica a da primeira execucao
    jogadores = np.array(sorted(atual["puuid"].unique()))
    rng = np.random.default_rng(SEED_PARTICAO)
    rng.shuffle(jogadores)
    corte = int(len(jogadores) * PROP_SELECAO)
    sel, val = set(jogadores[:corte]), set(jogadores[corte:])
    print(f"Selecao: {len(sel)} jogadores (treino) | Validacao: {len(val)} (teste)\n")

    # Predicoes por configuracao e fase
    pred = {}
    for nome, df in dfs.items():
        for fase, pre in FASES:
            r = prever(df, sel, val, pre)
            if r:
                pred[(nome, fase)] = r

    # Bootstrap sobre jogadores da validacao, reamostreios compartilhados
    # entre configuracoes para permitir comparacao pareada.
    jog_val = np.array(sorted(val))
    rb = np.random.default_rng(7)
    amostras = [rb.choice(len(jog_val), len(jog_val), replace=True)
                for _ in range(N_BOOTSTRAP)]

    def auc_boot(chave):
        y, p, g, _, _ = pred[chave]
        idx_por_jog = {j: np.where(g == j)[0] for j in np.unique(g)}
        base = roc_auc_score(y, p)
        vals = []
        for am in amostras:
            idx = np.concatenate([idx_por_jog[jog_val[k]]
                                  for k in am if jog_val[k] in idx_por_jog])
            if len(idx) < 50 or len(np.unique(y[idx])) < 2:
                continue
            vals.append(roc_auc_score(y[idx], p[idx]))
        return base, np.array(vals)

    resultados, distrib = {}, {}
    for chave in pred:
        base, vals = auc_boot(chave)
        resultados[chave] = (base, np.percentile(vals, 2.5), np.percentile(vals, 97.5))
        distrib[chave] = vals

    L = []
    P = L.append
    P("=" * 84)
    P("VALIDACAO DAS FRONTEIRAS DE FASE — PROTOCOLO CORRIGIDO")
    P("=" * 84)
    P("")
    P(f"Treino: {len(sel)} jogadores  |  Teste: {len(val)} jogadores (disjuntos)")
    P(f"Intervalos de 95% por bootstrap sobre jogadores ({N_BOOTSTRAP} reamostreios)")
    P("")
    for fase, _pre in FASES:
        chaves = [(n, fase) for n in CONFIGS if (n, fase) in pred]
        if not chaves:
            continue
        n_tr, n_te = pred[chaves[0]][3], pred[chaves[0]][4]
        P("-" * 84)
        P(f"FASE {fase.upper()}   (treino {n_tr} partidas / teste {n_te})")
        P("-" * 84)
        P(f"{'configuracao':<30}{'AUC':>8}{'IC 95%':>20}")
        for c in chaves:
            b, lo, hi = resultados[c]
            P(f"{c[0]:<30}{b:>8.3f}{f'[{lo:.3f}; {hi:.3f}]':>20}")
        P("")

    P("-" * 84)
    P("MEDIA DAS TRES FASES")
    P("-" * 84)
    medias = {}
    for n in CONFIGS:
        ks = [(n, f) for f, _ in FASES if (n, f) in pred]
        if len(ks) < 3:
            continue
        b = np.mean([resultados[k][0] for k in ks])
        tam = min(len(distrib[k]) for k in ks)
        dist = np.mean([distrib[k][:tam] for k in ks], axis=0)
        medias[n] = (b, np.percentile(dist, 2.5), np.percentile(dist, 97.5), dist)
        P(f"{n:<30}{b:>8.3f}{f'[{medias[n][1]:.3f}; {medias[n][2]:.3f}]':>20}")
    P("")

    P("-" * 84)
    P("DIFERENCAS PAREADAS (mesmo reamostreio; zero dentro do IC = equivalentes)")
    P("-" * 84)
    ref = "atual (hibrido 14/25)"
    if ref in medias:
        for n in medias:
            if n == ref:
                continue
            tam = min(len(medias[n][3]), len(medias[ref][3]))
            dif = medias[n][3][:tam] - medias[ref][3][:tam]
            lo, hi = np.percentile(dif, 2.5), np.percentile(dif, 97.5)
            veredito = "equivalentes" if lo <= 0 <= hi else "diferenca significativa"
            P(f"{n} menos {ref}:")
            P(f"   {dif.mean():+.3f}  IC 95% [{lo:+.3f}; {hi:+.3f}]   -> {veredito}")
    P("=" * 84)

    txt = "\n".join(L)
    out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
    (out / "validacao_fronteiras.txt").write_text(txt, encoding="utf-8")
    print("\n" + txt)
    print(f"\nSalvo em {out / 'validacao_fronteiras.txt'}")


if __name__ == "__main__":
    main()
