import datetime as dt
import logging
import time
from typing import List

from sqlalchemy import or_

from extensions import db
from models import (
    Player, RankedWeek, RankedBattleLog, BattleLog,
    RaidWeekend, RaidWeekendLog, UptimeTracker,
    ClanWar, ClanWarMember, ClanWarAttack,
    CWLSeason, CWLClan, CWLClanMember, CWLWar, CWLMember, CWLAttack,
)
from services.helpers import (
    json_get, parse_iso_datetime,
    get_name_to_id, get_resource_amount, get_weekly_attacks,
    get_member_rank_by_tag, get_next_monday, get_last_monday,
    JSON_PLAYER_DATA, JSON_BATTLE_LOG_DATA, JSON_RANKED_GROUP_DATA,
    JSON_RAID_WEEKEND_DATA, JSON_CLAN_WAR_DATA, JSON_CLAN_DATA, avg_league_name,
    JSON_CWL_GROUP_DATA, JSON_CWL_WAR_DATA,
)


# ── Create helpers ────────────────────────────────────────────────────────────

def create_db_player_from_api(player_data_api: dict, in_clan: bool = True) -> Player:
    if not isinstance(player_data_api, dict):
        raise TypeError(f"Expected Player dict, got {type(player_data_api).__name__}")
    return Player(
        tag         = json_get(player_data_api, JSON_PLAYER_DATA.TAG),
        name        = json_get(player_data_api, JSON_PLAYER_DATA.NAME),
        current_th  = json_get(player_data_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
        in_clan     = in_clan,
        league_tier = get_name_to_id(json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID)),
    )


def create_db_raid_weekend_from_api(current_raid_weekend: dict):
    if not isinstance(current_raid_weekend, dict):
        raise TypeError(f"Expected Raid dict, got {type(current_raid_weekend).__name__}")
    return RaidWeekend(
        start_time                = parse_iso_datetime(json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_STARTTIME)),
        end_time                  = parse_iso_datetime(json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ENDTIME)),
        state                     = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_STATE),
        capital_total_loot        = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_CAPITALTOTALLOOT),
        raids_completed           = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_RAIDSCOMPLETED),
        total_attacks             = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_TOTALATTACKS),
        enemy_districts_destroyed = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ENEMYDISTRICTSDESTROYED),
        offensive_reward          = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_OFFENSIVEREWARD),
        defensive_reward          = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_DEFENSIVEREWARD),
    )


def create_db_raid_weekend_log(raid_weekend, player_tag, district_name, loot, percentage, percentage_total, stars, defender_tag, defender_name, district_level, total_loot_all_attacks) -> RaidWeekendLog:
    if not isinstance(raid_weekend, RaidWeekend):
        raise TypeError(f"Expected RaidWeekend object, got {type(raid_weekend).__name__}")
    return RaidWeekendLog(
        raid_weekend_id        = raid_weekend.id,
        player_tag             = player_tag,
        defender_name          = defender_name,
        defender_tag           = defender_tag,
        district_level         = district_level,
        total_loot_all_attacks = total_loot_all_attacks,
        district_name          = district_name,
        percentage             = percentage,
        percentage_total       = percentage_total,
        stars                  = stars,
    )


def create_db_uptime_tracker(func_name: str, duration: str, status: str = 'success', error_message: str = None, summary: str = None) -> UptimeTracker:
    return UptimeTracker(function=func_name, duration=duration, status=status, error_message=error_message, summary=summary)


def db_finalize_uptime(func_name: str, t0: float, status: str = 'success', error_message: str = None, summary: str = None, logger=None):
    duration = round(time.time() - t0, 2)
    if logger:
        logger.info(f"Done in {duration}s | {summary or status}")
    db.session.add(UptimeTracker(function=func_name, duration=duration, status=status, error_message=error_message, summary=summary))
    db.session.commit()


