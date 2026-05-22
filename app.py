import logging
import os
import sys
from datetime import datetime, timedelta, timezone
import time

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request
from flask_migrate import Migrate
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from apscheduler.schedulers.background import BackgroundScheduler

from extensions import db
from help_functions import *

class ConsoleColorFormatter(logging.Formatter):
    RED = "\033[31m"
    RESET = "\033[0m"

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.ERROR and self._use_color():
            return f"{self.RED}{message}{self.RESET}"
        return message

    def _use_color(self):
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)
root_logger.handlers.clear()
handler = logging.StreamHandler()
handler.setFormatter(ConsoleColorFormatter(
    fmt='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%H:%M:%S'
))
root_logger.addHandler(handler)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

load_dotenv(override=True)

# 1. Server und Datenbank konfigurieren
app = Flask(__name__)

# Konstanten
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "coc_stats")
CLAN_TAG = os.getenv("CLAN_TAG", "#2QRC8998U")
API_TOKEN = os.getenv("API_TOKEN")

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not API_TOKEN:
    logging.warning("API_TOKEN is not set. Clash of Clans API calls will fail.")



db.init_app(app)

migrate = Migrate(app, db)

from databaseModels import * 






def api_call(url: str):
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }
    time.sleep(0.1)
    
    # The line `logging.debug(f"API Call URL: {url}")` is logging a debug message to the console or a
    # log file. This specific message includes the URL that is being used for an API call. The
    # `logging.debug()` function is used to provide detailed information for debugging purposes. In
    # this case, it helps track and monitor the API calls being made in the application.
    #logging.debug(f"API Call URL: {url}")
    
    try:
        # 1. Added a 10-second timeout to prevent hanging forever
        response = requests.get(url, headers=headers, timeout=10)
        
        # 2. This automatically raises an exception for 4xx and 5xx status codes
        response.raise_for_status()
        
        # 3. Return the parsed JSON and "None" for the error
        return response.json(), None

    # 4. Catch specific HTTP errors (like 403 Forbidden or 404 Not Found)
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"HTTP Error: {response.status_code} - {response.text}"
        logging.error(error_msg)
        return None, error_msg
        
    # 5. Catch connection issues (no internet, DNS failure)
    except requests.exceptions.ConnectionError:
        error_msg = "Connection Error: Failed to connect to the Clash of Clans API."
        logging.error(error_msg)
        return None, error_msg
        
    # 6. Catch timeouts
    except requests.exceptions.Timeout:
        error_msg = "Timeout Error: The Clash of Clans API took too long to respond."
        logging.error(error_msg)
        return None, error_msg
        
    # 7. Catch any other requests-related errors
    except requests.exceptions.RequestException as req_err:
        error_msg = f"Unexpected Request Error: {req_err}"
        logging.error(error_msg)
        return None, error_msg
        
    # 8. Catch cases where the API returns 200 OK, but the body isn't valid JSON
    except ValueError: 
        error_msg = "JSON Decode Error: API did not return valid JSON."
        logging.error(error_msg)
        return None, error_msg
    
    
    
def api_fetch_player_data(player_tag: str):
    player_url = f"https://api.clashofclans.com/v1/players/%23{player_tag.replace("#","")}"

    #logging.debug(f"Fetch Player Data")
    
    player_data, error = api_call(player_url)
    
    return player_data, error


def api_fetch_battlelog(player_tag: str):
    player_url = f"https://api.clashofclans.com/v1/players/%23{player_tag.replace("#","")}/battlelog"

    #logging.debug(f"Fetch Battle Log Data")
    
    player_data, error = api_call(player_url)
    
    return player_data, error


def api_fetch_league_group(group_tag: str, season_id: str, player_tag: str):
    player_url = f"https://api.clashofclans.com/v1/leaguegroup/%23{group_tag.replace("#","")}/{season_id}?playerTag=%23{player_tag.replace("#","")}"

    #logging.debug(f"Fetch League Groupe Data")
    
    group_data, error = api_call(player_url)
    
    return group_data, error


    

def api_fetch_clan_data(clan_tag: str):
    clan_url = f"https://api.clashofclans.com/v1/clans/%23{clan_tag.replace("#","")}"

    #logging.debug(f"Fetch Clan Data")
    
    clan_data, error = api_call(clan_url)
    
    return clan_data, error
    


