import requests

api_key = "RGAPI-43c7d27b-0db0-4c8b-843c-0d0bba963fc0"

def get_match_list(puuid, region):
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?api_key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None
