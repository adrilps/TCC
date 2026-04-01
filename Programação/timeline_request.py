import requests

api_key = "RGAPI-43c7d27b-0db0-4c8b-843c-0d0bba963fc0"
server = "BR1"
match_id = "3223766563"
region = "americas"

url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{server}_{match_id}/timeline?api_key={api_key}"
print(url)

response = requests.get(url)
if response.status_code == 200:
    match_data = response.json()
    print(match_data)
    with open("timeline_data.json", "w") as file:
        file.write(response.text)
else:
    print("error:", response.status_code, response.text)