def _group_attack_stats(league_members: list, max_attacks: int) -> tuple[int, int]:
    total = 0
    full  = 0
    for m in league_members:
        done = (json_get(m, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT,  default=0, raise_on_missing=False) or 0) + \
               (json_get(m, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT, default=0, raise_on_missing=False) or 0)
        total += done
        if max_attacks > 0 and done >= max_attacks:
            full += 1
    return total, full


def create_db_ranked_week(league_group_tag, league_season_id, player_data_api, league_group_data_api) -> RankedWeek:
    league_members = json_get(league_group_data_api, JSON_RANKED_GROUP_DATA.MEMBERS)
    player_tag     = json_get(player_data_api, JSON_PLAYER_DATA.TAG)
    calculated_rank           = get_member_rank_by_tag(league_members, player_tag)
    if calculated_rank <= 0 or calculated_rank > len(league_members):
        raise ValueError(f"Invalid rank {calculated_rank} for player {player_tag}")
    player_group_data = league_members[calculated_rank - 1]
    league_tier_name  = get_name_to_id(json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID))
    max_attacks = get_weekly_attacks(league_tier_name)
    group_total_attacks, group_full_attackers = _group_attack_stats(league_members, max_attacks)
    return RankedWeek(
        league_group_tag     = league_group_tag,
        league_season_id     = league_season_id,
        player_tag           = json_get(player_data_api, JSON_PLAYER_DATA.TAG),
        trophies             = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_TROPHIES),
        rank                 = calculated_rank,
        start_day            = get_last_monday(),
        end_day              = get_next_monday(),
        max_attacks          = max_attacks,
        townhall             = json_get(player_data_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
        attack_wins          = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT),
        attack_losses        = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT),
        defense_wins         = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_WIN_COUNT),
        defense_losses       = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_LOSE_COUNT),
        league_tier          = league_tier_name,
        group_total_attacks  = group_total_attacks,
        group_full_attackers = group_full_attackers,
    )


def create_db_ranked_week_done(done_week_db : RankedWeek,  league_group_data_api) -> RankedWeek:
    league_members = json_get(league_group_data_api, JSON_RANKED_GROUP_DATA.MEMBERS)
    player_tag     = done_week_db.player_tag
    calculated_rank           = get_member_rank_by_tag(league_members, player_tag)
    if calculated_rank <= 0 or calculated_rank > len(league_members):
        raise ValueError(f"Invalid rank {calculated_rank} for player {player_tag}")
    player_group_data = league_members[calculated_rank - 1]
    group_total_attacks, group_full_attackers = _group_attack_stats(league_members, done_week_db.max_attacks or 0)
    return RankedWeek(
        league_group_tag     = done_week_db.league_group_tag,
        league_season_id     = done_week_db.league_season_id,
        player_tag           = done_week_db.player_tag,
        trophies             = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_TROPHIES),
        rank                 = calculated_rank,
        start_day            = done_week_db.start_day,
        end_day              = done_week_db.end_day,
        max_attacks          = done_week_db.max_attacks,
        townhall             = done_week_db.townhall,
        attack_wins          = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT),
        attack_losses        = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT),
        defense_wins         = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_WIN_COUNT),
        defense_losses       = json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_LOSE_COUNT),
        league_tier          = done_week_db.league_tier,
        group_total_attacks  = group_total_attacks,
        group_full_attackers = group_full_attackers,
    )

def create_db_ranked_battle_log(opponent_db: Player, attack_api: dict, player_data_api: dict, is_attack: bool):
    return RankedBattleLog(
        league_group_tag = json_get(player_data_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG),
        league_season_id = json_get(player_data_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID),
        player_tag       = json_get(player_data_api, JSON_PLAYER_DATA.TAG),
        opponent_th      = opponent_db.current_th,
        attack           = is_attack,
        stars            = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_STARS),
        percentage       = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_DESTRUCTION),
        trophies         = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_TROPHIES),
        opponent_tag     = opponent_db.tag,
        opponent_name    = opponent_db.name,
        time             = parse_iso_datetime(json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_CREATION_TIME)),
    )


