import datetime as dt

from flask import Blueprint, render_template, redirect, url_for

from extensions import db
from models import Player, RankedWeek, RankedBattleLog, BattleLog, RaidWeekend, RaidWeekendLog, ClanWarMember, ClanWarAttack, ClanWar
from features.auth.routes import _current_user, _any_access
from services.helpers import LOCAL_TZ, week_cutoff

profile_bp = Blueprint('profile', __name__)


def _require_login():
    """Return redirect if not logged in, else None."""
    if not _any_access():
        return redirect(url_for('auth.login'))
    return None


def _current_ranked_week(player_tag):
    latest_season = (
        db.session.query(RankedWeek.league_season_id)
        .order_by(RankedWeek.league_season_id.desc())
        .first()
    )
    if not latest_season:
        return None, []
    rw = RankedWeek.query.filter_by(
        player_tag=player_tag,
        league_season_id=latest_season[0]
    ).first()
    if not rw:
        return None, []
    battles = (
        RankedBattleLog.query
        .filter_by(
            player_tag=player_tag,
            league_season_id=latest_season[0],
            league_group_tag=rw.league_group_tag
        )
        .order_by(RankedBattleLog.time.desc())
        .limit(20)
        .all()
    )
    return rw, battles


def _recent_battles(player_tag, days=7):
    cutoff = week_cutoff(None, 7)

    return (
        BattleLog.query
        .filter(
            BattleLog.player_tag == player_tag,
            BattleLog.time >= cutoff,
        )
        .order_by(BattleLog.time.desc())
        .limit(50)
        .all()
    )


def _recent_wars(player_tag, limit=5):
    war_ids = [
        r.clan_war_id for r in
        ClanWarMember.query
        .filter_by(player_tag=player_tag, is_opponent=False)
        .join(ClanWar, ClanWarMember.clan_war_id == ClanWar.id)
        .order_by(ClanWar.start_time.desc())
        .limit(limit)
        .with_entities(ClanWarMember.clan_war_id)
        .all()
    ]
    if not war_ids:
        return []
    wars = ClanWar.query.filter(ClanWar.id.in_(war_ids)).order_by(ClanWar.start_time.desc()).all()
    result = []
    for war in wars:
        attacks = ClanWarAttack.query.filter_by(
            clan_war_id=war.id, attacker_tag=player_tag
        ).all()
        result.append({'war': war, 'attacks': attacks})
    return result


def _raid_summary(player_tag, limit=4):
    recent_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).limit(limit).all()
    total_attacks = 0
    total_loot = 0
    for raid in recent_raids:
        logs = RaidWeekendLog.query.filter_by(
            raid_weekend_id=raid.id, player_tag=player_tag
        ).all()
        total_attacks += len(logs)
        total_loot += sum(l.total_loot_all_attacks or 0 for l in logs)
    return {'total_attacks': total_attacks, 'total_loot': total_loot, 'raids_checked': len(recent_raids)}


@profile_bp.route('/profile')
def profile():
    guard = _require_login()
    if guard:
        return guard

    user = _current_user()
    if not user:
        return redirect(url_for('auth.login'))

    player = user.linked_player

    if not player:
        return render_template('profile/profile.html', player=None, user=user)

    ranked_week, ranked_battles = _current_ranked_week(player.tag)
    recent_battles = _recent_battles(player.tag)
    recent_wars = _recent_wars(player.tag)
    raid_summary = _raid_summary(player.tag)

    attacks_this_week = sum(1 for b in recent_battles if b.attack)
    defenses_this_week = sum(1 for b in recent_battles if not b.attack)

    ranked_attacks_done = sum(1 for b in ranked_battles if b.attack)
    ranked_attacks_won  = sum(1 for b in ranked_battles if b.attack and (b.stars or 0) >= 2)

    return render_template(
        'profile/profile.html',
        user=user,
        player=player,
        ranked_week=ranked_week,
        ranked_battles=ranked_battles,
        ranked_attacks_done=ranked_attacks_done,
        ranked_attacks_won=ranked_attacks_won,
        recent_battles=recent_battles,
        attacks_this_week=attacks_this_week,
        defenses_this_week=defenses_this_week,
        recent_wars=recent_wars,
        raid_summary=raid_summary,
    )