def db_player_create_new(player_json):
    
    
    new_player = Player(
        tag = json_get(player_json, JSON_PLAYER_DATA.TAG),
        name = json_get(player_json, JSON_PLAYER_DATA.NAME),
        current_th = json_get(player_json, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
        in_clan = True,
        league_tier = json_get(player_json, JSON_PLAYER_DATA.LEAGUE_TIER.name, "Unranked")                       
        )
    logging.debug(f"Add new player: {new_player.name}")
    db.session.add(new_player)
    return new_player
        
def db_uptime_tracker_new(func_name: str, duration):
    new_uptime = UptimeTracker(
        function = func_name,
        duration = duration
    )
    db.session.add(new_uptime)        
        
def db_player_update(player_db, player_json):
    player_db.current_th = json_get(player_json, JSON_PLAYER_DATA.TOWN_HALL_LEVEL)
    player_db.name =  json_get(player_json, JSON_PLAYER_DATA.NAME)
    player_db.in_clan = True
    
    player_db.league_tier = json_get(player_json, JSON_PLAYER_DATA.LEAGUE_TIER.name, "Unranked")
    logging.debug(f"Updating player: {player_db.name}")
    return player_db     
        
def db_player_update_all_inactive():
    Player.query.update({Player.in_clan: False})
        
def db_ranked_week_get(group_tag: str, season_id : str, player_tag: str):
    return db.session.get(RankedWeek, (group_tag, season_id, player_tag))

def get_resource_amount(looted_resources, resource_name):
    """
    Searches a list of resource dictionaries for a specific name 
    and returns its amount.
    """
    for resource in looted_resources:
        if json_get(resource, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES_NAME) == resource_name:
            return json_get(resource, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES_AMOUNT)
            
    # Returns 0 if the resource name isn't found in the list
    return 0

def db_battle_log_get(player_tag, battle):
    
    player_tag = player_tag
    opponent_tag = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG)
    resources = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES)
        
    loot_gold = get_resource_amount(resources, "Gold")
    loot_elixir = get_resource_amount(resources, "Elixir")
    loot_dark_elixir = get_resource_amount(resources, "DarkElixir")
    
    return db.session.get(BattleLog, (player_tag, opponent_tag, loot_gold, loot_elixir,loot_dark_elixir))




def db_ranked_battle_log_create_new( attack, player_data, is_attack):
    opponent_tag_lookup = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG)
    opponent, error = api_fetch_player_data(opponent_tag_lookup)
    if error is not None:
        logging.error(f"Could not fetch opponent {opponent_tag_lookup}. Error: {error}")
        return 
    
    league_group_tag = json_get(player_data, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG)
    league_season_id = json_get(player_data, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID)
    player_tag  = json_get(player_data, JSON_PLAYER_DATA.TAG)
    opponent_th = json_get(opponent, JSON_PLAYER_DATA.TOWN_HALL_LEVEL)
    stars = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_STARS)
    destruction = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_DESTRUCTION)
    trophies = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_TROPHIES)
    opponent_name = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_NAME)
    opponent_tag = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG)
    time  = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_CREATION_TIME)
    
    if None ==  league_group_tag or None == league_season_id or None ==  player_tag or None ==  opponent_th or None ==  stars or None ==  destruction or None ==  trophies or None ==  opponent_name or None ==  opponent_tag or None ==  time:
        logging.error(f"Failed to get all parameters")
        return
    
    new_ranked_log = RankedBattleLog(
            league_group_tag = league_group_tag,
            league_season_id = league_season_id,
            player_tag = player_tag,
            opponent_th = opponent_th,
            attack = is_attack,
            stars = stars,
            percentage = destruction,
            trophies = trophies,
            opponent_tag = opponent_tag,
            opponent_name = opponent_name,
            time = parse_iso_datetime(time)
        )
    db.session.add(new_ranked_log)
    return new_ranked_log



def db_battle_log_create_new(player_tag, battle):
    player_tag = player_tag
    opponent_tag = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG,raise_on_missing=False)
    resources = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES,raise_on_missing=False)
    if(opponent_tag == None):
        return
        
    loot_gold = get_resource_amount(resources, "Gold")
    loot_elixir = get_resource_amount(resources, "Elixir")
    loot_dark_elixir = get_resource_amount(resources, "DarkElixir")
    
    attack = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_ATTACK)
    stars = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_STARS)
    percentage = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_DESTRUCTION)
    type = json_get(battle, JSON_BATTLE_LOG_DATA.ITEMS_BATTLE_TYPE)
    
    if None ==  opponent_tag or None == resources or None ==  loot_gold or None ==  loot_elixir or None ==  loot_dark_elixir or None ==  attack or None ==  stars or None ==  percentage or None ==  type:
        logging.warning(f"Failed to get all parameters")
        return
    
    new_battlelog = BattleLog(
        player_tag = player_tag,
        opponent_tag = opponent_tag,
        loot_gold = loot_gold,
        loot_elixir = loot_elixir,
        loot_dark_elixir = loot_dark_elixir,
        
        attack = attack,
        stars = stars,
        percentage = percentage,
        type = type 
        )
    db.session.add(new_battlelog)
    return new_battlelog


