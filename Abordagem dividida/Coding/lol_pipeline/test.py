import os, requests
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("RIOT_API_KEY")
puuid = "GCK12iqiY9OFiO69zdHaYz3fuGr7nWjt7yswjkfQumQ6NMU6bymU4dZZeaOw0Hzhww2qb_kBLugiZA"

resp = requests.get(
    f"https://br1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}",
    headers={"X-Riot-Token": key}
)
print(resp.status_code)
print(resp.json())