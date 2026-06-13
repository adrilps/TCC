import requests

api_key = "RGAPI-af8a2a12-97fa-4dd1-ba7b-0d039133974d"
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