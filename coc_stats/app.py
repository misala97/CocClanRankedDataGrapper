import json
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_migrate import Migrate

from logging_config import setup_root_logger
from extensions import db

load_dotenv(override=True)
setup_root_logger()

CLAN_TAG   = os.getenv("CLAN_TAG", "#2QRC8998U")

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder='static', static_url_path='/static')

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "coc_stats")

_secret_key = os.getenv("COC_SECRET_KEY")
if not _secret_key:
    import logging
    logging.getLogger().warning("COC_SECRET_KEY not set in .env — using random key, sessions reset on restart.")
    _secret_key = secrets.token_hex(32)

app.config['SECRET_KEY'] = _secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

db.init_app(app)
migrate = Migrate(app, db)

from models import *
db.configure_mappers()

# ── Blueprints ────────────────────────────────────────────────────────────────

from features.auth.routes    import auth_bp
from features.admin.routes   import admin_bp
from features.ranked.routes  import ranked_bp
from features.raid.routes    import raid_bp
from features.war.routes     import war_bp
from features.battles.routes import battles_bp
from features.player.routes  import player_bp
from features.cwl.routes     import cwl_bp
from features.profile.routes import profile_bp
from features.tools.routes   import tools_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ranked_bp)
app.register_blueprint(raid_bp)
app.register_blueprint(war_bp)
app.register_blueprint(battles_bp)
app.register_blueprint(player_bp)
app.register_blueprint(cwl_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(tools_bp)

# ── Template filters ─────────────────────────────────────────────────────────

from services.helpers import to_local as _to_local, compute_cwl_win_status, compute_war_win_status

@app.template_filter('local_dt')
def local_dt_filter(value, fmt='%d.%m.%Y %H:%M'):
    if value is None:
        return '—'
    return _to_local(value).strftime(fmt)

# ── Auth context processor ────────────────────────────────────────────────────

from features.auth.routes import _current_user, _is_super_admin, _is_env_admin, _can_create_reminder_ranked, _can_edit_clan_war
import datetime as _dt

def _nav_task_status():
    try:
        known = [
            ('task_update_ranked_weeks', 'Ranked'),
            ('task_update_battle_logs',  'Battles'),
            ('task_update_raid_weekend', 'Raids'),
            ('task_update_clan_war',     'War'),
            ('task_update_cwl',          'CWL'),
            ('task_update_clan_members', 'Members'),
        ]
        now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        result = []
        for fn, label in known:
            last = UptimeTracker.query.filter_by(function=fn)\
                       .order_by(UptimeTracker.time.desc()).first()
            if last and last.time:
                mins = round((now - last.time).total_seconds() / 60)
                status = 'good' if mins < 15 else ('warn' if mins < 60 else 'bad')
                time_str = f'{mins}m ago' if mins < 60 else f'{mins // 60}h ago'
            else:
                status, time_str, mins = 'none', 'No data', None
            result.append({'label': label, 'status': status, 'time_str': time_str, 'mins': mins})
        return result
    except Exception:
        return []

def _fmt_age(mins):
    if mins is None:
        return None
    if mins < 60:
        return f'{mins}m ago'
    if mins < 60 * 24:
        return f'{mins // 60}h ago'
    return f'{mins // (60 * 24)}d ago'

def _nav_health(tasks):
    """Overall sync health for the honest footer status line. 'bad' if any
    source is stale/missing, 'warn' if any is merely delayed, else 'good'. The
    age is time since the *freshest* successful sync — i.e. how long the system
    has been dark."""
    if not tasks:
        return {'level': 'good', 'age_str': None, 'down': 0}
    statuses = [t['status'] for t in tasks]
    ages = [t['mins'] for t in tasks if t['mins'] is not None]
    if any(s in ('bad', 'none') for s in statuses):
        level = 'bad'
    elif any(s == 'warn' for s in statuses):
        level = 'warn'
    else:
        level = 'good'
    down = sum(1 for s in statuses if s in ('bad', 'none'))
    return {'level': level, 'age_str': _fmt_age(min(ages)) if ages else None, 'down': down}

def _newbie_check_count():
    try:
        return Player.query.filter_by(in_clan=True, newbie_check=False).count()
    except Exception:
        return 0

def _pending_approval_count():
    # Admin-only figure (the admin sub-nav badge + Overview alert tile). Guarded by
    # the caller so the COUNT only runs for super admins, not every anonymous visitor.
    try:
        return AppUser.query.filter_by(is_approved=False).count()
    except Exception:
        return 0

def _clan_badge_url():
    try:
        latest_war = ClanWar.query.order_by(ClanWar.start_time.desc()).first()
        return latest_war.clan_badge if latest_war and latest_war.clan_badge else None
    except Exception:
        return None

@app.context_processor
def inject_auth():
    _nav_status = _nav_task_status()
    _super = _is_super_admin()
    return {
        'current_user':  _current_user(),
        'is_super_admin': _super,
        'is_env_admin':   _is_env_admin(),
        'can_create_reminder_ranked': _can_create_reminder_ranked(),
        'can_edit_clan_war': _can_edit_clan_war(),
        'nav_task_status': _nav_status,
        'nav_health': _nav_health(_nav_status),
        'newbie_check_count': _newbie_check_count(),
        'pending_approvals': _pending_approval_count() if _super else 0,
        'clan_badge_url': _clan_badge_url(),
    }

# ── Core routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    from sqlalchemy import func as sa_func
    latest_war = ClanWar.query.order_by(ClanWar.start_time.desc()).first()
    clan_name      = (latest_war.clan_name  if latest_war and latest_war.clan_name  else None) or "Our Clan"
    clan_badge_url = (latest_war.clan_badge if latest_war and latest_war.clan_badge else None)

    from services.helpers import week_cutoff, filter_import_window
    total_members = Player.query.filter_by(in_clan=True).count()
    week_start = week_cutoff(None, 7)

    week_logs = BattleLog.query.join(BattleLog.player).filter(
        BattleLog.time >= week_start,
        BattleLog.attack == True,
        Player.in_clan == True
    ).all()
    first_log_time_idx = dict(
        db.session.query(BattleLog.player_tag, sa_func.min(BattleLog.time))
        .group_by(BattleLog.player_tag)
        .all()
    )
    battle_logs_this_week = len(filter_import_window(week_logs, first_log_time_idx))
    current_season = db.session.query(RankedWeek.league_season_id)\
        .order_by(RankedWeek.league_season_id.desc()).first()
    ranked_battles_this_week = RankedBattleLog.query.join(
        Player, RankedBattleLog.player_tag == Player.tag
    ).filter(
        RankedBattleLog.league_season_id == current_season[0],
        RankedBattleLog.attack == True,
        Player.in_clan == True
    ).count() if current_season else 0
    week_start_name = week_start.strftime('%A')

    # Data can go stale (the sync daemon stops and a war's `state` is frozen at
    # 'inWar' indefinitely). Never present a round whose clock has already run
    # out as "live" — if its end_time is in the past, treat it as finished so the
    # War Room falls through to the honest "last completed" tier. Rounds with no
    # end_time are left as-is (unknown, not provably stale).
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

    active_war  = ClanWar.query.filter(
        ClanWar.state.in_(['preparation', 'inWar'])
    ).order_by(ClanWar.start_time.desc()).first()
    if active_war and active_war.end_time and active_war.end_time <= now:
        active_war = None
    war_win_status = compute_war_win_status(active_war, CLAN_TAG) if active_war else None

    active_raid = RaidWeekend.query.filter(
        RaidWeekend.state == 'ongoing'
    ).order_by(RaidWeekend.start_time.desc()).first()
    if active_raid and active_raid.end_time and active_raid.end_time <= now:
        active_raid = None

    active_cwl_season = CWLSeason.query.filter(
        CWLSeason.state.in_(['preparation', 'inWar'])
    ).order_by(CWLSeason.id.desc()).first()

    active_cwl_war = None
    cwl_win_status = None
    if active_cwl_season:
        _cwl_candidate = CWLWar.query.filter(
            CWLWar.season_id == active_cwl_season.id,
            CWLWar.state.in_(['preparation', 'inWar']),
            db.or_(CWLWar.clan_tag == CLAN_TAG, CWLWar.opp_tag == CLAN_TAG)
        ).first()
        if _cwl_candidate and _cwl_candidate.end_time and _cwl_candidate.end_time <= now:
            # The current round's clock has run out but sync froze it 'inWar' →
            # the whole season is stale, not live. Fall through to last completed.
            active_cwl_season = None
        else:
            active_cwl_war = _cwl_candidate
            if active_cwl_war:
                cwl_win_status = compute_cwl_win_status(active_cwl_war, CLAN_TAG)

    active_raid_est_medals = None
    if active_raid:
        from services.helpers import raid_district_medal_value
        destroyed = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == active_raid.id,
                    RaidWeekendLog.percentage_total >= 100)
            .with_entities(RaidWeekendLog.defender_tag, RaidWeekendLog.district_name, RaidWeekendLog.district_level)
            .distinct()
            .all()
        )
        total_medals  = sum(raid_district_medal_value(r.district_name, r.district_level) for r in destroyed)
        total_attacks = RaidWeekendLog.query.filter_by(raid_weekend_id=active_raid.id).count()
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensive_reward > 0)
            .order_by(RaidWeekend.start_time.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensive_reward)
            .all()
        )
        avg_def = round(sum(r.defensive_reward for r in past_def) / len(past_def)) if past_def else 0
        if total_medals > 0 and total_attacks > 0:
            baseline = total_medals / total_attacks
            active_raid_est_medals = max(0, min(round(baseline * 6), 1620)) + avg_def

    last_war = None
    if not active_war:
        last_war = ClanWar.query.filter(
            ClanWar.state == 'warEnded'
        ).order_by(ClanWar.start_time.desc()).first()

    last_raid = None
    if not active_raid:
        last_raid = RaidWeekend.query.filter(
            RaidWeekend.state == 'ended'
        ).order_by(RaidWeekend.start_time.desc()).first()

    last_cwl_war = None
    if not active_cwl_season:
        last_cwl_war = CWLWar.query.filter(
            CWLWar.state == 'warEnded',
            db.or_(CWLWar.clan_tag == CLAN_TAG, CWLWar.opp_tag == CLAN_TAG)
        ).order_by(CWLWar.id.desc()).first()

    # ── Player-specific hero data ────────────────────────────────────────────
    player_ranked_left        = None
    player_gain_settings      = None
    _zero_stats = '{"shiny":0,"glowy":0,"starry":0,"attacks":0,"wars":0}'
    player_war_stats_json     = _zero_stats
    player_cwl_stats_json     = _zero_stats
    player_th                 = 0
    player_league             = ''
    player_ore                = {'shiny': 0, 'glowy': 0, 'starry': 0}
    player_attacks_this_week  = 0
    player_war_stats          = {'attacks': 0, 'wars': 0}
    player_cwl_stats          = {'attacks': 0, 'wars': 0}

    _idx_user = _current_user()
    if _idx_user and _idx_user.linked_player:
        _p = _idx_user.linked_player

        try:
            if current_season:
                from sqlalchemy.orm import selectinload as _sload
                from services.helpers import _is_attack as _ia
                _rw = RankedWeek.query.filter_by(
                    player_tag=_p.tag,
                    league_season_id=current_season[0],
                ).options(_sload(RankedWeek.battle_logs)).first()
                if _rw:
                    _att = sum(1 for log in _rw.battle_logs if _ia(log))
                    player_ranked_left = max(0, (_rw.max_attacks or 0) - _att)
        except Exception:
            pass

        try:
            from features.tools.routes import _compute_war_stats, _compute_cwl_stats
            _ws = _compute_war_stats(_p.tag)
            _cs = _compute_cwl_stats(_p.tag)
            try:
                player_gain_settings = json.loads(_idx_user.gain_settings) if _idx_user.gain_settings else None
            except (TypeError, ValueError):
                player_gain_settings = None
            player_war_stats_json     = json.dumps(_ws)
            player_cwl_stats_json     = json.dumps(_cs)
            player_th                 = _p.current_th or 0
            player_league             = _p.league_tier or ''
            player_war_stats          = {'attacks': _ws['attacks'], 'wars': _ws['wars']}
            player_cwl_stats          = {'attacks': _cs['attacks'], 'wars': _cs['wars']}
        except Exception:
            pass

        try:
            player_ore = {
                'shiny':  _idx_user.ore_shiny  or 0,
                'glowy':  _idx_user.ore_glowy  or 0,
                'starry': _idx_user.ore_starry or 0,
            }
            player_attacks_this_week = BattleLog.query.filter(
                BattleLog.player_tag == _p.tag,
                BattleLog.time >= week_start,
                BattleLog.attack == True,
            ).count()
        except Exception:
            pass

    return render_template(
        'index.html',
        clan_name=clan_name,
        clan_badge_url=clan_badge_url,
        total_members=total_members,
        battle_logs_this_week=battle_logs_this_week,
        ranked_battles_this_week=ranked_battles_this_week,
        week_start_name=week_start_name,
        active_war=active_war,
        war_win_status=war_win_status,
        active_raid=active_raid,
        active_raid_est_medals=active_raid_est_medals,
        active_cwl_season=active_cwl_season,
        active_cwl_war=active_cwl_war,
        cwl_win_status=cwl_win_status,
        last_war=last_war,
        last_raid=last_raid,
        last_cwl_war=last_cwl_war,
        CLAN_TAG=CLAN_TAG,
        player_ranked_left=player_ranked_left,
        player_gain_settings=player_gain_settings,
        player_war_stats_json=player_war_stats_json,
        player_cwl_stats_json=player_cwl_stats_json,
        player_th=player_th,
        player_league=player_league,
        player_ore=player_ore,
        player_attacks_this_week=player_attacks_this_week,
        player_war_stats=player_war_stats,
        player_cwl_stats=player_cwl_stats,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from tasks.battle_logs   import task_update_battle_logs
    from tasks.raid_weekend  import task_update_raid_weekend
    from tasks.ranked_weeks  import task_update_ranked_weeks
    from tasks.clan_war      import task_update_clan_war
    from tasks.clan_members  import task_update_clan_members
    from tasks.cwl           import task_update_cwl

    # Uncomment to run tasks manually before starting:
    #task_update_clan_members()
    #task_update_battle_logs()
    #task_update_raid_weekend()
    #task_update_ranked_weeks()
    #task_update_clan_war()
    #task_update_cwl()

    app.run(host='0.0.0.0', debug=True, use_reloader=False, port=5000)