def db_ranked_battle_log_get(tag: str):
    return db.session.get(RankedBattleLog, tag)

def db_ranked_battle_log_get_by_opponent(opponent_tag: str, is_attack: bool):
    search_term = f"%{opponent_tag}%"
    return RankedBattleLog.query.filter(RankedBattleLog.attack == is_attack,  RankedBattleLog.opponent_tag.ilike(search_term)).first()

def db_ranked_battle_log_check(opponent_tag, attack, player_data, player_name, is_attack):
    if not db_ranked_battle_log_get_by_opponent(opponent_tag, is_attack):
            new_battlelog = db_ranked_battle_log_create_new(attack, player_data, is_attack)
            if new_battlelog is None:
                logging.warning(f"Skipped invalid ranked log attack: {is_attack} for player {player_name}")
                return
            
            logging.debug(
                f"Added Ranked Logs for attack: {is_attack} from {player_name}"
                f"against {json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_NAME, default='<unknown>', raise_on_missing=False)}"
            )
def db_ranked_battle_log_update( player_data: dict, league_group_data: dict):
    attack_logs = json_get(league_group_data, JSON_RANKED_GROUP_DATA.ATTACK_LOGS, default=[], raise_on_missing=False)
    defense_logs = json_get(league_group_data, JSON_RANKED_GROUP_DATA.DEFENSE_LOGS, default=[], raise_on_missing=False)

    player_name = json_get(player_data, JSON_PLAYER_DATA.NAME, default='<unknown>', raise_on_missing=False)

    
    for attack in attack_logs:
        opponent_tag = json_get(attack, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG, default=None, raise_on_missing=False)
        if not opponent_tag:
            logging.warning("Skipping attack log with missing opponent tag.")
            continue
        db_ranked_battle_log_check(opponent_tag, attack, player_data, player_name, True)
        
    for defense in defense_logs:
        opponent_tag = json_get(defense, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG, default=None, raise_on_missing=False)
        if not opponent_tag:
            logging.warning("Skipping attack log with missing opponent tag.")
            continue
        db_ranked_battle_log_check(opponent_tag, defense, player_data, player_name, False)
            


#JSON DONE
def db_ranked_week_create_new(league_group_tag, league_season_id, player_data: dict, league_group_data: dict):

        league_members = json_get(league_group_data, JSON_RANKED_GROUP_DATA.MEMBERS)
        player_tag = json_get(player_data, JSON_PLAYER_DATA.TAG)
        rank = get_member_rank_by_tag(league_members, player_tag)
        player_group_data = league_members[rank-1]
        
        trophies = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_TROPHIES)
        league_tier_name = json_get(player_data, JSON_PLAYER_DATA.LEAGUE_TIER.NAME)
        attack_wins = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT)
        attack_losses = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT)
        defense_wins = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_WIN_COUN)
        defense_losses = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_LOSE_COUNT)
        th_level = json_get(player_data, JSON_PLAYER_DATA.TOWN_HALL_LEVEL)
        
        if None == trophies or None == th_level or None == league_tier_name or None == attack_wins or None == attack_losses or None == defense_wins or None == defense_losses:
            logging.error(f"Failed to get all parameters")
            return
        
        # create new entry
        new_week = RankedWeek(
            league_group_tag=league_group_tag,
            league_season_id=league_season_id,
            player_tag=player_tag,
            trophies=trophies,
            rank=rank,
            start_day=get_last_monday(),
            end_day=get_next_monday(),
            max_attacks=get_weekly_attacks(league_tier_name),
            townhall=th_level,
            attack_wins=attack_wins,
            attack_losses=attack_losses,
            defense_wins=defense_wins,
            defense_losses=defense_losses,
            league_tier=league_tier_name
        )
        db.session.add(new_week)
        logging.debug(f"Added RankedWeek {new_week.league_group_tag}/{new_week.league_season_id}/{new_week.player_tag} for {player_data["name"]}")
        return new_week
    
    
