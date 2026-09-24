"""
collect_elo.py — Coleta para um elo especifico, com semeadura direta.

Uso:
    py collect_elo.py DIAMOND            -> ate 2500 partidas, sem limite de tempo
    py collect_elo.py DIAMOND 2500 120   -> ate 2500 partidas ou 120 minutos

Diferencas em relacao a collect.py (que coleta Ouro por BFS):
  * os jogadores vem do endpoint de entries do proprio elo, entao nao ha
    requisicao de verificacao de rank por jogador (metade das chamadas);
  * progresso e CSV ficam separados por elo, de modo que uma coleta nunca
    interfere na outra.

Pode interromper com Ctrl+C: progresso e partidas sao salvos.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "lol_pipeline" / ".env")

import os
import requests

ELOS_VALIDOS = {"IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"}

elo = (sys.argv[1] if len(sys.argv) > 1 else "DIAMOND").upper()
if elo not in ELOS_VALIDOS:
    print(f"Elo invalido: {elo}. Use um de {sorted(ELOS_VALIDOS)}")
    sys.exit(1)

max_matches = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
minutos = float(sys.argv[3]) if len(sys.argv) > 3 else None

key = os.getenv("RIOT_API_KEY", "")
resp = requests.get("https://br1.api.riotgames.com/lol/status/v4/platform-data",
                    headers={"X-Riot-Token": key}, timeout=10)
if resp.status_code in (401, 403):
    print(f"CHAVE INVALIDA/EXPIRADA (HTTP {resp.status_code}). Atualize lol_pipeline/.env")
    sys.exit(2)

print(f"Chave OK. Coletando {elo} (ate {max_matches} partidas"
      + (f", limite de {minutos:.0f} min" if minutos else "") + ")...", flush=True)

from lol_pipeline.data.spider import run_spider
from lol_pipeline.config import PROJECT_ROOT

saida = PROJECT_ROOT / "dataset" / f"matches_{elo}.csv"

df = run_spider(
    tiers={elo},
    max_matches=max_matches,
    max_players=20000,
    minutos=minutos,
    elo=elo,
    out_csv=str(saida),
    semear_por_elo=True,
    desde_dias=21,      # so partidas recentes: evita jogadores inativos
    por_jogador=20,     # com o filtro de data, pedir mais e barato
)

print(f"\n=== Coleta {elo} ===")
print(f"Total de linhas: {len(df)}")
if len(df) and "patch" in df.columns:
    print(df["patch"].astype(str).value_counts().sort_index().to_string())
if len(df) and "puuid" in df.columns:
    print(f"Jogadores unicos: {df['puuid'].nunique()}")
print(f"Arquivo: {saida}")
