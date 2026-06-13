import requests

api_key = "RGAPI-af8a2a12-97fa-4dd1-ba7b-0d039133974d"
server = "BR1"
match_id = "3223766563"
region = "americas"
puuid = "7AgGA9LTylxhg3FITJz7MVsA5O-UQS2Mn_CFJ9MPzl23d-ig6yOZ1MQdNPkbFJUgSk73DHZzStaDbA" #PUUID

url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids/?api_key={api_key}"
print(url)

response = requests.get(url)
if response.status_code == 200:
    match_data = response.json()
    print(match_data)
    with open("adc_match_list.json", "w") as file:
        file.write(response.text)
else:
    print("error:", response.status_code, response.text)