from datetime import datetime, timedelta, timezone
import logging


class JSONPath:
    """Lightweight helper representing a dotted JSON path that supports attribute chaining.

    Example: JSONPath('leagueTier').ICON_URLS -> JSONPath('leagueTier.iconUrls')
    Converting to `str()` yields the dotted path string.
    """
    def __init__(self, base: str):
        self._base = base

    def __getattr__(self, name: str):
        # Map common uppercase constant names to camelCase JSON keys
        if name.isupper():
            name_map = {
                'ICON_URLS': 'iconUrls',
                'SMALL': 'small',
            }
            seg = name_map.get(name, name.lower())
        else:
            seg = name
        return JSONPath(f"{self._base}.{seg}")

    def __setattr__(self, name: str, value):
        # Allow setting private attributes normally
        if name.startswith('_'):
            return object.__setattr__(self, name, value)

        # If assigning a JSONPath (e.g. NAME = JSONPath('name')), merge bases
        if isinstance(value, JSONPath):
            merged = JSONPath(f"{self._base}.{value._base}")
            return object.__setattr__(self, name, merged)

        # Allow assigning a plain string to append as a segment
        if isinstance(value, str):
            merged = JSONPath(f"{self._base}.{value}")
            return object.__setattr__(self, name, merged)

        # Fallback to normal setattr
        return object.__setattr__(self, name, value)

    def __str__(self):
        return self._base

    def __repr__(self):
        return f"JSONPath('{self._base}')"



class JSON_PLAYER_DATA:
    TAG = JSONPath("tag")
    NAME = JSONPath("name")
    TOWN_HALL_LEVEL = JSONPath("townHallLevel")
    CURRENT_LEAGUE_GROUP_TAG = JSONPath("currentLeagueGroupTag")
    CURRENT_LEAGUE_SEASON_ID = JSONPath("currentLeagueSeasonId")
    LEAGUE_TIER = JSONPath("leagueTier")
    LEAGUE_TIER.NAME = JSONPath("name")
    LEAGUE_TIER.ID = JSONPath("id")
    LEAGUE_TIER.ICON_URLS = JSONPath("iconUrls")
    LEAGUE_TIER.ICON_URLS.LARGE = JSONPath("large")
    
    
class JSON_CLAN_DATA:
    MEMBER_LIST = JSONPath("memberList")
    NAME = JSONPath("name")
    
class JSON_BATTLE_LOG_DATA:
    ITEMS = JSONPath("items")
    ITEMS_BATTLE_TYPE = JSONPath("battleType")
    ITEMS_OPPONENT_TAG = JSONPath("opponentPlayerTag")
    ITEMS_STARS = JSONPath("stars")
    ITEMS_DESTRUCTION = JSONPath("destructionPercentage")
    ITEMS_LOOTED_RESOURCES = JSONPath("lootedResources")
    ITEMS_LOOTED_RESOURCES_NAME = JSONPath("name")
    ITEMS_LOOTED_RESOURCES_AMOUNT = JSONPath("amount")
    ITEMS_ATTACK = JSONPath("attack")
    
class JSON_RAID_WEEKEND_DATA:
    ITEMS = JSONPath("items")
    ITEMS_STATE = JSONPath("state")
    
    ITEMS_STARTTIME = JSONPath("startTime")
    ITEMS_ENDTIME = JSONPath("endTime")
    ITEMS_CAPITALTOTALLOOT = JSONPath("capitalTotalLoot")
    ITEMS_RAIDSCOMPLETED = JSONPath("raidsCompleted")
    ITEMS_TOTALATTACKS = JSONPath("totalAttacks")
    ITEMS_ENEMYDISTRICTSDESTROYED = JSONPath("enemyDistrictsDestroyed")
    ITEMS_OFFENSIVEREWARD = JSONPath("offensiveReward")
    ITEMS_DEFENSIVEREWARD = JSONPath("defensiveReward")
    ITEMS_MEMBERS = JSONPath("members")
    ITEMS_MEMBERS_TAG = JSONPath("tag")
    ITEMS_ATTACKLOG = JSONPath("attackLog")
    ITEMS_ATTACKLOG_DEFENDER = JSONPath("defender")
    ITEMS_ATTACKLOG_DEFENDER.TAG = JSONPath("tag")
    ITEMS_ATTACKLOG_DEFENDER.NAME = JSONPath("name")
    ITEMS_ATTACKLOG_DISTRICTS = JSONPath("districts")
    ITEMS_ATTACKLOG_DISTRICTS_NAME = JSONPath("name")
    ITEMS_ATTACKLOG_DISTRICTS_HALLLEVEL = JSONPath("districtHallLevel")
    ITEMS_ATTACKLOG_DISTRICTS_ATTACKS = JSONPath("attacks")
    ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_PERCENT = JSONPath("destructionPercent")
    ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_STARS = JSONPath("stars")
    ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_ATTACKER = JSONPath("attacker")
    ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_ATTACKER.TAG = JSONPath("tag")
    
    
