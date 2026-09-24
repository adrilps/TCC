"""
config.py — Central control panel for the LoL SHAP pipeline.
Change phase boundaries, features, or model hyperparameters here.
"""

import os
from pathlib import Path

# Project root = the folder that contains lol_pipeline/ (anchors all paths so
# running from any cwd never creates a second cache/outputs directory again).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Phase feature definitions ─────────────────────────────────────────────────
# Nota sobre participacao em abates: a formulacao em razao
# (participacoes / abates da equipe) foi testada e descartada — nao apresenta
# correlacao com o resultado (r = +0,01) porque a normalizacao pelo total da
# equipe elimina a diferenca entre participar muito e a equipe lutar pouco.
# A contagem por minuto preserva o sinal e eleva a AUC nas tres fases.
# Phases are event-driven: early ends at first tower kill, mid ends at first
# Baron kill. EARLY_END_MIN / MID_END_MIN are fallbacks when those events don't
# occur by that time. Features are computed for the target mid-laner only.
# ── Criterio de selecao das variaveis ─────────────────────────────────────────
# Todas as metricas sao atribuiveis ao proprio jogador. Foram descartadas:
#   participacao em abates e parcela de dano — razoes cujo denominador e do
#     time; ambas sem correlacao com o resultado (r = +0,01 e r = +0,00)
#   participacoes por minuto — conta abates que sairam, ou seja, mede o
#     desfecho da luta e nao a acao de quem lutou
#   abates da equipe por minuto — preditor forte (r = +0,35), mas resultado
#     coletivo; fora do escopo do trabalho por construcao
# Em seu lugar entram metricas de tentativa: dano causado a campeoes por
# minuto, participacao em trocas letais e presenca em combates.
# As tres fases usam o mesmo conjunto, para que as importancias sejam
# comparaveis entre elas.

PHASE_FEATURES = {
    "Early": [
        "early_cs_per_min", "early_vision_per_min", "early_deaths_per_min",
        "early_solo_kills", "early_dano_por_min", "early_trocas_por_min",
        "early_presenca_lutas_por_min", "early_objective_proximity",
    ],
    "Mid": [
        "mid_cs_per_min", "mid_vision_per_min", "mid_deaths_per_min",
        "mid_solo_kills", "mid_dano_por_min", "mid_trocas_por_min",
        "mid_presenca_lutas_por_min", "mid_objective_proximity",
    ],
    "Late": [
        "late_cs_per_min", "late_vision_per_min", "late_deaths_per_min",
        "late_solo_kills", "late_dano_por_min", "late_trocas_por_min",
        "late_presenca_lutas_por_min", "late_objective_proximity",
    ],
}

# ── Model hyperparameters ─────────────────────────────────────────────────────
XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "base_score": 0.5,  # explicit value avoids XGBoost 2.x / SHAP parse bug
}

# ── Data generation defaults ──────────────────────────────────────────────────
N_MATCHES = 5000
RANDOM_SEED = 42
TEST_SIZE = 0.2

# ── Output paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR = str(PROJECT_ROOT / "outputs")

# ── Spider / BFS collector settings ──────────────────────────────────────────
REGION = "br1"                        # Riot platform region
REGION_ROUTING = "americas"           # Routing value for match-v5 endpoints
SEED_RIOT_ID = "folksdead#2001"       # BFS starting point (gameName#tagLine)
QUEUE_ID = 420                        # 420 = Ranked Solo/Duo
TARGET_ROLE = "MIDDLE"                # Riot API position string for mid lane
TARGET_TIERS = {"GOLD"}               # Rank tiers to accept (can add "PLATINUM" etc.)
MATCHES_PER_PLAYER = 5                # Max matches to pull per player (keep low for diversity)
MAX_MATCHES = 2000                    # Hard cap — spider stops when this is reached
MAX_PLAYERS_VISITED = 500             # Hard cap on unique players visited
RATE_LIMIT_CALLS = 100                # Riot dev key: 100 requests per 2 min
RATE_LIMIT_WINDOW = 121               # seconds (add 1s buffer)
CACHE_DIR = os.getenv("LOL_CACHE_DIR", str(PROJECT_ROOT / "cache"))  # override p/ mover o cache p/ fora do OneDrive
MATCHES_CSV = str(PROJECT_ROOT / "dataset" / "matches.csv")  # dataset final (separado do cache bruto)

# Phase time fallbacks in minutes (used when the trigger event hasn't occurred)
#   Early ends at first tower kill — fallback: EARLY_END_MIN
#   Mid ends at first Baron kill  — fallback: MID_END_MIN
EARLY_END_MIN = 14
MID_END_MIN = 25