#JSON DONE   
def db_ranked_week_update( ranked_week, player_data: dict, league_group_data: dict):
    
        league_members = json_get(league_group_data, JSON_RANKED_GROUP_DATA.MEMBERS)
        player_tag = json_get(player_data, JSON_PLAYER_DATA.TAG)
        rank = get_member_rank_by_tag(league_members, player_tag)
        player_group_data = league_members[rank-1]
        
        trophies = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_TROPHIES)
        attack_wins = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT)
        attack_losses = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT)
        defense_wins = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_WIN_COUN)
        defense_losses = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_LOSE_COUNT)
        
        if None == trophies or None == attack_wins or None == attack_losses or None == defense_wins or None == defense_losses:
            logging.error(f"Failed to get all parameters")
            return
        
        ranked_week.trophies=trophies
        ranked_week.rank=rank
        ranked_week.attack_wins=attack_wins
        ranked_week.attack_losses=attack_losses
        ranked_week.defense_wins=defense_wins
        ranked_week.defense_losses=defense_losses
        
        
        logging.debug(f"Updated RankedWeek {ranked_week.league_group_tag}/{ranked_week.league_season_id}/{ranked_week.player_tag} for {player_data["name"]}")
        return ranked_week

#JSON DONE
def db_player_get(tag: str):
    return db.session.get(Player, tag)

#JSON DONE
def db_player_get_all(in_clan:bool = True):
    # Return only players currently marked as in-clan (in_clan == True)
    return Player.query.filter(Player.in_clan == in_clan).all()


#JSON DONE
def clan_members_update():
    t0 = time.time()
    clan_data, error = api_fetch_clan_data(CLAN_TAG)
    if error is not None:
        logging.warning(f"Could not fetch Clan Data. Error: {error}")
        return

    member_list = json_get(clan_data, JSON_CLAN_DATA.MEMBER_LIST)
    if not member_list:
        logging.error(f"Could not find member_list")
        return

    with app.app_context():
        try:
            db_player_update_all_inactive()
            for player in member_list:
                player_tag = json_get(player, JSON_PLAYER_DATA.TAG)
                db_player = db_player_get(player_tag)
                if not db_player:
                    db_player_create_new(player)
                else:
                    db_player_update(db_player, player)
            t1 = time.time()
            duration = round(t1-t0, 2)
            logging.debug(f"Dauer: {duration} Sekunden.")         
            db_uptime_tracker_new(clan_members_update.__name__, duration)
            db.session.commit()
        except Exception as exc:
            logging.error(f"Failed to update player data: {exc}")
            db.session.rollback()     


#JSON DONE
def ranked_week_update():
    t0 = time.time()
    with app.app_context():
        db_players_in_clan = db_player_get_all();
        for db_player in db_players_in_clan:
            player_data, error = api_fetch_player_data(db_player.tag)
            if error is not None:
                logging.warning(f"Could not get {db_player.name}. Error: {error}")
                continue 
            
            season_id = json_get(player_data, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID)
            group_tag = None
            if season_id != 0:
                group_tag = json_get(player_data, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG)
            
            
            if not group_tag or not season_id:
                logging.debug(f"Ranked week could not be found for {db_player.name}.")
                continue
            
            ranked_group_data, error = api_fetch_league_group(group_tag, season_id, db_player.tag)
            if error is not None:
                logging.warning(f"Could not get {db_player.name} group data. Error: {error}")
                continue 
            
            try:      
                ranked_week = db_ranked_week_get(group_tag, season_id, db_player.tag)
                if not ranked_week:
                    db_ranked_week_create_new(group_tag, season_id, player_data, ranked_group_data)
                else:
                    db_ranked_week_update(ranked_week, player_data, ranked_group_data)
                
                db_ranked_battle_log_update(player_data, ranked_group_data)
                db.session.commit()
            except Exception as exc:
                logging.error(f"Failed to update ranked week: {exc}")
                db.session.rollback()
        t1 = time.time()
        duration = round(t1-t0, 2)
        logging.debug(f"Dauer: {duration} Sekunden.")         
        db_uptime_tracker_new(ranked_week_update.__name__, duration)
        db.session.commit()
        
                    
        
