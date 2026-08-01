"""
config.py — Central control panel for the LoL SHAP pipeline.
Change phase boundaries, features, or model hyperparameters here.
"""

# ── Phase feature definitions ─────────────────────────────────────────────────
# Phases are event-driven: early ends at first tower kill, mid ends at first
# Baron kill. EARLY_END_MIN / MID_END_MIN are fallbacks when those events don't
# occur by that time. Features are computed for the target mid-laner only.
PHASE_FEATURES = {
    "Early": [
        "early_cs_per_min", "early_vision_per_min", "early_deaths_per_min",
        "early_kill_participation", "early_damage_share",
        "early_solo_kills", "early_objective_proximity",
        "early_first_blood_involved",
    ],
    "Mid": [
        "mid_cs_per_min", "mid_vision_per_min", "mid_deaths_per_min",
        "mid_kill_participation", "mid_damage_share",
        "mid_solo_kills", "mid_objective_proximity",
    ],
    "Late": [
        "late_cs_per_min", "late_vision_per_min", "late_deaths_per_min",
        "late_kill_participation", "late_damage_share",
        "late_solo_kills", "late_objective_proximity",
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
OUTPUT_DIR = "outputs"

# ── Spider / BFS collector settings ──────────────────────────────────────────
REGION = "br1"                        # Riot platform region
REGION_ROUTING = "americas"           # Routing value for match-v5 endpoints
SEED_RIOT_ID = "folksdead#9116"       # BFS starting point (gameName#tagLine)
QUEUE_ID = 420                        # 420 = Ranked Solo/Duo
TARGET_ROLE = "MIDDLE"                # Riot API position string for mid lane
TARGET_TIERS = {"GOLD"}               # Rank tiers to accept (can add "PLATINUM" etc.)
MATCHES_PER_PLAYER = 5                # Max matches to pull per player (keep low for diversity)
MAX_MATCHES = 2000                    # Hard cap — spider stops when this is reached
MAX_PLAYERS_VISITED = 500             # Hard cap on unique players visited
RATE_LIMIT_CALLS = 100                # Riot dev key: 100 requests per 2 min
RATE_LIMIT_WINDOW = 121               # seconds (add 1s buffer)
CACHE_DIR = "cache"                   # Local cache directory (relative to project root)

# Phase time fallbacks in minutes (used when the trigger event hasn't occurred)
#   Early ends at first tower kill — fallback: EARLY_END_MIN
#   Mid ends at first Baron kill  — fallback: MID_END_MIN
EARLY_END_MIN = 14
MID_END_MIN = 25