def create_db_battle_log(player: Player, battle_api: dict):
    resources = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES)
    return BattleLog(
        player_tag       = player.tag,
        opponent_tag     = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG),
        loot_gold        = get_resource_amount(resources, "Gold"),
        loot_elixir      = get_resource_amount(resources, "Elixir"),
        loot_dark_elixir = get_resource_amount(resources, "DarkElixir"),
        attack           = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_ATTACK),
        stars            = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_STARS),
        percentage       = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_DESTRUCTION),
        type             = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_BATTLE_TYPE),
    )


def create_db_clan_war(war_data: dict, clan_full_api: dict = None, opp_full_api: dict = None) -> ClanWar:
    if not isinstance(war_data, dict):
        raise TypeError(f"Expected war dict, got {type(war_data).__name__}")
    clan_data = json_get(war_data, JSON_CLAN_WAR_DATA.CLAN,     default={}, raise_on_missing=False) or {}
    opp_data  = json_get(war_data, JSON_CLAN_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {}
    return ClanWar(
        state                    = json_get(war_data,  JSON_CLAN_WAR_DATA.STATE),
        clan_tag                 = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_TAG, raise_on_missing=False),
        team_size                = json_get(war_data,  JSON_CLAN_WAR_DATA.TEAM_SIZE),
        preparation_start_time   = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.PREPARATION_START_TIME)),
        start_time               = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.START_TIME)),
        end_time                 = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.END_TIME)),
        clan_name                = json_get(clan_full_api,  JSON_CLAN_DATA.NAME,                 raise_on_missing=False) if clan_full_api else None,
        clan_badge               = json_get(clan_data,      JSON_CLAN_WAR_DATA.SIDE_BADGE_LARGE, raise_on_missing=False),
        cwl_league               = json_get(clan_full_api,  JSON_CLAN_DATA.WAR_LEAGUE,           raise_on_missing=False) if clan_full_api else None,
        clan_location            = json_get(clan_full_api,  JSON_CLAN_DATA.LOCATION,             raise_on_missing=False) if clan_full_api else None,
        clan_wars_won            = json_get(clan_full_api,  JSON_CLAN_DATA.WAR_WINS,             raise_on_missing=False) if clan_full_api else None,
        clan_war_frequency       = json_get(clan_full_api,  JSON_CLAN_DATA.WAR_FREQUENCY,        raise_on_missing=False) if clan_full_api else None,
        clan_win_streak          = json_get(clan_full_api,  JSON_CLAN_DATA.WIN_STREAK,           raise_on_missing=False) if clan_full_api else None,
        opponent_tag             = json_get(opp_data,       JSON_CLAN_WAR_DATA.SIDE_TAG,         raise_on_missing=False),
        opponent_name            = json_get(opp_data,       JSON_CLAN_WAR_DATA.SIDE_NAME,        raise_on_missing=False),
        opponent_clan_level      = json_get(opp_data,       JSON_CLAN_WAR_DATA.SIDE_CLAN_LEVEL,  raise_on_missing=False),
        opponent_clan_badge      = json_get(opp_data,       JSON_CLAN_WAR_DATA.SIDE_BADGE_LARGE, raise_on_missing=False),
        opponent_clan_location   = json_get(opp_full_api,   JSON_CLAN_DATA.LOCATION,             raise_on_missing=False) if opp_full_api else None,
        opponent_cwl_league      = json_get(opp_full_api,   JSON_CLAN_DATA.WAR_LEAGUE,           raise_on_missing=False) if opp_full_api else None,
        opponent_wars_won        = json_get(opp_full_api,   JSON_CLAN_DATA.WAR_WINS,             raise_on_missing=False) if opp_full_api else None,
        opponent_war_frequency   = json_get(opp_full_api,   JSON_CLAN_DATA.WAR_FREQUENCY,        raise_on_missing=False) if opp_full_api else None,
        opponent_win_streak      = json_get(opp_full_api,   JSON_CLAN_DATA.WIN_STREAK,           raise_on_missing=False) if opp_full_api else None,
        clan_stars               = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_STARS,           default=0,   raise_on_missing=False),
        clan_attacks             = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_ATTACKS,         default=0,   raise_on_missing=False),
        clan_destruction_pct     = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_DESTRUCTION_PCT, default=0.0, raise_on_missing=False),
        opponent_stars           = json_get(opp_data,  JSON_CLAN_WAR_DATA.SIDE_STARS,           default=0,   raise_on_missing=False),
        opponent_attacks         = json_get(opp_data,  JSON_CLAN_WAR_DATA.SIDE_ATTACKS,         default=0,   raise_on_missing=False),
        opponent_destruction_pct = json_get(opp_data,  JSON_CLAN_WAR_DATA.SIDE_DESTRUCTION_PCT, default=0.0, raise_on_missing=False),
    )


