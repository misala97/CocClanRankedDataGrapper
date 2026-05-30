from databaseModels import * 
from help_functions import json_get, JSON_BATTLE_LOG_DATA, JSON_PLAYER_DATA, JSON_RANKED_GROUP_DATA, JSON_RAID_WEEKEND_DATA, JSON_CLAN_WAR_DATA
import logging
from typing import List
from help_functions import get_name_to_id, get_resource_amount,parse_iso_datetime,get_weekly_attacks,get_member_rank_by_tag, get_next_monday, get_last_monday
from sqlalchemy import or_

# Create Funktionen für DB Objekte
def create_db_player_from_api(player_data_api: dict, in_clan: bool = True) -> Player:
    if not isinstance(player_data_api, dict):
        raise TypeError(f"Expected Player dict, got {type(player_data_api).__name__}")
        
    return Player(
        tag = json_get(player_data_api, JSON_PLAYER_DATA.TAG),
        name = json_get(player_data_api, JSON_PLAYER_DATA.NAME),
        current_th = json_get(player_data_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
        in_clan = in_clan,
        league_tier = get_name_to_id(json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID)),     
        league_icon = json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ICON_URLS.LARGE, "Unranked")     
    )

def create_db_raid_weekend_from_api(current_raid_weekend: dict):
    if not isinstance(current_raid_weekend, dict):
        raise TypeError(f"Expected Raid dict, got {type(raid_api).__name__}")
    
    
        
    return RaidWeekend(
        startTime = parse_iso_datetime(json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_STARTTIME)),
        endTime = parse_iso_datetime(json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ENDTIME)),
        state = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_STATE),
        capitalTotalLoot = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_CAPITALTOTALLOOT),
        raidsCompleted = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_RAIDSCOMPLETED),
        totalAttacks = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_TOTALATTACKS),
        enemyDistrictsDestroyed = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ENEMYDISTRICTSDESTROYED),
        offensiveReward = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_OFFENSIVEREWARD),
        defensiveReward = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_DEFENSIVEREWARD) 
    )
    
def create_db_raid_weekend_log(raid_weekend: RaidWeekend, player_tag: str, district_name: str, loot: int, percentage: int, percentage_total: int, stars: int, defender_tag: str, defender_name: str, district_level: int, total_loot_all_atacks) -> RaidWeekendLog:
    if not isinstance(raid_weekend, RaidWeekend):
        raise TypeError(f"Expected RaidWeekend object, got {type(raid_weekend).__name__}")

    return RaidWeekendLog(
        raid_weekend_id=raid_weekend.id,
        playerTag=player_tag,
        defenderName=defender_name,
        defenderTag=defender_tag,
        districLevel=district_level,
        totalLootAllAttacks=total_loot_all_atacks,
        districtName=district_name,
        percentage=percentage,
        percentageTotal=percentage_total,
        stars=stars,
    )
    
def create_db_uptime_tracker(func_name: str, duration: str) -> UptimeTracker:    
    return UptimeTracker(
        function = func_name,
        duration = duration
    )
    
def create_db_ranked_week(league_group_tag:str, league_season_id: int, player_data_api: dict, league_group_data_api: dict) -> RankedWeek:
    league_members = json_get(league_group_data_api, JSON_RANKED_GROUP_DATA.MEMBERS)
    player_tag = json_get(player_data_api, JSON_PLAYER_DATA.TAG)
    rank = get_member_rank_by_tag(league_members, player_tag)
    if rank <= 0 or rank > len(league_members):
        raise ValueError(f"Invalid rank {rank} for player {player_tag}")
    player_group_data = league_members[rank-1]
    league_tier_name = get_name_to_id(json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID))
    league_icon = json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.ICON_URLS.LARGE, "Unranked")  
    
    return RankedWeek(
            league_group_tag=league_group_tag,
            league_season_id=league_season_id,
            player_tag=json_get(player_data_api, JSON_PLAYER_DATA.TAG),
            trophies=json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_TROPHIES),
            rank=rank,
            start_day=get_last_monday(),
            end_day=get_next_monday(),
            max_attacks=get_weekly_attacks(league_tier_name),
            townhall=json_get(player_data_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
            attack_wins=json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_WIN_COUNT),
            attack_losses=json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_ATTACK_LOSE_COUNT),
            defense_wins=json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_WIN_COUNT),
            defense_losses=json_get(player_group_data, JSON_RANKED_GROUP_DATA.MEMBERS_DEFENSE_LOSE_COUNT),
            league_tier=league_tier_name,
            league_icon = league_icon
    )
    
