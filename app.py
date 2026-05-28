import logging
import os
import re
import secrets
import sys
import time
from functools import wraps
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, render_template, request, session, redirect, url_for
from flask_migrate import Migrate
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from extensions import db
from help_functions import *
from api_functions import *
from database_functions import *
import datetime as dt
from logging.handlers import RotatingFileHandler


def normalize_league_name(league_name):
    if not league_name:
        return None
    cleaned = re.sub(r'\s+', ' ', re.sub(r'\.', '', re.sub(r'league', '', league_name, flags=re.I))).strip()
    return cleaned.lower()


def get_league_thresholds(league_name):
    if not league_name:
        return None
    name = normalize_league_name(league_name)
    thresholds = {
        "skeleton 1": {"pro": 50, "dem": 0},
        "skeleton 2": {"pro": 50, "dem": 5},
        "skeleton 3": {"pro": 50, "dem": 5},
        "barbarian 4": {"pro": 50, "dem": 5},
        "barbarian 5": {"pro": 50, "dem": 5},
        "barbarian 6": {"pro": 50, "dem": 5},
        "archer 7": {"pro": 50, "dem": 5},
        "archer 8": {"pro": 50, "dem": 5},
        "archer 9": {"pro": 40, "dem": 10},
        "wizard 10": {"pro": 35, "dem": 10},
        "wizard 11": {"pro": 50, "dem": 10},
        "wizard 12": {"pro": 40, "dem": 10},
        "valkyrie 13": {"pro": 35, "dem": 10},
        "valkyrie 14": {"pro": 50, "dem": 10},
        "valkyrie 15": {"pro": 40, "dem": 10},
        "witch 16": {"pro": 35, "dem": 10},
        "witch 17": {"pro": 50, "dem": 10},
        "witch 18": {"pro": 40, "dem": 10},
        "golem 19": {"pro": 35, "dem": 10},
        "golem 20": {"pro": 50, "dem": 10},
        "golem 21": {"pro": 40, "dem": 10},
        "pekka 22": {"pro": 30, "dem": 10},
        "pekka 23": {"pro": 50, "dem": 10},
        "pekka 24": {"pro": 40, "dem": 10},
        "titan 25": {"pro": 30, "dem": 15},
        "titan 26": {"pro": 50, "dem": 15},
        "titan 27": {"pro": 40, "dem": 15},
        "dragon 28": {"pro": 30, "dem": 15},
        "dragon 29": {"pro": 25, "dem": 15},
        "dragon 30": {"pro": 25, "dem": 15},
        "electro 31": {"pro": 20, "dem": 15},
        "electro 32": {"pro": 20, "dem": 15},
        "electro 33": {"pro": 15, "dem": 15},
        "legend iii": {"pro": 5, "dem": 15},
        "legend ii": {"pro": 3, "dem": 15}
    }
    return thresholds.get(name)


# ==========================================
# 1. LOGGING CONFIGURATION
# ==========================================
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

# --- Root Logger (Console Output) ---
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()

console_handler = logging.StreamHandler()
console_handler.setFormatter(ConsoleColorFormatter(
    fmt='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%H:%M:%S'
))
root_logger.addHandler(console_handler)

# Silence noisy libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# --- File Loggers Setup ---
# Create a folder for logs if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

