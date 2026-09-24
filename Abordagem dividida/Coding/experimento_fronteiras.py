"""
experimento_fronteiras.py — Determinacao empirica das fronteiras de fase.

Responde a duas perguntas que hoje o trabalho decide por convencao:
  (1) a segmentacao hibrida (evento com fallback de tempo) prediz melhor que
      um corte puramente temporal?
  (2) quais limiares de fallback funcionam melhor, em vez dos 14 e 25 minutos
      adotados por convencao?

PROTOCOLO CONTRA CIRCULARIDADE
  Escolher os limiares maximizando a AUC e depois reportar essa mesma AUC
  seria selecao sobre a metrica de validacao: o valor reportado seria o maximo
  de dezenas de tentativas, portanto otimista. Para evitar isso, os jogadores
  sao divididos em dois conjuntos disjuntos por PUUID:

    SELECAO   (70% dos jogadores) — usado para comparar as configuracoes
    VALIDACAO (30% dos jogadores) — nunca visto na escolha, usado so no fim

  A configuracao vencedora e escolhida olhando apenas a SELECAO; os numeros
  finais reportados vem da VALIDACAO. Assim a AUC final e uma estimativa
  honesta, nao um maximo.

Uso (no Windows, a partir da pasta Coding):
    py experimento_fronteiras.py

Saidas:
    outputs/experimento_fronteiras.csv       — todas as configuracoes
    outputs/experimento_fronteiras_resumo.txt — resumo pronto para o texto
"""
import sys, json, time, hashlib, itertools
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.config import (CACHE_DIR, MATCHES_CSV, REGION_ROUTING,
                                 XGB_PARAMS, TEST_SIZE, OUTPUT_DIR)
from lol_pipeline.data.spider import extract_features

# ── Grade de configuracoes ────────────────────────────────────────────────────
CAPS_EARLY = [10, 12, 14, 16, 18]
CAPS_MID   = [22, 25, 28, 31]
MODOS      = [("hibrido", True), ("tempo_fixo", False)]

METRICAS = ["cs_per_min", "vision_per_min", "deaths_per_min", "solo_kills",
            "dano_por_min", "trocas_por_min", "presenca_lutas_por_min",
            "objective_proximity"]
SEEDS_INTERNAS = (42, 7, 13)
PROP_SELECAO = 0.70
SEED_PARTICAO = 20260913

# Numeros conhecidos da configuracao atual, para validar o script antes de
# confiar no resto. Se estes nao baterem, algo divergiu e o resultado nao vale.
ESPERADO_LINHAS = 2045

cache = Path(CACHE_DIR)
base_url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches"


def do_cache(url):
    f = cache / f"{hashlib.md5(url.encode()).hexdigest()}.json"
    if not f.exists():
        return None
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return None


def extrair_todas_configuracoes(pares):
    """
    Le cada partida do cache UMA vez e calcula as features para todas as
    configuracoes. Carregar o JSON e a parte cara; reaproveitar a leitura
    torna o experimento viavel.
    """
    src = pd.read_csv(MATCHES_CSV)
    src["patch"] = src["patch"].astype(str)
    src = src[src["patch"] == "16.17"][["match_id", "puuid"]].drop_duplicates()
    print(f"{len(src)} partidas do patch 16.17 a processar")
    print(f"{len(pares)} configuracoes por partida\n")

    linhas = {k: [] for k in pares}
    t0 = time.time()
    for i, (mid, pu) in enumerate(src.itertuples(index=False), 1):
        info = do_cache(f"{base_url}/{mid}")
        tl = do_cache(f"{base_url}/{mid}/timeline")
        if not info or not tl:
            continue
        for chave, (modo, usar_ev, ce, cm) in pares.items():
            row = extract_features(info, tl, pu,
                                   early_cap_min=ce, mid_cap_min=cm,
                                   usar_eventos=usar_ev)
            if row:
                linhas[chave].append(row)
        if i % 250 == 0:
            dec = time.time() - t0
            print(f"  {i}/{len(src)} partidas — {dec/60:.1f} min decorridos, "
                  f"~{dec/i*(len(src)-i)/60:.1f} min restantes", flush=True)
    return {k: pd.DataFrame(v) for k, v in linhas.items()}