def create_db_ranked_battle_log(opponent_db:Player, attack_api : dict, player_data_api: dict , is_attack : bool):
    return RankedBattleLog(
            league_group_tag = json_get(player_data_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG),
            league_season_id = json_get(player_data_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID),
            player_tag = json_get(player_data_api, JSON_PLAYER_DATA.TAG),
            opponent_th = opponent_db.current_th,
            attack = is_attack,
            stars = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_STARS),
            percentage = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_DESTRUCTION),
            trophies = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_TROPHIES),
            opponent_tag = opponent_db.tag,
            opponent_name = opponent_db.name,
            time = parse_iso_datetime(json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_CREATION_TIME))
        )
    
    
def create_db_battle_log(player: Player, battle_api : dict):
    resources = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES)
    
    return BattleLog(
        player_tag = player.tag,
        opponent_tag = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG),
        loot_gold = get_resource_amount(resources, "Gold"),
        loot_elixir =  get_resource_amount(resources, "Elixir"),
        loot_dark_elixir = get_resource_amount(resources, "DarkElixir"),
        
        attack = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_ATTACK),
        stars = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_STARS),
        percentage = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_DESTRUCTION),
        type = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_BATTLE_TYPE)
        )


#Tatsächliche dbmanipulatione
#Gets
def db_player_get(tag: str) -> Player:
    return db.session.get(Player, tag)

def db_player_get_all(in_clan:bool = True) -> List[Player]:
    return Player.query.filter(Player.in_clan == in_clan).all()

def db_ranked_week_get(group_tag: str, season_id : str, player_tag: str) ->List[RankedWeek]:
    return db.session.get(RankedWeek, (group_tag, season_id, player_tag))

def db_raid_weekend_get(start_time, end_time) -> RaidWeekend:
    return RaidWeekend.query.filter(RaidWeekend.startTime == start_time, RaidWeekend.endTime == end_time).first()

def db_ranked_week_get_all_done() ->List[RankedWeek]:
    return RankedWeek.query.filter(
        RankedWeek.is_done == False,
        RankedWeek.start_day != get_last_monday(),
        RankedWeek.end_day != get_next_monday()
    ).all()

def db_ranked_battle_log_get(ranked_week: RankedWeek, opponent_tag: str, is_attack: bool) -> RankedBattleLog:
    return RankedBattleLog.query.filter(
        RankedBattleLog.league_group_tag == ranked_week.league_group_tag,
        RankedBattleLog.league_season_id == ranked_week.league_season_id,
        RankedBattleLog.player_tag == ranked_week.player_tag,
        RankedBattleLog.attack == is_attack,
        RankedBattleLog.opponent_tag == opponent_tag # Exact match!
    ).first()
    
    
def db_battle_log_get(player: Player, battle_api : dict):
    
    opponent_tag = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_OPPONENT_TAG)
    resources = json_get(battle_api, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES)
    
    loot_gold = get_resource_amount(resources, "Gold")
    loot_elixir = get_resource_amount(resources, "Elixir")
    loot_dark_elixir = get_resource_amount(resources, "DarkElixir")
    
    return BattleLog.query.filter(
        BattleLog.player_tag == player.tag, # Crucial: restrict to this player
        BattleLog.opponent_tag == opponent_tag,
        BattleLog.loot_gold == loot_gold,
        BattleLog.loot_elixir == loot_elixir,
        BattleLog.loot_dark_elixir == loot_dark_elixir
    ).first()
    
    