file_formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def setup_task_logger(name, log_file):
    """Creates a logger that writes to a file AND propagates to the console."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO) # Ensure we capture INFO and above for the tasks
    
    file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5)
    #file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

# Create the 3 specific loggers
battle_logger = setup_task_logger('battle_logs', 'logs/task_battle_logs.log')
ranked_logger = setup_task_logger('ranked_weeks', 'logs/task_ranked_weeks.log')
ranked_done_logger = setup_task_logger('ranked_done', 'logs/task_ranked_done.log')
clan_logger = setup_task_logger('clan_members', 'logs/task_clan_members.log')
raid_weekend_logger = setup_task_logger('raid_weekend', 'logs/raid_weekend.log')


# ==========================================
# 2. APP & DB SETUP
# ==========================================
load_dotenv(override=True)

LOCAL_TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))

def to_local(naive_utc):
    if naive_utc is None:
        return None
    return naive_utc.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL_TZ)

app = Flask(__name__)

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "coc_stats")
CLAN_TAG = os.getenv("CLAN_TAG", "#2QRC8998U")
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    root_logger.warning("SECRET_KEY not set in .env — using random key, sessions reset on restart.")
    _secret_key = secrets.token_hex(32)

app.config['SECRET_KEY'] = _secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if not API_TOKEN:
    root_logger.warning("API_TOKEN is not set. Clash of Clans API calls will fail.")

db.init_app(app)
migrate = Migrate(app, db)

from databaseModels import * 
db.configure_mappers()


# ==========================================
# 3. BACKGROUND TASKS
# ==========================================



def task_update_done_ranked_weeks():
    t0 = time.time()
    ranked_done_logger.info(f"Running task at {dt.datetime.now()}  ")
    with app.app_context():
        ranked_weeks_done = db_ranked_week_get_all_done()
        for week in ranked_weeks_done:
            #League Group
            try:
                group_data_api = api_fetch_league_group(week.league_group_tag, week.league_season_id, week.player_tag)
            except Exception as e:
                ranked_done_logger.warning(f"Could not fetch player group {week.player.name}. Error: {e}")
                continue

            #PLayer data
            try:
                player_api = api_fetch_player_data(week.player.tag)
            except Exception as e:
                ranked_done_logger.warning(f"Could not fetch player {week.player.name}. Error: {e}")
                continue


            #Ranked Woche anlegen
            try:
                tmp_ranked_week = create_db_ranked_week(week.league_group_tag, week.league_season_id, player_api, group_data_api)
                db_ranked_week_update(week, tmp_ranked_week, True)
            except Exception as e:
                ranked_done_logger.error(f"Failed to update ranked week for {week.player.name}: {e}")
                db.session.rollback() 
                continue
            db.session.commit()
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_done_ranked_weeks.__name__, duration))
        db.session.commit()    
            

        
def task_update_battle_logs():
    t0 = time.time()
    battle_logger.info(f"Running task at {dt.datetime.now()}  ")
    with app.app_context():
        db_players_in_clan = db_player_get_all()
        for db_player in db_players_in_clan:
            #Fetch Battlelog
            try:
                battle_log_api = api_fetch_battlelog(db_player.tag)
            except Exception as e:
                battle_logger.warning(f"Could not fetch player {db_player.name}. Error: {e}")
                continue
            
            #DB
            for battle_api in json_get(battle_log_api, JSON_BATTLE_LOG_DATA.ITEMS):
                try:
                    tmp_battle_log = create_db_battle_log(db_player, battle_api)
                    if tmp_battle_log.opponent_tag == None or tmp_battle_log.opponent_tag == "":
                        battle_logger.debug(f"Opponent player tag empty")
                        continue    
                    if not db_battle_log_get(db_player, battle_api):
                        db_battle_log_create_new(tmp_battle_log)
                except Exception as exc:
                    battle_logger.error(f"Failed to add battle log: {exc}")
                    db.session.rollback()
                    continue        
            db.session.commit()
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_battle_logs.__name__, duration))
        db.session.commit()            


def task_update_raid_weekend():
    t0 = time.time()
    raid_weekend_logger.info(f"Running task at {dt.datetime.now()}  ")
    with app.app_context():  
        #Raid Weekend data fetch
        try:
            raid_weekend_all_api = api_fetch_raid_weekend(CLAN_TAG)
            current_raid_weekend = json_get(raid_weekend_all_api, JSON_RAID_WEEKEND_DATA.ITEMS)[0]
        except Exception as e:
            raid_weekend_logger.warning(f"Could not fetch raid weekend. Error: {e}")
            return

        #Raid Weekend db
        try:
            tmp_raid_weekend = create_db_raid_weekend_from_api(current_raid_weekend)
            raid_weekend = db_raid_weekend_get(tmp_raid_weekend.startTime, tmp_raid_weekend.endTime)
            if not raid_weekend:
                    raid_weekend = db_raid_weekend_create_new(tmp_raid_weekend)
            else:
                db_raid_weekend_update(raid_weekend, tmp_raid_weekend)
        except Exception as e:
            raid_weekend_logger.error(f"Failed to update raid weekend: {e}")
            db.session.rollback() 
            return
        db.session.commit()
        
        #Attack Log
        try:
            attack_logs_api = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG)
        except Exception as e:
            raid_weekend_logger.warning(f"Could not get attack_log for Raid Weekend. Error: {e}")
            return  
        
        try:
            for attack_log_api in attack_logs_api:
                districts_api = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS)
                for district_api in districts_api:
                    attacks_api = json_get(district_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS, raise_on_missing=False)
                    if attacks_api is None:
                        continue
                    
                    sorted_attacks_api = sorted(attacks_api, key=lambda x: x['destructionPercent'])
                    previous_percent = 0
                    for attack_api in sorted_attacks_api:
                        current_percent = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_PERCENT)
                        # The percentage done in this specific attack
                        percentage_done = current_percent - previous_percent
                        player_tag = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_ATTACKER.TAG)
                        district_name = json_get(district_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_NAME)
                        stars = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_STARS)
                        defender_name = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DEFENDER.NAME)
                        defender_tag = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DEFENDER.TAG)
                        if current_percent == 100 and percentage_done < 15:
                            is_cleanup = True
                        else:
                            is_cleanup = False
                        previous_percent = current_percent
                        tmp_raid_weekend_log = create_db_raid_weekend_log(raid_weekend,player_tag,district_name,0,percentage_done,current_percent,stars,is_cleanup, defender_tag,defender_name)
                        raid_weekend_log = db_raid_weekend_log_get(raid_weekend, defender_tag, district_name,percentage_done,current_percent)
                        if not raid_weekend_log:
                                raid_weekend_log = db_raid_weekend_log_create_new(tmp_raid_weekend_log)
        except Exception as e:
            raid_weekend_logger.error(f"Failed to create raid weekend logs: {e}")
            db.session.rollback() 
            return
        db.session.commit()
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_raid_weekend.__name__, duration))
        db.session.commit()                     
        
        
        
def task_update_ranked_weeks():
    t0 = time.time()
    ranked_logger.info(f"Running task at {dt.datetime.now()}  ")
    with app.app_context():
        db_players_in_clan = db_player_get_all()
        for db_player in db_players_in_clan:
            #PLayer data
            try:
                player_api = api_fetch_player_data(db_player.tag)
            except Exception as e:
                ranked_logger.warning(f"Could not fetch player {db_player.name}. Error: {e}")
                continue
            
            #Season ID und Group tag
            try:
                season_id = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID)
                group_tag = None
                if season_id != 0:
                    group_tag = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG)
                else:
                    ranked_logger.debug(f"Ranked week not found for {db_player.name}")
                    continue    
            except Exception as e:
                ranked_logger.warning(f"Could not get season id or group tag for {db_player.name}. Error: {e}")
                continue    
            
            #League Group
            try:
                group_data_api = api_fetch_league_group(group_tag, season_id, db_player.tag)    
            except Exception as e:
                ranked_logger.warning(f"Could not fetch player group {db_player.name}. Error: {e}")
                continue
            
            #Ranked Woche anlegen
            try:      
                ranked_week = db_ranked_week_get(group_tag, season_id, db_player.tag)
                tmp_ranked_week = create_db_ranked_week(group_tag, season_id, player_api, group_data_api)
                if not ranked_week:
                    ranked_week = db_ranked_week_create_new(tmp_ranked_week)
                else:
                    db_ranked_week_update(ranked_week, tmp_ranked_week)
            except Exception as e:
                ranked_logger.error(f"Failed to update ranked week for {db_player.name}: {e}")
                db.session.rollback() 
                continue
            db.session.commit()
            
            #Ranked Battle Logs
            try:
                attack_logs_api = json_get(group_data_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS)
                defense_logs_api = json_get(group_data_api, JSON_RANKED_GROUP_DATA.DEFENSE_LOGS)
            except Exception as e:
                ranked_logger.warning(f"Could not get ranked logs for {db_player.name}. Error: {e}")
                continue
            
            #Attack Logs
            for attack_api in attack_logs_api:
                try:
                    opponent_tag = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG)
                    ranked_log_db = db_ranked_battle_log_get(ranked_week, opponent_tag, True)
                    
                    if not ranked_log_db:
                        opponent_api = api_fetch_player_data(opponent_tag)
                        db_opponent = create_db_player_from_api(opponent_api)
                        tmp_ranked_battle_log = create_db_ranked_battle_log(db_opponent, attack_api, player_api, True)
                        ranked_log_db = db_ranked_battle_log_create_new(tmp_ranked_battle_log)
                        ranked_logger.info(f"Adding new ranked attack battle log for  {db_player.name} ")
                except Exception as e:
                    db.session.rollback()    
                    ranked_logger.warning(f"Could not add ranked attack logs for {db_player.name}. Error: {e}")
                    continue
            db.session.commit()
            
            #Defense Logs
            for defense_api in defense_logs_api:
                try:
                    opponent_tag = json_get(defense_api, JSON_RANKED_GROUP_DATA.DEFENSE_LOGS_OPPONENT_TAG)
                    ranked_log_db = db_ranked_battle_log_get(ranked_week, opponent_tag, False)
                    
                    if not ranked_log_db:
                        opponent_api = api_fetch_player_data(opponent_tag)
                        db_opponent = create_db_player_from_api(opponent_api)
                        tmp_ranked_battle_log = create_db_ranked_battle_log(db_opponent, defense_api, player_api, False)
                        db_ranked_battle_log_create_new(tmp_ranked_battle_log)
                        ranked_logger.info(f"Adding new ranked defense log for  {db_player.name} ")
                except Exception as e:
                    db.session.rollback()    
                    ranked_logger.warning(f"Could not add ranked defense logs for {db_player.name}. Error: {e}")
                    continue
            db.session.commit()    
            
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_ranked_weeks.__name__, duration))
        db.session.commit()
                
        
def task_update_clan_members():
    t0 = time.time()
    clan_logger.info(f"Running task at {dt.datetime.now()}  ")
    #Fetch Api Data
    try:
        clan_api = api_fetch_clan_data(CLAN_TAG)
    except Exception as e:
        clan_logger.warning(f"Could not fetch clan data. Error: {e}")
        return

    try:
        member_list_api = json_get(clan_api, JSON_CLAN_DATA.MEMBER_LIST)
    except Exception as e:
        clan_logger.warning(f"Could not get member list. Error: {e}")
        return
    
    with app.app_context():
        try:
            db_player_update_all_inactive()
            
            for player_api in member_list_api:
                player_tag = json_get(player_api, JSON_PLAYER_DATA.TAG)
                db_player = db_player_get(player_tag)
                tmp_player = create_db_player_from_api(player_api)
                if not db_player:
                    clan_logger.info(f"Adding new player {tmp_player.name} to the clan ")
                    db_player = db_player_create_new(tmp_player)
                else:
                    db_player_update(db_player, tmp_player)
        except Exception as e:
            clan_logger.error(f"Failed to update player data: {e}")
            db.session.rollback() 
            return
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_clan_members.__name__, duration))
        db.session.commit()

# 4. Das Web-Frontend

# ==========================================
# PUBLIC WEBSITE (End-User Facing)
# ==========================================
@app.route('/')
def index():
    """Public homepage"""
    try:
        clan_data = api_fetch_clan_data(CLAN_TAG)
        clan_name = json_get(clan_data, JSON_CLAN_DATA.NAME, "Clan")
    except Exception as e:
        root_logger.warning(f"Could not fetch clan data for homepage: {e}")
        clan_name = "Our Clan"
    
    total_members = Player.query.count()
    now = dt.datetime.now(dt.timezone.utc)
    week_start_date = (now - dt.timedelta(days=now.weekday())).date()
    week_start = dt.datetime(week_start_date.year, week_start_date.month, week_start_date.day, tzinfo=dt.timezone.utc)

    battle_logs_this_week = BattleLog.query.filter(
        BattleLog.time >= week_start,
        BattleLog.attack == True
    ).count()
    ranked_battles_this_week = RankedBattleLog.query.filter(
        RankedBattleLog.ranked_week.has(RankedWeek.start_day >= week_start_date),
        RankedBattleLog.attack == True
    ).count()
    week_start_name = week_start.strftime('%A')

    return render_template(
        'index.html',
        clan_name=clan_name,
        total_members=total_members,
        battle_logs_this_week=battle_logs_this_week,
        ranked_battles_this_week=ranked_battles_this_week,
        week_start_name=week_start_name
    )


# ==========================================
# DEBUG DASHBOARD (Admin-only)
# ==========================================
@app.route('/debug')
def debug_dashboard():
    """Debug dashboard - moved to /debug route"""
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
        'debug_dashboard.html',
        players=players,
        selected_player=selected_player,
        battle_logs=battle_logs,
        ranked_weeks=ranked_weeks,
        uptime_trackers=uptime_tracker_objs,
        uptime_trackers_json=uptime_trackers,
        current_tag=filter_tag,
        current_sort=sort_by,
    )


# ==========================================
# FEATURE PAGES (Public Features)
# ==========================================
@app.route('/ranked')
def ranked_weeks_page():
    """Ranked Week Performance page with detailed battle breakdown"""
    # Get all unique ranked weeks
    distinct_weeks = db.session.query(
        RankedWeek.start_day,
        RankedWeek.end_day,
        RankedWeek.league_season_id
    ).distinct().order_by(RankedWeek.start_day.desc()).all()
    
    # Get selected week (default to most recent)
    selected_week_id = request.args.get('week_id', default=None)
    
    if not selected_week_id and distinct_weeks:
        # Default to most recent week
        selected_week_id = distinct_weeks[0].league_season_id
    
    # Build a full player list and include ranked week data for the selected week if present
    week_data = []
    all_players = Player.query.options(
        selectinload(Player.ranked_weeks).selectinload(RankedWeek.battle_logs)
    ).all()

    for player in all_players:
        ranked_week = None
        if selected_week_id:
            ranked_week = next(
                (rw for rw in player.ranked_weeks if rw.league_season_id == selected_week_id),
                None
            )

        league_tier = player.league_tier
        league_icon = player.league_icon
        rank = None
        trophies = None
        max_attacks = 0
        attack_logs = []
        defense_logs = []
        attack_details = []
        defense_details = []
        adj_attack_scores = []
        player_th = 0

        if ranked_week:
            league_tier = ranked_week.league_tier or league_tier
            league_icon = ranked_week.league_icon or league_icon
            rank = ranked_week.rank
            trophies = ranked_week.trophies
            max_attacks = ranked_week.max_attacks or 0
            player_th = ranked_week.townhall or player.current_th or 0

            def _th_multiplier(diff):
                if player_th >= 18:
                    if diff >= 0:   return 1.00
                    if diff == -1:  return 0.90
                    if diff <= -2:  return 0.75
                    return 0.01
                if player_th == 17:
                    if diff >= 1:   return 1.05
                    if diff == 0:   return 0.95
                    if diff == -1:  return 0.85
                    if diff <= -2:  return 0.75
                    return 0.01
                if diff >= 2:  return 1.15
                if diff == 1:  return 1.05
                if diff == 0:  return 0.95
                if diff == -1: return 0.85
                if diff == -2: return 0.75
                return 0.01

            for log in ranked_week.battle_logs:
                detail_entry = {
                    'opponent_name': log.opponent_name or log.opponent_tag or 'Unbekannt',
                    'opponent_th': log.opponent_th or '',
                    'stars': log.stars or 0,
                    'percentage': log.percentage or 0,
                }

                if log.attack is True or log.attack == 1:
                    attack_logs.append(log.stars or 0)
                    attack_details.append(detail_entry)
                    try:
                        opp_th = int(log.opponent_th)
                    except (TypeError, ValueError):
                        opp_th = player_th
                    diff = opp_th - player_th
                    adj = (log.stars or 0) * _th_multiplier(diff)
                    adj_attack_scores.append(adj)
                else:
                    defense_logs.append(log.stars or 0)
                    defense_details.append(detail_entry)

        att_count = len(attack_logs)
        def_count = len(defense_logs)

        att_avg = round(sum(attack_logs) / att_count, 2) if att_count else 0
        def_avg = round(sum(defense_logs) / def_count, 2) if def_count else 0

        att_0star = sum(1 for s in attack_logs if s == 0)
        att_1star = sum(1 for s in attack_logs if s == 1)
        att_2star = sum(1 for s in attack_logs if s == 2)
        att_3star = sum(1 for s in attack_logs if s == 3)

        def_0star = sum(1 for s in defense_logs if s == 0)
        def_1star = sum(1 for s in defense_logs if s == 1)
        def_2star = sum(1 for s in defense_logs if s == 2)
        def_3star = sum(1 for s in defense_logs if s == 3)

        is_active = ranked_week is not None
        missing_attacks = max(0, max_attacks - att_count)
        missing_text = f" ({missing_attacks} missing)" if missing_attacks > 0 else ""

        # TH-adjusted score: each attack weighted ±10% per TH level vs opponent,
        # divided by att_max so missing attacks directly tank the score.
        th_adj_score = round(sum(adj_attack_scores) / max_attacks, 3) if max_attacks > 0 else 0.0
        score_100 = min(round(th_adj_score * 100 / 3.45), 100)

        if not is_active:
            badge_class = 'badge-inactive'
            judge_label = 'Inactive'
            rank_status = 'inactive'
        elif score_100 >= 87:
            badge_class = 'badge-godlike'
            judge_label = 'Godlike' + missing_text
            rank_status = 'neutral'
        elif score_100 >= 80:
            badge_class = 'badge-dominant'
            judge_label = 'Dominant' + missing_text
            rank_status = 'neutral'
        elif score_100 >= 65:
            badge_class = 'badge-wow'
            judge_label = 'Very Good' + missing_text
            rank_status = 'neutral'
        elif score_100 >= 58:
            badge_class = 'badge-good'
            judge_label = 'Good' + missing_text
            rank_status = 'neutral'
        elif score_100 >= 43:
            badge_class = 'badge-warning'
            judge_label = 'Bad' + missing_text
            rank_status = 'neutral'
        elif score_100 >= 29:
            badge_class = 'badge-suck'
            judge_label = 'Disaster' + missing_text
            rank_status = 'neutral'
        else:
            badge_class = 'badge-useless'
            judge_label = 'Useless' + missing_text
            rank_status = 'neutral'

        thresholds = get_league_thresholds(league_tier)
        if is_active and thresholds and rank and rank > 0:
            if rank <= thresholds['pro']:
                rank_status = 'up'
            elif rank > (100 - thresholds['dem']):
                rank_status = 'down'
            else:
                rank_status = 'neutral'

        week_data.append({
            'player_name': player.name or player.tag,
            'player_tag': player.tag,
            'rank': rank,
            'trophies': trophies or 0,
            'league_tier': league_tier,
            'league_icon': league_icon,
            'att_count': att_count,
            'att_max': max_attacks,
            'att_0star': att_0star,
            'att_1star': att_1star,
            'att_2star': att_2star,
            'att_3star': att_3star,
            'att_avg': att_avg,
            'th_adj_score': th_adj_score,
            'score_100': score_100,
            'player_th': player_th or player.current_th or 0,
            'def_count': def_count,
            'def_max': max_attacks,
            'def_0star': def_0star,
            'def_1star': def_1star,
            'def_2star': def_2star,
            'def_3star': def_3star,
            'def_avg': def_avg,
            'attack_details': attack_details,
            'defense_details': defense_details,
            'badge_class': badge_class,
            'judge_label': judge_label,
            'is_active': is_active,
            'rank_status': rank_status
        })

    week_data.sort(key=lambda item: (item['rank'] or 9999, item['player_name'] or ''))

    # Build per-player history for the last 10 ranked weeks (oldest first for charts)
    last_10_seasons = [dw.league_season_id for dw in distinct_weeks[:10]]
    player_history = {}
    for player in all_players:
        history = []
        for season_id in reversed(last_10_seasons):
            dw = next((d for d in distinct_weeks if d.league_season_id == season_id), None)
            rw = next((r for r in player.ranked_weeks if r.league_season_id == season_id), None)
            if rw and dw:
                a_stars = [log.stars or 0 for log in rw.battle_logs if log.attack is True or log.attack == 1]
                d_stars = [log.stars or 0 for log in rw.battle_logs if not (log.attack is True or log.attack == 1)]
                att_c = len(a_stars)
                def_c = len(d_stars)
                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': att_c,
                    'att_max': rw.max_attacks or 0,
                    'att_avg': round(sum(a_stars) / att_c, 2) if att_c else 0,
                    'def_count': def_c,
                    'def_avg': round(sum(d_stars) / def_c, 2) if def_c else 0,
                    'trophies': rw.trophies or 0,
                    'rank': rw.rank,
                })
        if history:
            player_history[player.tag] = history

    # Get selected week info for display
    selected_week_info = None
    if selected_week_id:
        selected_week_info = next((w for w in distinct_weeks if w.league_season_id == selected_week_id), None)

    return render_template(
        'ranked_weeks.html',
        distinct_weeks=distinct_weeks,
        selected_week_id=selected_week_id,
        selected_week_info=selected_week_info,
        week_data=week_data,
        player_history=player_history,
    )


@app.route('/raid')
def raid_weekend_page():
    all_raids = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).all()

    selected_id = request.args.get('raid_id', type=int)
    if not selected_id and all_raids:
        selected_id = all_raids[0].id

    selected_raid = RaidWeekend.query.filter_by(id=selected_id).first() if selected_id else None

    player_data = []
    total_log_attacks = 0
    cleanup_count = 0
    top_finisher = None

    if selected_raid:
        logs = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == selected_raid.id)
            .options(selectinload(RaidWeekendLog.player))
            .all()
        )

        player_map = {}
        for log in logs:
            tag = log.playerTag
            if tag not in player_map:
                player_map[tag] = {
                    'player_name': log.player.name if log.player else tag,
                    'player_tag': tag,
                    'att_count': 0,
                    'cleanup_count': 0,
                    'total_loot': 0,
                    'avg_loot': 0,
                    'finishes': 0,
                    'attack_logs': [],
                }
            p = player_map[tag]
            p['att_count'] += 1
            if log.isCleanUp:
                p['cleanup_count'] += 1
            if log.percentageTotal == 100:
                p['finishes'] += 1
            p['attack_logs'].append({
                'district_name': log.districtName or '—',
                'stars': log.stars or 0,
                'percentage': log.percentage or 0,
                'percentage_total': log.percentageTotal or 0,
                'loot': 0,
                'is_clean_up': bool(log.isCleanUp),
                'defender_name': log.defenderName or '—',
                'defender_tag': log.defenderTag or '—',
            })

        for p in player_map.values():
            non_cleanup = [l['percentage'] for l in p['attack_logs'] if not l['is_clean_up']]
            p['avg_pct'] = round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0

        # Build career stats across all raid weekends in one pass
        total_raids_count = len(all_raids)
        all_career_logs = RaidWeekendLog.query.all()
        career_raw = {}
        for log in all_career_logs:
            tag = log.playerTag
            if tag not in career_raw:
                career_raw[tag] = {'raid_ids': set(), 'non_cleanup_pcts': [], 'career_finishes': 0}
            career_raw[tag]['raid_ids'].add(log.raid_weekend_id)
            if log.percentageTotal == 100:
                career_raw[tag]['career_finishes'] += 1
            if not log.isCleanUp:
                career_raw[tag]['non_cleanup_pcts'].append(log.percentage or 0)

        for p in player_map.values():
            tag = p['player_tag']
            c = career_raw.get(tag, {})
            raid_ids = c.get('raid_ids', set())
            non_cleanup = c.get('non_cleanup_pcts', [])
            p['participation'] = f"{len(raid_ids)}/{total_raids_count}"
            p['career_avg_pct'] = round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0
            p['career_finishes'] = c.get('career_finishes', 0)

        player_data = sorted(player_map.values(), key=lambda x: x['att_count'], reverse=True)
        total_log_attacks = sum(p['att_count'] for p in player_data)
        cleanup_count = sum(p['cleanup_count'] for p in player_data)

        if player_data:
            best = max(player_data, key=lambda x: x['finishes'])
            top_finisher = best if best['finishes'] > 0 else None

    raid_options = []
    for r in all_raids:
        start = r.startTime.strftime('%d.%m.%Y') if r.startTime else '?'
        end = r.endTime.strftime('%d.%m.%Y') if r.endTime else '?'
        raid_options.append({'id': r.id, 'label': f"{start} – {end}"})

    return render_template(
        'raid_weekend.html',
        raid_options=raid_options,
        selected_raid=selected_raid,
        selected_id=selected_id,
        player_data=player_data,
        total_log_attacks=total_log_attacks,
        cleanup_count=cleanup_count,
        top_finisher=top_finisher,
    )


@app.route('/battles')
def battle_history_page():
    """Battle History page"""
    selected_type = request.args.get('type', 'all')
    selected_week_str = request.args.get('week', None)

    now = dt.datetime.now(dt.timezone.utc)
    current_week_start = (now - dt.timedelta(days=now.weekday())).date()

    is_all_time = (selected_week_str == 'all')

    if not is_all_time:
        if selected_week_str:
            try:
                week_start = dt.date.fromisoformat(selected_week_str)
                week_start = week_start - dt.timedelta(days=week_start.weekday())
            except ValueError:
                week_start = current_week_start
        else:
            week_start = current_week_start
        week_end = week_start + dt.timedelta(days=6)
        week_start_dt = dt.datetime(week_start.year, week_start.month, week_start.day, tzinfo=dt.timezone.utc)
        next_monday_dt = week_start_dt + dt.timedelta(days=7)

    oldest = (
        BattleLog.query
        .filter(BattleLog.attack == True)
        .order_by(BattleLog.time.asc())
        .first()
    )
    available_weeks = []
    all_time_label = 'All Time'
    if oldest and oldest.time:
        min_date = oldest.time.date()
        min_monday = min_date - dt.timedelta(days=min_date.weekday())
        all_time_label = f"All Time – since {min_monday.strftime('%d.%m.%Y')}"
        w = min_monday
        while w <= current_week_start:
            wend = w + dt.timedelta(days=6)
            available_weeks.append({
                'start': w.isoformat(),
                'label': f"{w.strftime('%d.%m.%Y')} – {wend.strftime('%d.%m.%Y')}"
            })
            w += dt.timedelta(days=7)
        available_weeks.reverse()
        available_weeks.insert(0, {'start': 'all', 'label': all_time_label})

    if is_all_time:
        base_q = BattleLog.query.filter(BattleLog.attack == True)
    else:
        base_q = BattleLog.query.filter(
            BattleLog.attack == True,
            BattleLog.time >= week_start_dt,
            BattleLog.time < next_monday_dt,
        )
    if selected_type != 'all':
        base_q = base_q.filter(BattleLog.type == selected_type)

    attacks = base_q.options(selectinload(BattleLog.player)).all()

    # When a player first joins, the poller bulk-imports their entire recent
    # battle history in a single run (all within seconds of each other).
    # Those logs are noise and should be excluded. The poller runs every 5 min,
    # so anything within a 2-minute window of the player's very first log
    # is part of that initial import. New legitimate battles arrive no earlier
    # than the next poll cycle (5+ min later) and are kept.
    from sqlalchemy import func as sa_func
    first_log_time = dict(
        db.session.query(BattleLog.player_tag, sa_func.min(BattleLog.time))
        .group_by(BattleLog.player_tag)
        .all()
    )
    import_window = dt.timedelta(minutes=2)

    attacks = [
        b for b in attacks
        if not (b.time and first_log_time.get(b.player_tag) and
                b.time <= first_log_time[b.player_tag] + import_window)
    ]

    total_attacks = len(attacks)
    total_gold    = sum(b.loot_gold or 0 for b in attacks)
    total_elixir  = sum(b.loot_elixir or 0 for b in attacks)
    total_dark    = sum(b.loot_dark_elixir or 0 for b in attacks)

    player_map = {}
    for b in attacks:
        tag = b.player_tag
        if tag not in player_map:
            player_map[tag] = {
                'player_name': b.player.name if b.player else b.player_tag,
                'player_tag': tag,
                'att_count': 0,
                'total_gold': 0, 'total_elixir': 0, 'total_dark': 0,
                'attack_logs': [],
            }
        s = player_map[tag]
        if b.player:
            s['player_name'] = b.player.name
        stars = min(b.stars or 0, 3)
        s['att_count'] += 1
        s['total_gold'] += b.loot_gold or 0
        s['total_elixir'] += b.loot_elixir or 0
        s['total_dark'] += b.loot_dark_elixir or 0
        local_time = to_local(b.time)
        s['attack_logs'].append({
            'time': local_time.strftime('%d.%m.%y %H:%M') if local_time else '–',
            'time_sort': local_time.isoformat() if local_time else '',
            'opponent_tag': b.opponent_tag or '–',
            'stars': stars,
            'percentage': b.percentage or 0,
            'gold': b.loot_gold or 0,
            'elixir': b.loot_elixir or 0,
            'dark': b.loot_dark_elixir or 0,
        })

    player_data = []
    for s in player_map.values():
        player_data.append({
            'player_name': s['player_name'],
            'player_tag': s['player_tag'],
            'att_count': s['att_count'],
            'total_gold': s['total_gold'],
            'total_elixir': s['total_elixir'],
            'total_dark': s['total_dark'],
            'attack_logs': s['attack_logs'],
        })

    player_data.sort(key=lambda x: x['att_count'], reverse=True)
    top_by_attacks = sorted(player_data, key=lambda x: x['att_count'], reverse=True)[:10]

    return render_template(
        'battle_history.html',
        available_weeks=available_weeks,
        selected_week_start='all' if is_all_time else week_start.isoformat(),
        current_week_start=current_week_start.isoformat(),
        selected_type=selected_type,
        week_label=all_time_label if is_all_time else f"{week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}",
        total_attacks=total_attacks,
        total_gold=total_gold,
        total_elixir=total_elixir,
        total_dark=total_dark,
        top_by_attacks=top_by_attacks,
        player_data=player_data,
    )

def calculate_activity_score(player_tag):
    now = dt.datetime.now(dt.timezone.utc)

    # Ranked: active in last 4 distinct seasons
    last_4 = (db.session.query(RankedWeek.league_season_id)
              .distinct().order_by(RankedWeek.league_season_id.desc()).limit(4).all())
    last_4_ids = [r.league_season_id for r in last_4]
    active_seasons = (RankedWeek.query
                      .filter(RankedWeek.player_tag == player_tag,
                              RankedWeek.league_season_id.in_(last_4_ids))
                      .count()) if last_4_ids else 0
    total_seasons = len(last_4_ids)
    ranked_score = round(40 * active_seasons / total_seasons) if total_seasons else 0

    # Battle: attacks in last 7 days
    week_ago = now - dt.timedelta(days=7)
    battles_7d = (BattleLog.query
                  .filter(BattleLog.player_tag == player_tag,
                          BattleLog.attack == True,
                          BattleLog.time >= week_ago)
                  .count())
    battle_score = min(30, battles_7d * 6)

    # Raid: participated in last 3 raid weekends
    last_3_raids = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).limit(3).all()
    last_3_ids = [r.id for r in last_3_raids]
    raids_participated = (RaidWeekendLog.query
                          .filter(RaidWeekendLog.playerTag == player_tag,
                                  RaidWeekendLog.raid_weekend_id.in_(last_3_ids))
                          .with_entities(RaidWeekendLog.raid_weekend_id)
                          .distinct().count()) if last_3_ids else 0
    total_raid_windows = len(last_3_ids)
    raid_score = round(30 * raids_participated / total_raid_windows) if total_raid_windows else 0

    total = ranked_score + battle_score + raid_score
    if total >= 80:
        label, color = 'Active', 'green'
    elif total >= 50:
        label, color = 'Regular', 'blue'
    elif total >= 20:
        label, color = 'Casual', 'accent'
    else:
        label, color = 'Inactive', 'red'

    return {
        'score': total,
        'label': label,
        'label_color': color,
        'ranked_score': ranked_score, 'ranked_max': 40,
        'ranked_detail': f'{active_seasons} of last {total_seasons} ranked seasons active',
        'battle_score': battle_score, 'battle_max': 30,
        'battle_detail': f'{battles_7d} attacks in last 7 days (6 pts each, capped at 5)',
        'raid_score': raid_score, 'raid_max': 30,
        'raid_detail': f'{raids_participated} of last {total_raid_windows} raid weekends participated',
    }


@app.route('/player/<tag>')
def player_profile(tag):
    actual_tag = '#' + tag
    player = db_player_get(actual_tag)
    if not player:
        return render_template('player_profile.html', player=None, player_tag=actual_tag), 404

    activity = calculate_activity_score(actual_tag)

    # Ranked history (last 10 weeks)
    ranked_weeks_q = (RankedWeek.query
                      .filter(RankedWeek.player_tag == actual_tag)
                      .order_by(RankedWeek.start_day.desc())
                      .limit(10)
                      .options(selectinload(RankedWeek.battle_logs))
                      .all())
    ranked_history = []
    for rw in ranked_weeks_q:
        a_logs = [l for l in rw.battle_logs if l.attack is True or l.attack == 1]
        d_logs = [l for l in rw.battle_logs if not (l.attack is True or l.attack == 1)]
        a_stars = [l.stars or 0 for l in a_logs]
        d_stars = [l.stars or 0 for l in d_logs]
        ranked_history.append({
            'start_day': rw.start_day.strftime('%d.%m.%y') if rw.start_day else '—',
            'end_day': rw.end_day.strftime('%d.%m.%y') if rw.end_day else '—',
            'league_tier': rw.league_tier or '—',
            'rank': rw.rank,
            'trophies': rw.trophies or 0,
            'att_count': len(a_logs), 'att_max': rw.max_attacks or 0,
            'att_avg': round(sum(a_stars) / len(a_stars), 2) if a_stars else 0,
            'def_count': len(d_logs),
            'def_avg': round(sum(d_stars) / len(d_stars), 2) if d_stars else 0,
            'is_done': bool(rw.is_done),
        })

    # Recent battles (last 20)
    recent_battles_q = (BattleLog.query
                        .filter(BattleLog.player_tag == actual_tag)
                        .order_by(BattleLog.time.desc())
                        .limit(20)
                        .all())
    battle_history = []
    for b in recent_battles_q:
        local_time = to_local(b.time)
        battle_history.append({
            'time': local_time.strftime('%d.%m.%y %H:%M') if local_time else '—',
            'opponent_tag': b.opponent_tag or '—',
            'stars': min(b.stars or 0, 3),
            'percentage': b.percentage or 0,
            'gold': b.loot_gold or 0,
            'elixir': b.loot_elixir or 0,
            'dark': b.loot_dark_elixir or 0,
            'type': b.type or '—',
            'attack': bool(b.attack),
        })

    # Raid history (all raids, queried efficiently)
    player_raid_logs = RaidWeekendLog.query.filter(RaidWeekendLog.playerTag == actual_tag).all()
    raid_logs_by_id = {}
    for l in player_raid_logs:
        raid_logs_by_id.setdefault(l.raid_weekend_id, []).append(l)

    all_raids = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).all()
    raid_history = []
    for r in all_raids:
        logs = raid_logs_by_id.get(r.id, [])
        non_cleanup = [l.percentage for l in logs if not l.isCleanUp and l.percentage is not None]
        raid_history.append({
            'start': r.startTime.strftime('%d.%m.%Y') if r.startTime else '—',
            'end': r.endTime.strftime('%d.%m.%Y') if r.endTime else '—',
            'participated': len(logs) > 0,
            'att_count': len(logs),
            'avg_pct': round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0,
            'finishes': sum(1 for l in logs if l.percentageTotal == 100),
            'cleanups': sum(1 for l in logs if l.isCleanUp),
        })

    return render_template('player_profile.html',
                           player=player,
                           activity=activity,
                           ranked_history=ranked_history,
                           battle_history=battle_history,
                           raid_history=raid_history)


def require_admin_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_hub'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user_ok = ADMIN_USER and secrets.compare_digest(username.encode(), ADMIN_USER.encode())
        pass_ok = ADMIN_PASS and secrets.compare_digest(password.encode(), ADMIN_PASS.encode())
        if user_ok and pass_ok:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_hub'))
        error = 'Invalid username or password.'

    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))


@app.route('/admin')
@require_admin_login
def admin_hub():
    from collections import defaultdict

    days = request.args.get('days', 7, type=int)
    if days not in [1, 7, 14, 30]:
        days = 7

    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    trackers = UptimeTracker.query.filter(
        UptimeTracker.time >= cutoff
    ).order_by(UptimeTracker.time.asc()).all()

    by_function = defaultdict(list)
    for t in trackers:
        try:
            dur = float(t.duration) if t.duration else 0.0
        except (ValueError, TypeError):
            dur = 0.0
        by_function[t.function].append({
            'time': t.time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'duration': dur,
        })

    function_stats = {}
    now_naive = dt.datetime.utcnow()

    for fn, runs in by_function.items():
        durations = [r['duration'] for r in runs]
        avg_dur = round(sum(durations) / len(durations), 2) if durations else 0
        max_dur = round(max(durations), 2) if durations else 0

        gaps_minutes = []
        for i in range(1, len(runs)):
            t1 = dt.datetime.strptime(runs[i - 1]['time'], '%Y-%m-%dT%H:%M:%SZ')
            t2 = dt.datetime.strptime(runs[i]['time'], '%Y-%m-%dT%H:%M:%SZ')
            gaps_minutes.append((t2 - t1).total_seconds() / 60)

        sorted_gaps = sorted(gaps_minutes)
        median_gap = sorted_gaps[len(sorted_gaps) // 2] if sorted_gaps else None
        max_gap = max(gaps_minutes) if gaps_minutes else None

        gap_events = []
        if median_gap and len(runs) > 1:
            for i in range(1, len(runs)):
                t1 = dt.datetime.strptime(runs[i - 1]['time'], '%Y-%m-%dT%H:%M:%SZ')
                t2 = dt.datetime.strptime(runs[i]['time'], '%Y-%m-%dT%H:%M:%SZ')
                gap_min = (t2 - t1).total_seconds() / 60
                if gap_min > median_gap * 2.5:
                    gap_events.append({
                        'start': runs[i - 1]['time'],
                        'end': runs[i]['time'],
                        'duration_min': round(gap_min, 1),
                    })

        last_run_str = runs[-1]['time'] if runs else None
        status = 'unknown'
        minutes_since = None
        if last_run_str:
            last_run_dt = dt.datetime.strptime(last_run_str, '%Y-%m-%dT%H:%M:%SZ')
            minutes_since = round((now_naive - last_run_dt).total_seconds() / 60, 1)
            if median_gap:
                if minutes_since > median_gap * 2.5:
                    status = 'down'
                elif minutes_since > median_gap * 1.5:
                    status = 'warning'
                else:
                    status = 'up'
            else:
                status = 'up' if minutes_since < 120 else 'warning'

        function_stats[fn] = {
            'count': len(runs),
            'avg_duration': avg_dur,
            'max_duration': max_dur,
            'median_gap': round(median_gap, 1) if median_gap else None,
            'max_gap': round(max_gap, 1) if max_gap else None,
            'last_run': last_run_str,
            'minutes_since': minutes_since,
            'status': status,
            'gap_events': gap_events,
        }

    return render_template(
        'admin_hub.html',
        by_function=dict(by_function),
        function_stats=function_stats,
        selected_days=days,
    )


# ==========================================
# PUB QUIZ
# ==========================================

def _team_scores(team):
    r1p = team.round1_points or 0
    r2p = team.round2_points or 0
    r3p = team.round3_points or 0
    r4p = team.round4_points or 0
    r1s = team.round1_size or 1
    r2s = team.round2_size or 1
    r3s = team.round3_size or 1
    r4s = team.round4_size or 1
    total = r1p + r2p + r3p + r4p
    per_capita = round(r1p / r1s + r2p / r2s + r3p / r3s + r4p / r4s, 2)
    return total, per_capita


@app.route('/pubquiz')
def pubquiz():
    rounds = PubQuizRounds.query.order_by(PubQuizRounds.datum.desc()).all()
    selected_id = request.args.get('round_id', type=int)
    if not selected_id and rounds:
        selected_id = rounds[0].id

    selected_round = PubQuizRounds.query.filter_by(id=selected_id).first() if selected_id else None

    team_data = []
    round_rankings = {1: [], 2: [], 3: [], 4: []}
    overall_avg = None
    round_avgs = {1: None, 2: None, 3: None, 4: None}

    if selected_round:
        for t in selected_round.teams:
            total, per_capita = _team_scores(t)
            team_data.append({
                'id': t.id,
                'name': t.name or '—',
                'round1_points': t.round1_points,
                'round2_points': t.round2_points,
                'round3_points': t.round3_points,
                'round4_points': t.round4_points,
                'round1_size': t.round1_size,
                'round2_size': t.round2_size,
                'round3_size': t.round3_size,
                'round4_size': t.round4_size,
                'total': total,
                'per_capita': per_capita,
            })
        team_data.sort(key=lambda x: x['total'], reverse=True)

        for rnum, key in [(1, 'round1_points'), (2, 'round2_points'), (3, 'round3_points'), (4, 'round4_points')]:
            pts = [t[key] for t in team_data if t[key] is not None]
            round_avgs[rnum] = round(sum(pts) / len(pts), 2) if pts else None
            with_pts = sorted([t for t in team_data if t[key] is not None], key=lambda x: x[key], reverse=True)
            without_pts = [t for t in team_data if t[key] is None]
            round_rankings[rnum] = with_pts + without_pts

        totals = [t['total'] for t in team_data]
        overall_avg = round(sum(totals) / len(totals), 2) if totals else None

    return render_template('pubquiz.html',
                           rounds=rounds,
                           selected_round=selected_round,
                           selected_id=selected_id,
                           team_data=team_data,
                           round_rankings=round_rankings,
                           overall_avg=overall_avg,
                           round_avgs=round_avgs)


@app.route('/pubquiz/admin/logout')
def pubquiz_admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('pubquiz'))


@app.route('/pubquiz/admin')
@require_admin_login
def pubquiz_admin():
    rounds = PubQuizRounds.query.order_by(PubQuizRounds.datum.desc()).all()
    selected_id = request.args.get('round_id', type=int)
    if not selected_id and rounds:
        selected_id = rounds[0].id
    selected_round = PubQuizRounds.query.filter_by(id=selected_id).first() if selected_id else None
    return render_template('pubquiz_admin.html',
                           rounds=rounds,
                           selected_round=selected_round,
                           selected_id=selected_id)


@app.route('/pubquiz/admin/round/create', methods=['POST'])
@require_admin_login
def pubquiz_create_round():
    datum_str = request.form.get('datum', '').strip()
    bilderrunde = request.form.get('bilderrunde', '').strip() or None
    quizmaster = request.form.get('quizmaster', '').strip() or None
    try:
        datum = dt.datetime.fromisoformat(datum_str) if datum_str else dt.datetime.now()
    except ValueError:
        datum = dt.datetime.now()
    new_round = PubQuizRounds(datum=datum, bilderrunde=bilderrunde, quizmaster=quizmaster)
    db.session.add(new_round)
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=new_round.id))


@app.route('/pubquiz/admin/round/<int:round_id>/delete', methods=['POST'])
@require_admin_login
def pubquiz_delete_round(round_id):
    r = PubQuizRounds.query.get_or_404(round_id)
    db.session.delete(r)
    db.session.commit()
    return redirect(url_for('pubquiz_admin'))


@app.route('/pubquiz/admin/round/<int:round_id>/update', methods=['POST'])
@require_admin_login
def pubquiz_update_round(round_id):
    r = PubQuizRounds.query.get_or_404(round_id)
    datum_str = request.form.get('datum', '').strip()
    if datum_str:
        try:
            r.datum = dt.datetime.fromisoformat(datum_str)
        except ValueError:
            pass
    r.bilderrunde = request.form.get('bilderrunde', '').strip() or None
    r.quizmaster = request.form.get('quizmaster', '').strip() or None
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=round_id))


@app.route('/pubquiz/admin/team/add', methods=['POST'])
@require_admin_login
def pubquiz_add_team():
    round_id = request.form.get('round_id', type=int)
    name = request.form.get('name', '').strip()
    if not round_id or not name:
        return redirect(url_for('pubquiz_admin', round_id=round_id))
    if PubQuizTeams.query.filter(PubQuizTeams.round_id == round_id, db.func.lower(PubQuizTeams.name) == name.lower()).first():
        return redirect(url_for('pubquiz_admin', round_id=round_id, error='duplicate', error_name=name))
    team = PubQuizTeams(name=name, round_id=round_id)
    db.session.add(team)
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=round_id))


@app.route('/pubquiz/admin/round/<int:round_id>/scores/<int:round_num>', methods=['POST'])
@require_admin_login
def pubquiz_save_round_scores(round_id, round_num):
    if round_num not in (1, 2, 3, 4):
        return redirect(url_for('pubquiz_admin', round_id=round_id))
    teams = PubQuizTeams.query.filter_by(round_id=round_id).all()
    for team in teams:
        pts_str = request.form.get(f'team_{team.id}_points', '').strip()
        size_str = request.form.get(f'team_{team.id}_size', '').strip()
        pts = int(pts_str) if pts_str.lstrip('-').isdigit() else None
        size = int(size_str) if size_str.isdigit() and int(size_str) > 0 else None
        if round_num == 1:
            team.round1_points, team.round1_size = pts, size
        elif round_num == 2:
            team.round2_points, team.round2_size = pts, size
        elif round_num == 3:
            team.round3_points, team.round3_size = pts, size
        else:
            team.round4_points, team.round4_size = pts, size
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=round_id))


@app.route('/pubquiz/admin/team/<int:team_id>/update', methods=['POST'])
@require_admin_login
def pubquiz_update_team(team_id):
    team = PubQuizTeams.query.get_or_404(team_id)
    team.name = request.form.get('name', team.name).strip()

    def _int(key, fallback):
        v = request.form.get(key, '').strip()
        return int(v) if v.isdigit() else fallback

    team.round1_points = _int('round1_points', team.round1_points)
    team.round2_points = _int('round2_points', team.round2_points)
    team.round3_points = _int('round3_points', team.round3_points)
    team.round1_size   = _int('round1_size',   team.round1_size)
    team.round2_size   = _int('round2_size',   team.round2_size)
    team.round3_size   = _int('round3_size',   team.round3_size)
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=team.round_id))


@app.route('/pubquiz/admin/team/<int:team_id>/delete', methods=['POST'])
@require_admin_login
def pubquiz_delete_team(team_id):
    team = PubQuizTeams.query.get_or_404(team_id)
    round_id = team.round_id
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for('pubquiz_admin', round_id=round_id))


if __name__ == '__main__':
    #task_update_clan_members()
    #task_update_ranked_weeks()
    #task_update_battle_logs()
    #task_update_done_ranked_weeks()
    #task_update_raid_weekend()
    
    # Webserver starten (use_reloader=False verhindert, dass der Scheduler beim Speichern doppelt startet)
    app.run(debug=True, use_reloader=False)