import os

# Riot API Key
RIOt#A#PI#_KEY = "RGA##PI-c12880e3-3579-4ed8-a648-56efde01b3b7"

# Target Player Settings
#GAME_NAME = "Hide on bush"
GAME_NAME = "ignacarious"
#TAG_LINE = "KR1"
TAG_LINE = "smo"
#ROUTE_REGION = "asia"  # Use 'americas' for BR/NA, 'europe' for EUW, 'asia' for KR/JP
ROUTE_REGION = "americas"

# Infrastructure Settings
DB_URI = "postgresql://postgres:mysecretpassword@localhost:5432/lol_analytics"

# API Endpoints
ACCOUNT_URL = f"https://{ROUTE_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id"
MATCH_HISTORY_URL = f"https://{ROUTE_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid"
MATCH_TIMELINE_URL = f"https://{ROUTE_REGION}.api.riotgames.com/lol/match/v5/matches"