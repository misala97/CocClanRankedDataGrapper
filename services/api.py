import logging
import os
import time

import requests
from dotenv import load_dotenv


load_dotenv(override=True)
API_TOKEN = os.getenv("API_TOKEN")


def api_call(url: str) -> dict:
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json"}
    time.sleep(0.1)
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        raise RuntimeError(f"HTTP Error: {response.status_code} - {response.text}") from http_err
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Connection Error: Failed to connect to the Clash of Clans API.")
    except requests.exceptions.Timeout:
        raise RuntimeError("Timeout Error: The Clash of Clans API took too long to respond.")
    except requests.exceptions.RequestException as req_err:
        raise RuntimeError(f"Unexpected Request Error: {req_err}") from req_err
    except ValueError:
        raise RuntimeError("JSON Decode Error: API did not return valid JSON.")


def clean_tag(tag: str) -> str:
    return tag.replace("#", "").strip()


def api_fetch_player_data(player_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/players/%23{clean_tag(player_tag)}")


def api_fetch_raid_weekend(tag: str):
    return api_call(f"https://api.clashofclans.com/v1/clans/%23{clean_tag(tag)}/capitalraidseasons?limit=1")


def api_fetch_battlelog(player_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/players/%23{clean_tag(player_tag)}/battlelog")


def api_fetch_league_group(group_tag: str, season_id: str, player_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/leaguegroup/%23{clean_tag(group_tag)}/{season_id}?playerTag=%23{clean_tag(player_tag)}")


def api_fetch_clan_data(clan_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/clans/%23{clean_tag(clan_tag)}")


def api_fetch_clan_war(clan_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/clans/%23{clean_tag(clan_tag)}/currentwar")


def api_fetch_cwl_league_group(clan_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/clans/%23{clean_tag(clan_tag)}/currentwar/leaguegroup")


def api_fetch_cwl_war(war_tag: str):
    return api_call(f"https://api.clashofclans.com/v1/clanwarleagues/wars/%23{clean_tag(war_tag)}")