class JSON_RANKED_GROUP_DATA:
    MEMBERS = JSONPath("members")
    MEMBERS_TROPHIES = JSONPath("leagueTrophies")
    MEMBERS_ATTACK_WIN_COUNT = JSONPath("attackWinCount")
    MEMBERS_ATTACK_LOSE_COUNT = JSONPath("attackLoseCount")
    MEMBERS_DEFENSE_WIN_COUNT = JSONPath("defenseWinCount")
    MEMBERS_DEFENSE_LOSE_COUNT = JSONPath("defenseLoseCount")
    
    ATTACK_LOGS = JSONPath("attackLogs")
    ATTACK_LOGS_OPPONENT_TAG = JSONPath("opponentPlayerTag")
    ATTACK_LOGS_OPPONENT_NAME = JSONPath("opponentName")
    ATTACK_LOGS_STARS = JSONPath("stars")
    ATTACK_LOGS_DESTRUCTION = JSONPath("destructionPercentage")
    ATTACK_LOGS_TROPHIES = JSONPath("trophies")
    ATTACK_LOGS_CREATION_TIME = JSONPath("creationTime")
    
    DEFENSE_LOGS = JSONPath("defenseLogs")
    DEFENSE_LOGS_OPPONENT_TAG = JSONPath("opponentPlayerTag")
    DEFENSE_LOGS_OPPONENT_NAME = JSONPath("opponentName")
    DEFENSE_LOGS_STARS = JSONPath("stars")
    DEFENSE_LOGS_DESTRUCTION = JSONPath("destructionPercentage")
    DEFENSE_LOGS_TROPHIES = JSONPath("trophies")
    DEFENSE_LOGS_CREATION_TIME = JSONPath("creationTime")


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

def get_last_monday(ref_date=None):
    if ref_date is None:
        d = datetime.now().date()
    elif isinstance(ref_date, datetime):
        d = ref_date.date()
    else:
        d = ref_date

    # Monday == 0
    days_since_monday = d.weekday()
    return d - timedelta(days=days_since_monday)
    

def get_next_monday(ref_date=None):
    if ref_date is None:
        d = datetime.now().date()
    elif isinstance(ref_date, datetime):
        d = ref_date.date()
    else:
        d = ref_date

    # Monday == 0
    # 7 - d.weekday() will return 7 if today is Monday, 6 if Tuesday, ..., 1 if Sunday.
    days_until_monday = 7 - d.weekday()
    return d + timedelta(days=days_until_monday)

def get_weekly_attacks(league_string: str):
    league_name = league_string.lower().strip()
    if "legend" in league_name:
        if "iii" in league_name or "3" in league_name: return 24
        elif "ii" in league_name or "2" in league_name: return 30
        else: return 56 

    attack_limits = {
        "skeleton": 6, "barbarian": 6, "archer": 8, "wizard": 8, 
        "valkyrie": 10, "witch": 10, "golem": 12, "p.e.k.k.a": 12, 
        "pekka": 12, "titan": 12, "dragon": 14, "electro": 18
    }

    for league, limit in attack_limits.items():
        if league in league_name: return limit
    return 0

