"""
rebuild_dataset.py — Reconstroi o dataset a partir do cache local, sem chamadas
a API. Usado apos correcoes na extracao de features (ex.: fronteiras de fase).

Uso:  py rebuild_dataset.py [saida.csv]
"""
import sys, json, hashlib
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lol_pipeline.config import CACHE_DIR, MATCHES_CSV, REGION_ROUTING
from lol_pipeline.data.spider import extract_features

cache = Path(CACHE_DIR)

def cached(url):
    f = cache / f"{hashlib.md5(url.encode()).hexdigest()}.json"
    if f.exists():
        try:
            return json.load(open(f))
        except Exception:
            return None
    return None

src = pd.read_csv(MATCHES_CSV)
pairs = src[["match_id", "puuid"]].drop_duplicates()
print(f"{len(pairs)} pares (match_id, puuid) no dataset atual")

rows, faltando, falhou = [], 0, 0
base = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches"
for i, (mid, puuid) in enumerate(pairs.itertuples(index=False), 1):
    info = cached(f"{base}/{mid}")
    tl   = cached(f"{base}/{mid}/timeline")
    if not info or not tl:
        faltando += 1
        continue
    row = extract_features(info, tl, puuid)
    if row:
        rows.append(row)
    else:
        falhou += 1
    if i % 400 == 0:
        print(f"  {i}/{len(pairs)}...", flush=True)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(MATCHES_CSV)
df = pd.DataFrame(rows)
df.to_csv(out, index=False)
print(f"\nreconstruido: {len(df)} linhas | sem cache: {faltando} | extracao falhou: {falhou}")
print(f"salvo em {out}")