def battle_log_update():
    t0 = time.time()
    with app.app_context():
        db_players_in_clan = db_player_get_all();
        for db_player in db_players_in_clan:
            battle_log, error = api_fetch_battlelog(db_player.tag)
            if error is not None:
                logging.warning(f"Could not get {db_player.name}. Error: {error}")
                continue 
            
            try:  
                for battle in json_get(battle_log, JSON_BATTLE_LOG_DATA.ITEMS):
                    if not db_battle_log_get(db_player.tag, battle):
                        new_battlelog = db_battle_log_create_new(db_player.tag, battle)
                        if new_battlelog is not None:
                            logging.debug(f"Added Battle Logs for {db_player.name}")
                db.session.commit()
            except Exception as exc:
                logging.error(f"Failed to add battle log: {exc}")
                db.session.rollback()
            logging.debug(f"Updated Battle Log for {db_player.name}")
        t1 = time.time()
        duration = round(t1-t0, 2)
        logging.debug(f"Dauer: {duration} Sekunden.")         
        db_uptime_tracker_new(battle_log_update.__name__, duration)
        db.session.commit()
        
    
    
        
        
    
    







        




# 4. Das Web-Frontend (Dashboard)
@app.route('/')
def dashboard():
    # 1. URL-Parameter auslesen (falls nicht vorhanden, gibt es Standardwerte)
    filter_tag = request.args.get('player_tag', default='').strip()
    sort_by = request.args.get('sort', default='tag')

    # 2. Basis-Query für die Player Tabelle vorbereiten
    players_query = Player.query
    if filter_tag:
        search_term = f"%{filter_tag}%"
        players_query = players_query.filter(
            or_(Player.tag.ilike(search_term), Player.name.ilike(search_term))
        )

    if sort_by == 'name':
        players_query = players_query.order_by(Player.name.asc())
    elif sort_by == 'last_updated':
        players_query = players_query.order_by(Player.last_updated.desc())
    else:
        players_query = players_query.order_by(Player.tag.asc())

    players = players_query.options(
        selectinload(Player.ranked_weeks).selectinload(RankedWeek.battle_logs),
        selectinload(Player.battle_logs)
    ).all()

    selected_player = None
    battle_logs = []
    ranked_weeks = []
    uptime_trackers = []
    if filter_tag:
        selected_player = db.session.get(Player, filter_tag)
        if not selected_player:
            selected_player = Player.query.filter(Player.tag.ilike(filter_tag)).first()

        if selected_player:
            battle_logs = (
                BattleLog.query
                .filter(BattleLog.player_tag == selected_player.tag)
                .order_by(BattleLog.time.desc())
                .limit(100)
                .all()
            )
            ranked_weeks = (
                RankedWeek.query
                .filter(RankedWeek.player_tag == selected_player.tag)
                .order_by(RankedWeek.start_day.desc())
                .all()
            )
    
    # Fetch uptime tracker data for the overview
    uptime_tracker_objs = UptimeTracker.query.order_by(UptimeTracker.time.desc()).limit(100).all()
    uptime_trackers = [
        {
            'id': tracker.id,
            'function': tracker.function,
            'time': tracker.time.isoformat() if tracker.time else None
        }
        for tracker in uptime_tracker_objs
    ]

    return render_template(
        'dashboard.html',
        players=players,
        selected_player=selected_player,
        battle_logs=battle_logs,
        ranked_weeks=ranked_weeks,
        uptime_trackers=uptime_tracker_objs,
        uptime_trackers_json=uptime_trackers,
        current_tag=filter_tag,
        current_sort=sort_by,
    )

#Scheduler einrichten und starten
#scheduler = BackgroundScheduler()
#scheduler.add_job(func=clan_members_update, trigger="interval", minutes=1)
#scheduler.add_job(func=ranked_week_update, trigger="interval", minutes=2)
#scheduler.add_job(func=battle_log_update, trigger="interval", minutes=2)
#scheduler.start()


if __name__ == '__main__':
    #clan_members_update()
    #ranked_week_update()
    #battle_log_update()
    
    #print(JSON_PLAYER_DATA.TAG)
    
    #print(JSON_PLAYER_DATA.LEAGUE_TIER)
    #print(JSON_PLAYER_DATA.LEAGUE_TIER.NAME)
    
    #player, error= api_fetch_player_data("2JUQY0JP")
    #print(json_get(player, "tag"))

    # Webserver starten (use_reloader=False verhindert, dass der Scheduler beim Speichern doppelt startet)
    app.run(debug=True, use_reloader=False)