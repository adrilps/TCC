import os

# Riot API Key
RIOT_API_KEY = "RGAPI-ffdfe0f7-1250-4bb7-b49b-f1fd4240e4be"

# Target Player Settings
GAME_NAME = "ignacarious"
TAG_LINE = "smo"
ROUTE_REGION = "americas"  # Use 'americas' for BR/NA, 'europe' for EUW, 'asia' for KR/JP

# Infrastructure Settings
DB_URI = "postgresql://postgres:mysecretpassword@localhost:5432/lol_analytics"

# API Endpoints
ACCOUNT_URL = f"https://{ROUTE_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id"
MATCH_HISTORY_URL = f"https://{ROUTE_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid"
MATCH_TIMELINE_URL = f"https://{ROUTE_REGION}.api.riotgames.com/lol/match/v5/matches"