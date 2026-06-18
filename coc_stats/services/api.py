import logging
import os
import time

import requests
from dotenv import load_dotenv


load_dotenv(override=True)
API_TOKEN = os.getenv("API_TOKEN")

MAX_ATTEMPTS = 2          # 1 retry on transient (timeout/connection) failures.
RETRY_BACKOFF_SECONDS = 2 # Worst case ~doubles a single attempt's cost (e.g. ~22s if both
                           # attempts time out), since a retry pays the full request timeout again.


def api_call(url: str) -> dict:
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json"}
    transient = None  # (message, cause) from the most recent retryable failure

    for attempt in range(MAX_ATTEMPTS):
        if attempt == 0:
            time.sleep(0.1)
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            message = f"HTTP Error: {response.status_code} - {response.text}"
            if response.status_code in (429, 500, 502, 503, 504):
                transient = (message, http_err)
            else:
                raise RuntimeError(message) from http_err
        except requests.exceptions.ConnectionError as conn_err:
            transient = ("Connection Error: Failed to connect to the Clash of Clans API.", conn_err)
        except requests.exceptions.Timeout as timeout_err:
            transient = ("Timeout Error: The Clash of Clans API took too long to respond.", timeout_err)
        except requests.exceptions.RequestException as req_err:
            raise RuntimeError(f"Unexpected Request Error: {req_err}") from req_err
        except ValueError:
            raise RuntimeError("JSON Decode Error: API did not return valid JSON.")

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(RETRY_BACKOFF_SECONDS)

    if transient is None:
        raise RuntimeError(f"API call failed: MAX_ATTEMPTS={MAX_ATTEMPTS} made no request attempts.")
    message, cause = transient
    raise RuntimeError(message) from cause


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
