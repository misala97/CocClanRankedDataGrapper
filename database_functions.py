from databaseModels import * 
from help_functions import json_get, JSON_BATTLE_LOG_DATA, JSON_PLAYER_DATA, JSON_RANKED_GROUP_DATA
import logging
from typing import List
from help_functions import get_resource_amount,parse_iso_datetime,get_weekly_attacks,get_member_rank_by_tag, get_next_monday, get_last_monday
from sqlalchemy import or_

# Create Funktionen für DB Objekte
def create_db_player_from_api(api_player: dict, in_clan: bool = True) -> Player:
    if not isinstance(api_player, dict):
        raise TypeError(f"Expected Player dict, got {type(player).__name__}")
        
    return Player(
        tag = json_get(api_player, JSON_PLAYER_DATA.TAG),
        name = json_get(api_player, JSON_PLAYER_DATA.NAME),
        current_th = json_get(api_player, JSON_PLAYER_DATA.TOWN_HALL_LEVEL),
        in_clan = in_clan,
        league_tier = json_get(api_player, JSON_PLAYER_DATA.LEAGUE_TIER.name, "Unranked"),     
        league_icon = json_get(api_player, JSON_PLAYER_DATA.LEAGUE_TIER.ICON_URLS.LARGE, "Unranked")     
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
    league_tier_name = json_get(player_data_api, JSON_PLAYER_DATA.LEAGUE_TIER.NAME)
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