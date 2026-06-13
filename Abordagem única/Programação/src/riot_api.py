import requests
import time
import config

class RiotAPIClient:
    def __init__(self):
        self.api_key = config.RIOT_API_KEY

    def get_puuid(self, game_name, tag_line):
        """Retrieves an account's unique identification key wrapper."""
        url = f"{config.ACCOUNT_URL}/{game_name}/{tag_line}?api_key={self.api_key}"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"[API ERROR] Account locator failed with code {response.status_code}")
            return None
        return response.json().get("puuid")

    def get_recent_matches(self, puuid, count=50, queue_id=420):
        """Fetches list pointers referencing recent match records, filtered by queue."""
        # queue=420 is Ranked Solo/Duo. (440 is Flex, 400 is Normal Draft)
        url = f"{config.MATCH_HISTORY_URL}/{puuid}/ids?queue={queue_id}&start=0&count={count}&api_key={self.api_key}"
        
        response = requests.get(url)
        if response.status_code != 200:
            print(f"[API ERROR] Match index extraction failed with code {response.status_code}")
            return []
        return response.json()

    def get_match_timeline(self, match_id):
        """Requests high-fidelity live state data for targeted historical match."""
        url = f"{config.MATCH_TIMELINE_URL}/{match_id}/timeline?api_key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code == 429:
            print("[API WARNING] Rate limit tripped. Buffering request for 10 seconds...")
            time.sleep(10)
            return self.get_match_timeline(match_id)
            
        if response.status_code != 200:
            print(f"[API ERROR] Timeline query dropped for ID {match_id}. Status {response.status_code}")
            return None
            
        return response.json()
    
    def get_match_summary(self, match_id):
        """Requests high-level match summary (includes win/loss and total stats)."""
        # Note: This is the /matches/ endpoint, NOT the /matches/.../timeline endpoint
        url = f"{config.MATCH_TIMELINE_URL}/{match_id}?api_key={self.api_key}"
        response = requests.get(url)
        if response.status_code == 429:
            time.sleep(10)
            return self.get_match_summary(match_id)
        if response.status_code != 200:
            return None
        return response.json()