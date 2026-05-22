import logging
import os
import sys
import time

from dotenv import load_dotenv
from flask import Flask, render_template, request
from flask_migrate import Migrate
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from extensions import db
from help_functions import *
from api_functions import * 
from database_functions import *
import datetime
from logging.handlers import RotatingFileHandler


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
clan_logger = setup_task_logger('clan_members', 'logs/task_clan_members.log')


# ==========================================
# 2. APP & DB SETUP
# ==========================================
load_dotenv(override=True)

app = Flask(__name__)

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "coc_stats")
CLAN_TAG = os.getenv("CLAN_TAG", "#2QRC8998U")
API_TOKEN = os.getenv("API_TOKEN")

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
        
def task_update_battle_logs():
    t0 = time.time()
    battle_logger.info(f"Running task at {datetime.now()}  ")
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
        
        
def task_update_ranked_weeks():
    t0 = time.time()
    ranked_logger.info(f"Running task at {datetime.now()}  ")
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
    clan_logger.info(f"Running task at {datetime.now()}  ")
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
    #task_update_clan_members()
    #task_update_ranked_weeks()
    #task_update_battle_logs()
    
    #print(JSON_PLAYER_DATA.TAG)
    
    #print(JSON_PLAYER_DATA.LEAGUE_TIER)
    #print(JSON_PLAYER_DATA.LEAGUE_TIER.NAME)
    
    #player, error= api_fetch_player_data("2JUQY0JP")
    #print(json_get(player, "tag"))

    # Webserver starten (use_reloader=False verhindert, dass der Scheduler beim Speichern doppelt startet)
    app.run(debug=True, use_reloader=False)