def auc_media(df, jogadores_permitidos):
    """AUC media por fase, restrita aos jogadores do conjunto informado."""
    sub0 = df[df["puuid"].isin(jogadores_permitidos)]
    out = {}
    for fase, pre in (("inicial", "early"), ("intermediaria", "mid"), ("final", "late")):
        s = sub0[sub0[f"{pre}_duration_min"] > 0].reset_index(drop=True)
        if len(s) < 200:
            out[fase] = (np.nan, len(s))
            continue
        feats = [f"{pre}_{m}" for m in METRICAS]
        X, y, g = s[feats], s["win"], s["puuid"]
        aucs = []
        for seed in SEEDS_INTERNAS:
            tr, te = next(GroupShuffleSplit(1, test_size=TEST_SIZE,
                                            random_state=seed).split(X, y, g))
            if y.iloc[te].nunique() < 2:
                continue
            m = xgb.XGBClassifier(**{**XGB_PARAMS, "random_state": seed})
            m.fit(X.iloc[tr], y.iloc[tr])
            aucs.append(roc_auc_score(y.iloc[te], m.predict_proba(X.iloc[te])[:, 1]))
        out[fase] = (float(np.mean(aucs)) if aucs else np.nan, len(s))
    return out


def main():
    pares = {}
    for (modo, usar_ev), ce, cm in itertools.product(MODOS, CAPS_EARLY, CAPS_MID):
        pares[(modo, ce, cm)] = (modo, usar_ev, ce, cm)

    dfs = extrair_todas_configuracoes(pares)

    # ── Verificacao de sanidade ──────────────────────────────────────────────
    atual = dfs[("hibrido", 14, 25)]
    print(f"\nVerificacao: configuracao atual (hibrido 14/25) gerou {len(atual)} linhas "
          f"(esperado {ESPERADO_LINHAS})")
    if abs(len(atual) - ESPERADO_LINHAS) > 5:
        print("  ATENCAO: divergencia em relacao ao dataset congelado. "
              "Verifique antes de usar estes resultados.")
    else:
        print("  OK — o script reproduz o conjunto de referencia.\n")

    # ── Particao de jogadores ────────────────────────────────────────────────
    jogadores = np.array(sorted(atual["puuid"].unique()))
    rng = np.random.default_rng(SEED_PARTICAO)
    rng.shuffle(jogadores)
    corte = int(len(jogadores) * PROP_SELECAO)
    selecao, validacao = set(jogadores[:corte]), set(jogadores[corte:])
    print(f"Jogadores: {len(selecao)} em SELECAO, {len(validacao)} em VALIDACAO\n")

    # ── Avaliacao em SELECAO ─────────────────────────────────────────────────
    registros = []
    for (modo, ce, cm), df in dfs.items():
        if len(df) == 0:
            continue
        r = auc_media(df, selecao)
        registros.append({
            "modo": modo, "cap_inicial": ce, "cap_intermediaria": cm,
            "n_total": len(df),
            "auc_sel_inicial": r["inicial"][0], "n_sel_inicial": r["inicial"][1],
            "auc_sel_intermediaria": r["intermediaria"][0], "n_sel_intermediaria": r["intermediaria"][1],
            "auc_sel_final": r["final"][0], "n_sel_final": r["final"][1],
        })
    tab = pd.DataFrame(registros)
    tab["auc_sel_media"] = tab[["auc_sel_inicial", "auc_sel_intermediaria", "auc_sel_final"]].mean(axis=1)
    tab = tab.sort_values("auc_sel_media", ascending=False).reset_index(drop=True)

    # ── Escolha por modo, olhando SO a selecao ───────────────────────────────
    escolhidas = {m: tab[tab.modo == m].iloc[0] for m in tab.modo.unique()}

    # ── Numeros finais em VALIDACAO ──────────────────────────────────────────
    finais = []
    alvos = {f"melhor_{m}": (m, int(e.cap_inicial), int(e.cap_intermediaria))
             for m, e in escolhidas.items()}
    alvos["atual_14_25"] = ("hibrido", 14, 25)
    for rotulo, chave in alvos.items():
        r = auc_media(dfs[chave], validacao)
        finais.append({
            "configuracao": rotulo, "modo": chave[0],
            "cap_inicial": chave[1], "cap_intermediaria": chave[2],
            "auc_val_inicial": r["inicial"][0],
            "auc_val_intermediaria": r["intermediaria"][0],
            "auc_val_final": r["final"][0],
            "n_val_inicial": r["inicial"][1],
            "n_val_intermediaria": r["intermediaria"][1],
            "n_val_final": r["final"][1],
        })
    fin = pd.DataFrame(finais)
    fin["auc_val_media"] = fin[["auc_val_inicial", "auc_val_intermediaria", "auc_val_final"]].mean(axis=1)

    out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out / "experimento_fronteiras.csv", index=False)

    linhas_txt = []
    P = linhas_txt.append
    P("=" * 78)
    P("DETERMINACAO EMPIRICA DAS FRONTEIRAS DE FASE")
    P("=" * 78)
    P("")
    P(f"Particao por jogador: {len(selecao)} em selecao / {len(validacao)} em validacao")
    P(f"Configuracoes avaliadas: {len(tab)}  ({len(CAPS_EARLY)}x{len(CAPS_MID)} limiares x 2 modos)")
    P("")
    P("-" * 78)
    P("MELHORES CONFIGURACOES NO CONJUNTO DE SELECAO (AUC media das 3 fases)")
    P("-" * 78)
    P(f"{'modo':<12}{'cap ini':>9}{'cap int':>9}{'inicial':>10}{'interm':>10}{'final':>10}{'media':>10}")
    for _, r in tab.head(12).iterrows():
        P(f"{r.modo:<12}{int(r.cap_inicial):>9}{int(r.cap_intermediaria):>9}"
          f"{r.auc_sel_inicial:>10.3f}{r.auc_sel_intermediaria:>10.3f}"
          f"{r.auc_sel_final:>10.3f}{r.auc_sel_media:>10.3f}")
    P("")
    P("Melhor de cada modo:")
    for m, e in escolhidas.items():
        P(f"  {m:<12} limiares {int(e.cap_inicial)}/{int(e.cap_intermediaria)}  "
          f"AUC media na selecao {e.auc_sel_media:.3f}")
    P("")
    P("-" * 78)
    P("RESULTADO FINAL — CONJUNTO DE VALIDACAO (nunca usado na escolha)")
    P("-" * 78)
    P(f"{'configuracao':<20}{'limiares':>12}{'inicial':>10}{'interm':>10}{'final':>10}{'media':>10}")
    for _, r in fin.sort_values("auc_val_media", ascending=False).iterrows():
        P(f"{r.configuracao:<20}{str(r.cap_inicial)+'/'+str(r.cap_intermediaria):>12}"
          f"{r.auc_val_inicial:>10.3f}{r.auc_val_intermediaria:>10.3f}"
          f"{r.auc_val_final:>10.3f}{r.auc_val_media:>10.3f}")
    P("")
    P(f"n na validacao: inicial {int(fin.n_val_inicial.iloc[0])}, "
      f"intermediaria {int(fin.n_val_intermediaria.iloc[0])}, "
      f"final {int(fin.n_val_final.iloc[0])}")
    P("")
    P("Leitura: comparar 'melhor_hibrido' com 'melhor_tempo_fixo' responde se a")
    P("segmentacao por evento vale a pena. Comparar 'melhor_hibrido' com")
    P("'atual_14_25' diz se os limiares por convencao custaram desempenho.")
    P("=" * 78)

    texto = "\n".join(linhas_txt)
    (out / "experimento_fronteiras_resumo.txt").write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"\nArquivos salvos em {out}")


if __name__ == "__main__":
    main()