def create_db_clan_war_member(clan_war: ClanWar, member: dict, is_opponent: bool, ranked_league: str = None) -> ClanWarMember:
    if not isinstance(clan_war, ClanWar):
        raise TypeError(f"Expected ClanWar object, got {type(clan_war).__name__}")
    return ClanWarMember(
        clan_war_id      = clan_war.id,
        is_opponent      = is_opponent,
        player_tag       = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_TAG),
        player_name      = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_NAME),
        town_hall_level  = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_TH_LEVEL),
        map_position     = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_MAP_POSITION),
        opponent_attacks = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_OPP_ATTACKS, default=0, raise_on_missing=False),
        ranked_league    = ranked_league,
    )


def create_db_clan_war_attack(clan_war: ClanWar, attack: dict) -> ClanWarAttack:
    if not isinstance(clan_war, ClanWar):
        raise TypeError(f"Expected ClanWar object, got {type(clan_war).__name__}")
    return ClanWarAttack(
        clan_war_id     = clan_war.id,
        attacker_tag    = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_ATTACKER_TAG),
        defender_tag    = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_DEFENDER_TAG),
        stars           = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_STARS),
        destruction_pct = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_DESTRUCTION_PCT),
        attack_order    = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_ORDER),
        duration        = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_DURATION),
    )


# ── Gets ──────────────────────────────────────────────────────────────────────

def db_player_get(tag: str) -> Player:
    return db.session.get(Player, tag)

def db_player_get_all(in_clan: bool = True) -> List[Player]:
    return Player.query.filter(Player.in_clan == in_clan).all()

def db_ranked_week_get(group_tag, season_id, player_tag) -> RankedWeek:
    return db.session.get(RankedWeek, (group_tag, season_id, player_tag))

def db_raid_weekend_get(start_time, end_time) -> RaidWeekend:
    return RaidWeekend.query.filter(RaidWeekend.start_time == start_time, RaidWeekend.end_time == end_time).first()

def db_ranked_week_get_all_done() -> List[RankedWeek]:
    now_utc = dt.datetime.now(dt.timezone.utc)
    cutoff_date = now_utc.date() if now_utc.hour >= 6 else now_utc.date() - dt.timedelta(days=1)
    return RankedWeek.query.filter(
        RankedWeek.is_done == False,
        RankedWeek.end_day <= cutoff_date,
    ).all()

def db_ranked_battle_log_get(ranked_week: RankedWeek, opponent_tag: str, is_attack: bool) -> RankedBattleLog:
    return RankedBattleLog.query.filter(
        RankedBattleLog.league_group_tag == ranked_week.league_group_tag,
        RankedBattleLog.league_season_id == ranked_week.league_season_id,
        RankedBattleLog.player_tag       == ranked_week.player_tag,
        RankedBattleLog.attack           == is_attack,
        RankedBattleLog.opponent_tag     == opponent_tag,
    ).first()

