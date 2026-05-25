import logging
import os
import re
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
root_logger.setLevel(logging.DEBUG)
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
                ranked_logger.warning(f"Could not fetch player group {week.player.name}. Error: {e}")
                continue
            
            #PLayer data
            try:
                player_api = api_fetch_player_data(week.player.tag)
            except Exception as e:
                ranked_logger.warning(f"Could not fetch player {week.player.name}. Error: {e}")
                continue
            
            
            #Ranked Woche anlegen
            try:      
                tmp_ranked_week = create_db_ranked_week(week.league_group_tag, week.league_season_id, player_api, group_data_api)
                db_ranked_week_update(week, tmp_ranked_week, True)
            except Exception as e:
                ranked_logger.error(f"Failed to update ranked week for {week.player.name}: {e}")
                db.session.rollback() 
                continue
            db.session.commit()
        duration = round(time.time() - t0, 2)
        db_uptime_tracker_create_new(create_db_uptime_tracker(task_update_battle_logs.__name__, duration))
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

        if ranked_week:
            league_tier = ranked_week.league_tier or league_tier
            league_icon = ranked_week.league_icon or league_icon
            rank = ranked_week.rank
            trophies = ranked_week.trophies
            max_attacks = ranked_week.max_attacks or 0

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

        if not is_active:
            badge_class = 'badge-inactive'
            judge_label = 'Inactive'
            rank_status = 'inactive'
        elif att_avg >= 3.0 and att_count > 0:
            badge_class = 'badge-perfect'
            judge_label = 'Perfect' + missing_text
            rank_status = 'neutral'
        elif att_avg >= 2.5:
            badge_class = 'badge-wow'
            judge_label = 'Very Good' + missing_text
            rank_status = 'neutral'
        elif att_avg >= 2.0:
            badge_class = 'badge-good'
            judge_label = 'Good' + missing_text
            rank_status = 'neutral'
        elif att_avg >= 1.5:
            badge_class = 'badge-warning'
            judge_label = 'Bad' + missing_text
            rank_status = 'neutral'
        else:
            badge_class = 'badge-suck'
            judge_label = 'Disaster' + missing_text
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


@app.route('/battles')
def battle_history_page():
    """Battle History page"""
    selected_type = request.args.get('type', 'homeVillage')
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

    # Always fetch the full history per player (type filter only, no date window) so
    # the initial API dump is identified from the complete timeline, not the already-
    # narrowed week slice (which would wrongly drop real current-week attacks).
    all_q = BattleLog.query.filter(BattleLog.attack == True)
    if selected_type != 'all':
        all_q = all_q.filter(BattleLog.type == selected_type)
    all_attacks_raw = all_q.options(selectinload(BattleLog.player)).all()

    _by_player: dict = {}
    for b in all_attacks_raw:
        _by_player.setdefault(b.player_tag, []).append(b)

    attacks = []
    for logs in _by_player.values():
        logs.sort(key=lambda b: b.time or dt.datetime.min)
        valid = logs[25:]  # drop the one-time initial API dump
        if is_all_time:
            attacks.extend(valid)
        else:
            attacks.extend(
                b for b in valid
                if b.time and b.time >= week_start_dt and b.time < next_monday_dt
            )

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
        s['attack_logs'].append({
            'time': b.time.strftime('%d.%m.%y %H:%M') if b.time else '–',
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

if __name__ == '__main__':
    #task_update_clan_members()
    #task_update_ranked_weeks()
    #task_update_battle_logs()
    #task_update_done_ranked_weeks()
    
    # Webserver starten (use_reloader=False verhindert, dass der Scheduler beim Speichern doppelt startet)
    app.run(debug=True, use_reloader=False)