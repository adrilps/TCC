"""
collect.py — Coleta nao interativa (BFS, mid lane, Ouro, BR1).

Uso (no Windows, a partir da pasta Coding):
    py collect.py            -> coleta ate 2500 novas partidas visitadas
    py collect.py 500        -> rodada menor

A chave e lida de lol_pipeline/.env (RIOT_API_KEY=...).
Pode interromper com Ctrl+C a qualquer momento: progresso, cache e
partidas ja coletadas sao salvos; a proxima execucao retoma de onde parou.
O CSV final fica em cache/matches.csv (dedup por match_id).
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "lol_pipeline" / ".env")

import os
import requests

key = os.getenv("RIOT_API_KEY", "")
resp = requests.get("https://br1.api.riotgames.com/lol/status/v4/platform-data",
                    headers={"X-Riot-Token": key}, timeout=10)
if resp.status_code in (401, 403):
    print(f"CHAVE INVALIDA/EXPIRADA (HTTP {resp.status_code}). Renove em developer.riotgames.com e atualize lol_pipeline/.env")
    sys.exit(2)
print(f"Chave OK (HTTP {resp.status_code}). Iniciando coleta...", flush=True)

from lol_pipeline.data.spider import run_spider

max_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
minutos = float(sys.argv[2]) if len(sys.argv) > 2 else None
if minutos:
    print(f"Limite de tempo: {minutos:.0f} minutos.", flush=True)

df = run_spider(max_matches=max_matches, max_players=20000, minutos=minutos)

print("\n=== Resumo da coleta ===")
print(f"Total de linhas no dataset: {len(df)}")
if "patch" in df.columns and len(df):
    print("Por patch:")
    print(df["patch"].astype(str).value_counts().sort_index().to_string())