def db_battle_log_get(player: Player, battle_api: dict):
    opponent_tag     = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG)
    resources        = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES)
    loot_gold        = get_resource_amount(resources, "Gold")
    loot_elixir      = get_resource_amount(resources, "Elixir")
    loot_dark_elixir = get_resource_amount(resources, "DarkElixir")
    return BattleLog.query.filter(
        BattleLog.player_tag      == player.tag,
        BattleLog.opponent_tag    == opponent_tag,
        BattleLog.loot_gold       == loot_gold,
        BattleLog.loot_elixir     == loot_elixir,
        BattleLog.loot_dark_elixir == loot_dark_elixir,
    ).first()

def db_raid_weekend_log_get(raid_weekend, defender_tag, district_name, percentage, percentage_total) -> RaidWeekendLog:
    return RaidWeekendLog.query.filter(
        RaidWeekendLog.raid_weekend_id  == raid_weekend.id,
        RaidWeekendLog.defender_tag     == defender_tag,
        RaidWeekendLog.district_name    == district_name,
        RaidWeekendLog.percentage       == percentage,
        RaidWeekendLog.percentage_total == percentage_total,
    ).first()

def db_clan_war_get(start_time) -> ClanWar:
    return ClanWar.query.filter_by(start_time=start_time).first()


# ── Create new ────────────────────────────────────────────────────────────────

def db_player_create_new(player: Player) -> Player:
    if not isinstance(player, Player):
        raise TypeError(f"Expected Player object, got {type(player).__name__}")
    logging.debug(f"Adding player {player.name}")
    db.session.add(player)
    return player

def db_ranked_week_create_new(ranked_week: RankedWeek) -> RankedWeek:
    if not isinstance(ranked_week, RankedWeek):
        raise TypeError(f"Expected RankedWeek object, got {type(ranked_week).__name__}")
    logging.debug(f"Adding ranked week for tag: {ranked_week.player_tag}")
    db.session.add(ranked_week)
    return ranked_week

def db_raid_weekend_create_new(raid_weekend: RaidWeekend) -> RaidWeekend:
    if not isinstance(raid_weekend, RaidWeekend):
        raise TypeError(f"Expected RaidWeekend object, got {type(raid_weekend).__name__}")
    logging.debug(f"Adding raid weekend for endtime: {raid_weekend.end_time}")
    db.session.add(raid_weekend)
    return raid_weekend

def db_raid_weekend_log_create_new(raid_weekend_log: RaidWeekendLog) -> RaidWeekendLog:
    if not isinstance(raid_weekend_log, RaidWeekendLog):
        raise TypeError(f"Expected RaidWeekendLog object, got {type(raid_weekend_log).__name__}")
    logging.debug(f"Adding raid weekend log for defender: {raid_weekend_log.defender_name}")
    db.session.add(raid_weekend_log)
    return raid_weekend_log

def db_uptime_tracker_create_new(uptime: UptimeTracker):
    if not isinstance(uptime, UptimeTracker):
        raise TypeError(f"Expected UptimeTracker object, got {type(uptime).__name__}")
    logging.debug(f"Adding uptime tracker for {uptime.function}")
    db.session.add(uptime)
    return uptime

def db_ranked_battle_log_create_new(ranked_battle_log: RankedBattleLog):
    if not isinstance(ranked_battle_log, RankedBattleLog):
        raise TypeError(f"Expected RankedBattleLog object, got {type(ranked_battle_log).__name__}")
    logging.debug(f"Adding ranked_battle_log for tag: {ranked_battle_log.player_tag}")
    db.session.add(ranked_battle_log)
    return ranked_battle_log