def db_raid_weekend_log_get(raid_weekend: RaidWeekend, defender_tag, district_name, percentage: int, percentage_total: int) -> RaidWeekendLog:
    return RaidWeekendLog.query.filter(
        RaidWeekendLog.raid_weekend_id == raid_weekend.id,
        RaidWeekendLog.defenderTag == defender_tag,
        RaidWeekendLog.districtName == district_name,
        RaidWeekendLog.percentage == percentage,
        RaidWeekendLog.percentageTotal == percentage_total,

    ).first()




#Create new
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
    
    logging.debug(f"Adding raid weekend for endtime: {raid_weekend.endTime}")
    db.session.add(raid_weekend)
    
    return raid_weekend

def db_raid_weekend_log_create_new(raid_weekend_log: RaidWeekendLog) -> RaidWeekendLog:
    if not isinstance(raid_weekend_log, RaidWeekendLog):
        raise TypeError(f"Expected RaidWeekendLog object, got {type(raid_weekend_log).__name__}")
    
    logging.debug(f"Adding raid weekend log for defender: {raid_weekend_log.defenderName}")
    db.session.add(raid_weekend_log)
    
    return raid_weekend_log


def db_uptime_tracker_create_new(uptime: UptimeTracker):
    if not isinstance(uptime, UptimeTracker):
        raise TypeError(f"Expected UptimeTracker object, got {type(uptime).__name__}")
    
    logging.debug(f"Adding uptime tracker for {uptime.function} at {uptime.time}")
    db.session.add(uptime)
    
    return uptime     


def db_ranked_battle_log_create_new(ranked_battle_log: RankedBattleLog):
    if not isinstance(ranked_battle_log, RankedBattleLog):
        raise TypeError(f"Expected Ranked BatteLog object, got {type(ranked_battle_log).__name__}")
    
    logging.debug(f"Adding ranked_battle_log for tag: {ranked_battle_log.player_tag}")
    db.session.add(ranked_battle_log)
    
    return ranked_battle_log   

def db_battle_log_create_new(battle_log: BattleLog):
    if not isinstance(battle_log, BattleLog):
        raise TypeError(f"Expected Expected BattleLog, got {type(battle_log).__name__}")
    
    logging.debug(f"Adding battle_log for tag: {battle_log.player_tag}")
    db.session.add(battle_log)
    
    return battle_log     



#Updates
def db_player_update_all_inactive() -> None:
    logging.debug(f"Setting all players inactive")
    return Player.query.filter_by(in_clan=True).update(
        {Player.in_clan: False}, 
        synchronize_session='fetch'
    )
    


def db_player_update(player : Player, updated_player : Player) -> Player:
    if (player.current_th != updated_player.current_th or 
        player.name != updated_player.name or 
        player.league_tier != updated_player.league_tier or
        player.in_clan != updated_player.in_clan):
        
        player.current_th = updated_player.current_th
        player.name = updated_player.name
        player.in_clan = updated_player.in_clan
        player.league_tier = updated_player.league_tier
        player.league_icon = updated_player.league_icon
        
        logging.debug(f"Updating player: {player.name}")
    return player


def db_ranked_week_update(ranked_week: RankedWeek, updated_ranked_week: RankedWeek, is_done:bool = False) -> RankedWeek:

        if(ranked_week.trophies != updated_ranked_week.trophies or
            ranked_week.rank != updated_ranked_week.rank or
            ranked_week.attack_wins != updated_ranked_week.attack_wins or
            ranked_week.attack_losses != updated_ranked_week.attack_losses or
            ranked_week.defense_wins != updated_ranked_week.defense_wins or
            ranked_week.defense_losses != updated_ranked_week.defense_losses):
            
        
            ranked_week.trophies=updated_ranked_week.trophies
            ranked_week.rank=updated_ranked_week.rank
            ranked_week.attack_wins=updated_ranked_week.attack_wins
            ranked_week.attack_losses=updated_ranked_week.attack_losses
            ranked_week.defense_wins=updated_ranked_week.defense_wins
            ranked_week.defense_losses=updated_ranked_week.defense_losses
    
            logging.debug(f"Updated for {ranked_week.player.name}")
        ranked_week.is_done = is_done
        return ranked_week
    
    
    