def get_name_to_id(league_id: int) -> str:
    # A dictionary mapping all the IDs to their respective league names
    league_map = {
        105000000: "Unranked",
        105000001: "Skeleton League 1",
        105000002: "Skeleton League 2",
        105000003: "Skeleton League 3",
        105000004: "Barbarian League 4",
        105000005: "Barbarian League 5",
        105000006: "Barbarian League 6",
        105000007: "Archer League 7",
        105000008: "Archer League 8",
        105000009: "Archer League 9",
        105000010: "Wizard League 10",
        105000011: "Wizard League 11",
        105000012: "Wizard League 12",
        105000013: "Valkyrie League 13",
        105000014: "Valkyrie League 14",
        105000015: "Valkyrie League 15",
        105000016: "Witch League 16",
        105000017: "Witch League 17",
        105000018: "Witch League 18",
        105000019: "Golem League 19",
        105000020: "Golem League 20",
        105000021: "Golem League 21",
        105000022: "P.E.K.K.A League 22",
        105000023: "P.E.K.K.A League 23",
        105000024: "P.E.K.K.A League 24",
        105000025: "Titan League 25",
        105000026: "Titan League 26",
        105000027: "Titan League 27",
        105000028: "Dragon League 28",
        105000029: "Dragon League 29",
        105000030: "Dragon League 30",
        105000031: "Electro League 31",
        105000032: "Electro League 32",
        105000033: "Electro League 33",
        105000034: "Legend League III",
        105000035: "Legend League II",
        105000036: "Legend League I"
    }
    
    # Return the corresponding name, or a fallback string if the ID isn't found
    return league_map.get(league_id, "Unknown League")


def get_member_rank_by_tag(members, player_name):
    for index, member in enumerate(members, start=1):
        if member["playerTag"] == player_name:
            return index
    return None


def parse_iso_datetime(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        # MySQL DATETIME does not accept ISO strings with a trailing Z.
        dt = dt.replace("Z", "+00:00")
        return datetime.fromisoformat(dt)
    return dt

def json_get(json_object: dict, key, default=None, raise_on_missing: bool = True):
    """
    Retrieve a value from a nested JSON-like structure using a key or dotted path.

    - `json_object` should be a dict (or nested dict/list structure).
    - `key` can be a single key (str), a dotted path like 'a.b.c', or an iterable of keys.
      Numeric path segments (e.g. 'items.0.name') will be treated as list indices when
      the current value is a list.
    - If `raise_on_missing` is True (default) a KeyError is raised when a path segment
      is missing. Otherwise `default` is returned.
    """
    if json_object is None:
        if raise_on_missing:
            logging.error(f"json_get: json_object is None for key={key}")
            raise KeyError(f"json_object is None")
        return default

    # Build path segments
    if isinstance(key, str):
        path = key.split('.') if '.' in key else [key]
    else:
        try:
            path = list(key)
        except Exception:
            path = [str(key)]

    # Normalize dotted segments so JSONPath or single-string dotted keys work
    normalized = []
    for p in path:
        if isinstance(p, str) and '.' in p:
            normalized.extend(p.split('.'))
        else:
            normalized.append(p)
    path = normalized

    current = json_object
    for segment in path:
        # If current is a list and segment is an integer index
        if isinstance(current, list):
            # allow numeric string indices
            try:
                idx = int(segment)
            except Exception:
                if raise_on_missing:
                    logging.error(f"json_get: expected numeric index for list but got '{segment}'")
                    raise KeyError(f"Expected numeric index for list but got '{segment}'")
                return default
            if idx < 0 or idx >= len(current):
                if raise_on_missing:
                    logging.error(f"json_get: list index {idx} out of range for segment '{segment}'")
                    raise KeyError(f"List index {idx} out of range")
                return default
            current = current[idx]
            continue

        # Otherwise expect dict-like access
        if not isinstance(current, dict):
            if raise_on_missing:
                logging.error(f"json_get: cannot access key '{segment}' on non-dict object: {current}")
                raise KeyError(f"Cannot access key '{segment}' on non-dict object")
            return default

        if segment not in current:
            if raise_on_missing:
                logging.error(f"Key: [{segment}] could not be found in current object")
                raise KeyError(f"Key: [{segment}] could not be found")
            return default

        current = current.get(segment)

    # Warn if the retrieved value is falsy (empty) — keep previous behavior
    #if None == current:
        #logging.warning(f"Key path [{key}] empty or falsy in object.")

    return current