def db_battle_log_create_new(battle_log: BattleLog):
    if not isinstance(battle_log, BattleLog):
        raise TypeError(f"Expected BattleLog, got {type(battle_log).__name__}")
    logging.debug(f"Adding battle_log for tag: {battle_log.player_tag}")
    db.session.add(battle_log)
    return battle_log


# ── Updates ───────────────────────────────────────────────────────────────────

def db_player_update_all_inactive() -> None:
    logging.debug("Setting all players inactive")
    return Player.query.filter_by(in_clan=True).update(
        {Player.in_clan: False}, synchronize_session='fetch'
    )

def db_player_update(player: Player, updated_player: Player) -> Player:
    if (player.current_th  != updated_player.current_th or
            player.name    != updated_player.name or
            player.league_tier != updated_player.league_tier or
            player.in_clan != updated_player.in_clan):
        player.current_th  = updated_player.current_th
        player.name        = updated_player.name
        player.in_clan     = updated_player.in_clan
        player.league_tier = updated_player.league_tier
        logging.debug(f"Updating player: {player.name}")
    return player

def db_ranked_week_update(ranked_week: RankedWeek, updated: RankedWeek, is_done: bool = False) -> RankedWeek:
    if (ranked_week.trophies             != updated.trophies or
            ranked_week.rank             != updated.rank or
            ranked_week.attack_wins      != updated.attack_wins or
            ranked_week.attack_losses    != updated.attack_losses or
            ranked_week.defense_wins     != updated.defense_wins or
            ranked_week.defense_losses   != updated.defense_losses or
            ranked_week.group_total_attacks  != updated.group_total_attacks or
            ranked_week.group_full_attackers != updated.group_full_attackers):
        ranked_week.trophies             = updated.trophies
        ranked_week.rank                 = updated.rank
        ranked_week.attack_wins          = updated.attack_wins
        ranked_week.attack_losses        = updated.attack_losses
        ranked_week.defense_wins         = updated.defense_wins
        ranked_week.defense_losses       = updated.defense_losses
        ranked_week.group_total_attacks  = updated.group_total_attacks
        ranked_week.group_full_attackers = updated.group_full_attackers
        logging.debug(f"Updated ranked week for {ranked_week.player.name}")
    ranked_week.is_done = is_done
    return ranked_week

def db_raid_weekend_update(raid_weekend: RaidWeekend, updated: RaidWeekend) -> RaidWeekend:
    if (raid_weekend.state                    != updated.state or
            raid_weekend.capital_total_loot   != updated.capital_total_loot or
            raid_weekend.raids_completed      != updated.raids_completed or
            raid_weekend.total_attacks        != updated.total_attacks or
            raid_weekend.enemy_districts_destroyed != updated.enemy_districts_destroyed or
            raid_weekend.offensive_reward     != updated.offensive_reward or
            raid_weekend.defensive_reward     != updated.defensive_reward):
        raid_weekend.state                    = updated.state
        raid_weekend.capital_total_loot       = updated.capital_total_loot
        raid_weekend.raids_completed          = updated.raids_completed
        raid_weekend.total_attacks            = updated.total_attacks
        raid_weekend.enemy_districts_destroyed = updated.enemy_districts_destroyed
        raid_weekend.offensive_reward         = updated.offensive_reward
        raid_weekend.defensive_reward         = updated.defensive_reward
        logging.debug(f"Updated raid weekend {raid_weekend.start_time}")
    return raid_weekend

def db_clan_war_update(existing: ClanWar, updated: ClanWar):
    if not isinstance(existing, ClanWar) or not isinstance(updated, ClanWar):
        raise TypeError("Expected ClanWar objects")
    existing.state                    = updated.state
    existing.clan_stars               = updated.clan_stars
    existing.clan_attacks             = updated.clan_attacks
    existing.clan_destruction_pct     = updated.clan_destruction_pct
    existing.opponent_stars           = updated.opponent_stars
    existing.opponent_attacks         = updated.opponent_attacks
    existing.opponent_destruction_pct = updated.opponent_destruction_pct
    logging.debug(f"Updated clan war {existing.start_time}")
    return existing


