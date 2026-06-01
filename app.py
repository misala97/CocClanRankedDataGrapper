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
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "coc_stats")

_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    import logging
    logging.getLogger().warning("SECRET_KEY not set in .env — using random key, sessions reset on restart.")
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
from features.pubquiz.routes import pubquiz_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ranked_bp)
app.register_blueprint(raid_bp)
app.register_blueprint(war_bp)
app.register_blueprint(battles_bp)
app.register_blueprint(player_bp)
app.register_blueprint(pubquiz_bp)

# ── Template filters ─────────────────────────────────────────────────────────

from services.helpers import to_local as _to_local

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
                status, time_str = 'none', 'No data'
            result.append({'label': label, 'status': status, 'time_str': time_str})
        return result
    except Exception:
        return []

@app.context_processor
def inject_auth():
    return {
        'current_user':  _current_user(),
        'is_super_admin': _is_super_admin(),
        'is_env_admin':   _is_env_admin(),
        'can_create_reminder_ranked': _can_create_reminder_ranked(),
        'can_edit_clan_war': _can_edit_clan_war(),
        'nav_task_status': _nav_task_status(),
    }

# ── Core routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    import datetime as dt
    from sqlalchemy import func as sa_func
    latest_war = ClanWar.query.order_by(ClanWar.start_time.desc()).first()
    clan_name      = (latest_war.clan_name  if latest_war and latest_war.clan_name  else None) or "Our Clan"
    clan_badge_url = (latest_war.clan_badge if latest_war and latest_war.clan_badge else None)

    from services.helpers import LOCAL_TZ
    total_members = Player.query.filter_by(in_clan=True).count()
    now_local = dt.datetime.now(LOCAL_TZ)
    week_start_date = (now_local - dt.timedelta(days=now_local.weekday())).date()
    week_start = dt.datetime(week_start_date.year, week_start_date.month, week_start_date.day, tzinfo=LOCAL_TZ)\
        .astimezone(dt.timezone.utc).replace(tzinfo=None)

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
    import_window = dt.timedelta(minutes=2)
    battle_logs_this_week = sum(
        1 for b in week_logs
        if not (b.time and first_log_time_idx.get(b.player_tag) and
                b.time <= first_log_time_idx[b.player_tag] + import_window)
    )
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

    active_war  = ClanWar.query.filter(
        ClanWar.state.in_(['preparation', 'inWar'])
    ).order_by(ClanWar.start_time.desc()).first()

    active_raid = RaidWeekend.query.filter(
        RaidWeekend.state == 'ongoing'
    ).order_by(RaidWeekend.startTime.desc()).first()

    active_raid_est_medals = None
    if active_raid:
        from services.helpers import raid_district_medal_value
        destroyed = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == active_raid.id,
                    RaidWeekendLog.percentageTotal >= 100)
            .with_entities(RaidWeekendLog.defenderTag, RaidWeekendLog.districtName, RaidWeekendLog.districLevel)
            .distinct()
            .all()
        )
        total_medals  = sum(raid_district_medal_value(r.districtName, r.districLevel) for r in destroyed)
        total_attacks = RaidWeekendLog.query.filter_by(raid_weekend_id=active_raid.id).count()
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensiveReward > 0)
            .order_by(RaidWeekend.startTime.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensiveReward)
            .all()
        )
        avg_def = round(sum(r.defensiveReward for r in past_def) / len(past_def)) if past_def else 0
        if total_medals > 0 and total_attacks > 0:
            baseline = total_medals / total_attacks
            active_raid_est_medals = max(0, min(round(baseline * 6), 1620)) + avg_def

    return render_template(
        'index.html',
        clan_name=clan_name,
        clan_badge_url=clan_badge_url,
        total_members=total_members,
        battle_logs_this_week=battle_logs_this_week,
        ranked_battles_this_week=ranked_battles_this_week,
        week_start_name=week_start_name,
        active_war=active_war,
        active_raid=active_raid,
        active_raid_est_medals=active_raid_est_medals,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from tasks.battle_logs   import task_update_battle_logs
    from tasks.raid_weekend  import task_update_raid_weekend
    from tasks.ranked_weeks  import task_update_ranked_weeks
    from tasks.clan_war      import task_update_clan_war
    from tasks.clan_members  import task_update_clan_members

    # Uncomment to run tasks manually before starting:
    #task_update_clan_members()
    #task_update_battle_logs()
    #task_update_raid_weekend()
    #task_update_ranked_weeks()
    task_update_clan_war()

    app.run(debug=True, use_reloader=False)
