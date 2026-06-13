import os

# Riot API Key
RIOT_API_KEY = "RGAPI-142ead17-fb1f-4300-be7d-ebf28f9621c0"

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