# ── CWL helpers ───────────────────────────────────────────────────────────────

def db_cwl_season_get(season: str):
    return CWLSeason.query.filter_by(season=season).first()

def db_cwl_season_create(season_str: str, state: str, league_name: str) -> CWLSeason:
    obj = CWLSeason(season=season_str, state=state, league_name=league_name)
    db.session.add(obj)
    db.session.flush()
    logging.debug(f"Created CWL season {season_str}")
    return obj

def db_cwl_season_update(existing: CWLSeason, state: str, league_name: str):
    existing.state       = state
    existing.league_name = league_name or existing.league_name
    logging.debug(f"Updated CWL season {existing.season} state={state}")

def db_cwl_war_get(war_tag: str) -> CWLWar:
    return CWLWar.query.filter_by(war_tag=war_tag).first()

def create_db_cwl_war(season_id: int, round_number: int, war_tag: str, war_data: dict,
                      clan_api: dict = None, opp_api: dict = None) -> CWLWar:
    clan = json_get(war_data, JSON_CWL_WAR_DATA.CLAN,     default={}, raise_on_missing=False) or {}
    opp  = json_get(war_data, JSON_CWL_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {}
    return CWLWar(
        season_id            = season_id,
        round_number         = round_number,
        war_tag              = war_tag,
        state                = json_get(war_data, JSON_CWL_WAR_DATA.STATE),
        start_time           = parse_iso_datetime(json_get(war_data, JSON_CWL_WAR_DATA.START_TIME)),
        end_time             = parse_iso_datetime(json_get(war_data, JSON_CWL_WAR_DATA.END_TIME)),
        team_size            = json_get(war_data, JSON_CWL_WAR_DATA.TEAM_SIZE),
        clan_tag             = json_get(clan, JSON_CWL_WAR_DATA.SIDE_TAG),
        clan_name            = json_get(clan, JSON_CWL_WAR_DATA.SIDE_NAME),
        clan_badge           = json_get(clan, JSON_CWL_WAR_DATA.SIDE_BADGE),
        clan_level           = json_get(clan, JSON_CWL_WAR_DATA.SIDE_CLAN_LEVEL,  raise_on_missing=False),
        clan_cwl_league      = json_get(clan_api, JSON_CLAN_DATA.WAR_LEAGUE,      raise_on_missing=False) if clan_api else None,
        clan_location        = json_get(clan_api, JSON_CLAN_DATA.LOCATION,        raise_on_missing=False) if clan_api else None,
        clan_wars_won        = json_get(clan_api, JSON_CLAN_DATA.WAR_WINS,        raise_on_missing=False) if clan_api else None,
        clan_war_frequency   = json_get(clan_api, JSON_CLAN_DATA.WAR_FREQUENCY,   raise_on_missing=False) if clan_api else None,
        clan_win_streak      = json_get(clan_api, JSON_CLAN_DATA.WIN_STREAK,      raise_on_missing=False) if clan_api else None,
        clan_stars           = json_get(clan, JSON_CWL_WAR_DATA.SIDE_STARS,       default=0, raise_on_missing=False) or 0,
        clan_attacks         = json_get(clan, JSON_CWL_WAR_DATA.SIDE_ATTACKS,     default=0, raise_on_missing=False) or 0,
        clan_destruction_pct = json_get(clan, JSON_CWL_WAR_DATA.SIDE_DESTRUCTION, default=0.0, raise_on_missing=False) or 0.0,
        opp_tag              = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_TAG),
        opp_name             = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_NAME),
        opp_badge            = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_BADGE),
        opp_level            = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_CLAN_LEVEL,  raise_on_missing=False),
        opp_cwl_league       = json_get(opp_api,  JSON_CLAN_DATA.WAR_LEAGUE,      raise_on_missing=False) if opp_api else None,
        opp_location         = json_get(opp_api,  JSON_CLAN_DATA.LOCATION,        raise_on_missing=False) if opp_api else None,
        opp_wars_won         = json_get(opp_api,  JSON_CLAN_DATA.WAR_WINS,        raise_on_missing=False) if opp_api else None,
        opp_war_frequency    = json_get(opp_api,  JSON_CLAN_DATA.WAR_FREQUENCY,   raise_on_missing=False) if opp_api else None,
        opp_win_streak       = json_get(opp_api,  JSON_CLAN_DATA.WIN_STREAK,      raise_on_missing=False) if opp_api else None,
        opp_stars            = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_STARS,       default=0, raise_on_missing=False) or 0,
        opp_attacks          = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_ATTACKS,     default=0, raise_on_missing=False) or 0,
        opp_destruction_pct  = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_DESTRUCTION, default=0.0, raise_on_missing=False) or 0.0,
    )

