from dotenv import load_dotenv
import requests

import time
import os

import logging
from error_definitions import *

load_dotenv(override=True)
API_TOKEN = os.getenv("API_TOKEN")

def api_call(url: str) -> dict:
    headers = {"Authorization": f"Bearer {API_TOKEN}","Accept": "application/json"
    }
    time.sleep(0.1)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    # 4. Catch specific HTTP errors (like 403 Forbidden or 404 Not Found)
    except requests.exceptions.HTTPError as http_err:
        raise APIError(f"HTTP Error: {response.status_code} - {response.text}") from http_err
    
        
    # 5. Catch connection issues (no internet, DNS failure)
    except requests.exceptions.ConnectionError:
        raise APIError("Connection Error: Failed to connect to the Clash of Clans API.") from http_err
    
    # 6. Catch timeouts
    except requests.exceptions.Timeout:
        raise APIError("Timeout Error: The Clash of Clans API took too long to respond.") from http_err
        
    # 7. Catch any other requests-related errors
    except requests.exceptions.RequestException as req_err:
        raise APIError(f"Unexpected Request Error: {req_err}") from http_err
        
    # 8. Catch cases where the API returns 200 OK, but the body isn't valid JSON
    except ValueError: 
        raise APIError("JSON Decode Error: API did not return valid JSON.") from http_err
    
    
def clean_tag(tag: str) -> str:
    return tag.replace("#", "").strip()
    
def api_fetch_player_data(player_tag: str):
    player_url = f"https://api.clashofclans.com/v1/players/%23{clean_tag(player_tag)}"

    player_data = api_call(player_url)
    
    return player_data

def api_fetch_raid_weekend(tag: str) -> str:
    raid_url = f"https://api.clashofclans.com/v1/clans/%23{clean_tag(tag)}/capitalraidseasons?limit=1"
    
    raid_data = api_call(raid_url)
    
    return raid_data


def api_fetch_battlelog(player_tag: str):
    battle_log_url = f"https://api.clashofclans.com/v1/players/%23{clean_tag(player_tag)}/battlelog"
    
    battle_log_data = api_call(battle_log_url)
    
    return battle_log_data


def api_fetch_league_group(group_tag: str, season_id: str, player_tag: str):
    league_group_url = f"https://api.clashofclans.com/v1/leaguegroup/%23{clean_tag(group_tag)}/{season_id}?playerTag=%23{clean_tag(player_tag)}"
    
    league_group_data = api_call(league_group_url)
    
    return league_group_data


    

def api_fetch_clan_data(clan_tag: str):
    clan_url = f"https://api.clashofclans.com/v1/clans/%23{clean_tag(clan_tag)}"
    
    clan_data = api_call(clan_url)
    
    return clan_data