def db_raid_weekend_update(raid_weekend: RaidWeekend, updated_raid_weekend: RaidWeekend, is_done:bool = False) -> RaidWeekend:

    if(raid_weekend.state != updated_raid_weekend.state or
        raid_weekend.capitalTotalLoot != updated_raid_weekend.capitalTotalLoot or
        raid_weekend.raidsCompleted != updated_raid_weekend.raidsCompleted or
        raid_weekend.totalAttacks != updated_raid_weekend.totalAttacks or
        raid_weekend.enemyDistrictsDestroyed != updated_raid_weekend.enemyDistrictsDestroyed or
        raid_weekend.offensiveReward != updated_raid_weekend.offensiveReward or
        raid_weekend.defensiveReward != updated_raid_weekend.defensiveReward):

        raid_weekend.state = updated_raid_weekend.state
        raid_weekend.capitalTotalLoot = updated_raid_weekend.capitalTotalLoot
        raid_weekend.raidsCompleted = updated_raid_weekend.raidsCompleted
        raid_weekend.totalAttacks = updated_raid_weekend.totalAttacks
        raid_weekend.enemyDistrictsDestroyed = updated_raid_weekend.enemyDistrictsDestroyed
        raid_weekend.offensiveReward = updated_raid_weekend.offensiveReward
        raid_weekend.defensiveReward = updated_raid_weekend.defensiveReward

        logging.debug(f"Updated raid weekend {raid_weekend.startTime}")


# ── Clan War ──────────────────────────────────────────────────────────────────

def create_db_clan_war(war_data: dict) -> ClanWar:
    if not isinstance(war_data, dict):
        raise TypeError(f"Expected war dict, got {type(war_data).__name__}")
    clan_data = json_get(war_data, JSON_CLAN_WAR_DATA.CLAN, default={}, raise_on_missing=False) or {}
    opp_data  = json_get(war_data, JSON_CLAN_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {}
    return ClanWar(
        state                    = json_get(war_data, JSON_CLAN_WAR_DATA.STATE),
        team_size                = json_get(war_data, JSON_CLAN_WAR_DATA.TEAM_SIZE),
        attacks_per_member       = json_get(war_data, JSON_CLAN_WAR_DATA.ATTACKS_PER_MEMBER),
        battle_modifier          = json_get(war_data, JSON_CLAN_WAR_DATA.BATTLE_MODIFIER),
        preparation_start_time   = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.PREPARATION_START_TIME)),
        start_time               = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.START_TIME)),
        end_time                 = parse_iso_datetime(json_get(war_data, JSON_CLAN_WAR_DATA.END_TIME)),
        opponent_tag             = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_TAG,           raise_on_missing=False),
        opponent_name            = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_NAME,          raise_on_missing=False),
        opponent_clan_level      = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_CLAN_LEVEL,    raise_on_missing=False),
        clan_stars               = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_STARS,        default=0, raise_on_missing=False),
        clan_attacks             = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_ATTACKS,      default=0, raise_on_missing=False),
        clan_destruction_pct     = json_get(clan_data, JSON_CLAN_WAR_DATA.SIDE_DESTRUCTION_PCT, default=0.0, raise_on_missing=False),
        opponent_stars           = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_STARS,         default=0, raise_on_missing=False),
        opponent_attacks         = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_ATTACKS,       default=0, raise_on_missing=False),
        opponent_destruction_pct = json_get(opp_data, JSON_CLAN_WAR_DATA.SIDE_DESTRUCTION_PCT, default=0.0, raise_on_missing=False),
    )


def create_db_clan_war_member(clan_war: ClanWar, member: dict, is_opponent: bool) -> ClanWarMember:
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


def db_clan_war_get(start_time) -> ClanWar:
    return ClanWar.query.filter_by(start_time=start_time).first()


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