def db_cwl_war_update(existing: CWLWar, war_data: dict):
    clan = json_get(war_data, JSON_CWL_WAR_DATA.CLAN,     default={}, raise_on_missing=False) or {}
    opp  = json_get(war_data, JSON_CWL_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {}
    existing.state                = json_get(war_data, JSON_CWL_WAR_DATA.STATE)
    existing.clan_stars           = json_get(clan, JSON_CWL_WAR_DATA.SIDE_STARS,       default=0,   raise_on_missing=False) or 0
    existing.clan_attacks         = json_get(clan, JSON_CWL_WAR_DATA.SIDE_ATTACKS,     default=0,   raise_on_missing=False) or 0
    existing.clan_destruction_pct = json_get(clan, JSON_CWL_WAR_DATA.SIDE_DESTRUCTION, default=0.0, raise_on_missing=False) or 0.0
    existing.opp_stars            = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_STARS,       default=0,   raise_on_missing=False) or 0
    existing.opp_attacks          = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_ATTACKS,     default=0,   raise_on_missing=False) or 0
    existing.opp_destruction_pct  = json_get(opp,  JSON_CWL_WAR_DATA.SIDE_DESTRUCTION, default=0.0, raise_on_missing=False) or 0.0
    logging.debug(f"Updated CWL war {existing.war_tag}")

def create_db_cwl_clan_member(clan_id: int, member_data: dict, ranked_league: str = None) -> CWLClanMember:
    return CWLClanMember(
        clan_id         = clan_id,
        player_tag      = json_get(member_data, JSON_CWL_GROUP_DATA.CLAN_MEMBER_TAG, raise_on_missing=False),
        player_name     = json_get(member_data, JSON_CWL_GROUP_DATA.CLAN_MEMBER_NAME, raise_on_missing=False),
        town_hall_level = json_get(member_data, JSON_CWL_GROUP_DATA.CLAN_MEMBER_TH, raise_on_missing=False),
        ranked_league   = ranked_league,
    )


def create_db_cwl_member(war_id: int, clan_tag: str, member_data: dict, is_opponent: bool, ranked_league: str = None) -> CWLMember:
    return CWLMember(
        war_id          = war_id,
        clan_tag        = clan_tag,
        player_tag      = json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_TAG),
        player_name     = json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_NAME),
        town_hall_level = json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_TH),
        map_position    = json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_POS),
        is_opponent     = is_opponent,
        ranked_league   = ranked_league,
    )

def create_db_cwl_attack(war_id: int, attack_data: dict) -> CWLAttack:
    return CWLAttack(
        war_id          = war_id,
        attacker_tag    = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_ATTACKER_TAG),
        defender_tag    = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_DEFENDER_TAG),
        stars           = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_STARS),
        destruction_pct = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_DESTRUCTION),
        attack_order    = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_ORDER),
        duration        = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_DURATION),
    )
