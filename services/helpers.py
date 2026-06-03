import datetime as dt
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(override=True)
LOCAL_TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))

CLEANUP_THRESHOLD = 35

RAID_DISTRICT_MEDALS     = {1: 135, 2: 225, 3: 350, 4: 405, 5: 460}
RAID_CAPITAL_PEAK_MEDALS = {2: 180, 3: 360, 4: 585, 5: 810, 6: 1115, 7: 1240, 8: 1260, 9: 1375, 10: 1450}

def raid_district_medal_value(name, level):
    lvl = int(level or 0)
    if name and 'capital peak' in name.lower():
        return RAID_CAPITAL_PEAK_MEDALS.get(lvl, 0)
    return RAID_DISTRICT_MEDALS.get(lvl, 0)


# ── Timezone ──────────────────────────────────────────────────────────────────

def to_local(naive_utc):
    if naive_utc is None:
        return None
    return naive_utc.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL_TZ)


# ── JSONPath helper ───────────────────────────────────────────────────────────

class JSONPath:
    def __init__(self, base: str):
        self._base = base

    def __getattr__(self, name: str):
        if name.isupper():
            name_map = {'ICON_URLS': 'iconUrls', 'SMALL': 'small'}
            seg = name_map.get(name, name.lower())
        else:
            seg = name
        return JSONPath(f"{self._base}.{seg}")

    def __setattr__(self, name: str, value):
        if name.startswith('_'):
            return object.__setattr__(self, name, value)
        if isinstance(value, JSONPath):
            merged = JSONPath(f"{self._base}.{value._base}")
            return object.__setattr__(self, name, merged)
        if isinstance(value, str):
            merged = JSONPath(f"{self._base}.{value}")
            return object.__setattr__(self, name, merged)
        return object.__setattr__(self, name, value)

    def __str__(self):
        return self._base

    def __repr__(self):
        return f"JSONPath('{self._base}')"


# ── JSON path constants ───────────────────────────────────────────────────────

class JSON_PLAYER_DATA:
    TAG = JSONPath("tag")
    NAME = JSONPath("name")
    TOWN_HALL_LEVEL = JSONPath("townHallLevel")
    WAR_PREFERENCE = JSONPath("warPreference")
    CURRENT_LEAGUE_GROUP_TAG = JSONPath("currentLeagueGroupTag")
    CURRENT_LEAGUE_SEASON_ID = JSONPath("currentLeagueSeasonId")
    LEAGUE_TIER = JSONPath("leagueTier")
    LEAGUE_TIER.NAME = JSONPath("name")
    LEAGUE_TIER.ID = JSONPath("id")
    LEAGUE_TIER.ICON_URLS = JSONPath("iconUrls")
    LEAGUE_TIER.ICON_URLS.LARGE = JSONPath("large")


class JSON_CLAN_DATA:
    MEMBER_LIST   = JSONPath("memberList")
    NAME          = JSONPath("name")
    BADGE_LARGE   = JSONPath("badgeUrls.large")
    WAR_LEAGUE    = JSONPath("warLeague.name")
    LOCATION      = JSONPath("location.name")
    WAR_WINS      = JSONPath("warWins")
    WAR_FREQUENCY = JSONPath("warFrequency")
    WIN_STREAK    = JSONPath("warWinStreak")


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


class JSON_CLAN_WAR_DATA:
    STATE                  = JSONPath("state")
    TEAM_SIZE              = JSONPath("teamSize")
    PREPARATION_START_TIME = JSONPath("preparationStartTime")
    START_TIME             = JSONPath("startTime")
    END_TIME               = JSONPath("endTime")
    CLAN                   = JSONPath("clan")
    OPPONENT               = JSONPath("opponent")
    SIDE_TAG               = JSONPath("tag")
    SIDE_NAME              = JSONPath("name")
    SIDE_CLAN_LEVEL        = JSONPath("clanLevel")
    SIDE_BADGE_LARGE       = JSONPath("badgeUrls.large")
    SIDE_ATTACKS           = JSONPath("attacks")
    SIDE_STARS             = JSONPath("stars")
    SIDE_DESTRUCTION_PCT   = JSONPath("destructionPercentage")
    SIDE_MEMBERS           = JSONPath("members")
    MEMBER_TAG             = JSONPath("tag")
    MEMBER_NAME            = JSONPath("name")
    MEMBER_TH_LEVEL        = JSONPath("townhallLevel")
    MEMBER_MAP_POSITION    = JSONPath("mapPosition")
    MEMBER_OPP_ATTACKS     = JSONPath("opponentAttacks")
    MEMBER_ATTACKS         = JSONPath("attacks")
    MEMBER_LEAGUE          = JSONPath("league.name")
    ATTACK_ATTACKER_TAG    = JSONPath("attackerTag")
    ATTACK_DEFENDER_TAG    = JSONPath("defenderTag")
    ATTACK_STARS           = JSONPath("stars")
    ATTACK_DESTRUCTION_PCT = JSONPath("destructionPercentage")
    ATTACK_ORDER           = JSONPath("order")
    ATTACK_DURATION        = JSONPath("duration")


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


class JSON_CWL_GROUP_DATA:
    STATE           = JSONPath("state")
    SEASON          = JSONPath("season")
    WAR_LEAGUE      = JSONPath("warLeague")
    WAR_LEAGUE_NAME = JSONPath("name")
    CLANS           = JSONPath("clans")
    CLAN_TAG        = JSONPath("tag")
    CLAN_NAME       = JSONPath("name")
    CLAN_BADGE      = JSONPath("badgeUrls.large")
    CLAN_MEMBERS    = JSONPath("members")
    CLAN_MEMBER_TAG = JSONPath("tag")
    CLAN_MEMBER_NAME= JSONPath("name")
    CLAN_MEMBER_TH  = JSONPath("townHallLevel")
    ROUNDS          = JSONPath("rounds")
    ROUND_WAR_TAGS  = JSONPath("warTags")


class JSON_CWL_WAR_DATA:
    STATE        = JSONPath("state")
    TEAM_SIZE    = JSONPath("teamSize")
    START_TIME   = JSONPath("startTime")
    END_TIME     = JSONPath("endTime")
    CLAN         = JSONPath("clan")
    OPPONENT     = JSONPath("opponent")
    SIDE_TAG        = JSONPath("tag")
    SIDE_NAME       = JSONPath("name")
    SIDE_BADGE      = JSONPath("badgeUrls.large")
    SIDE_CLAN_LEVEL = JSONPath("clanLevel")
    SIDE_STARS      = JSONPath("stars")
    SIDE_ATTACKS    = JSONPath("attacks")
    SIDE_DESTRUCTION = JSONPath("destructionPercentage")
    SIDE_MEMBERS    = JSONPath("members")
    MEMBER_TAG   = JSONPath("tag")
    MEMBER_NAME  = JSONPath("name")
    MEMBER_TH    = JSONPath("townhallLevel")
    MEMBER_POS   = JSONPath("mapPosition")
    MEMBER_ATTACKS      = JSONPath("attacks")
    ATTACK_ATTACKER_TAG = JSONPath("attackerTag")
    ATTACK_DEFENDER_TAG = JSONPath("defenderTag")
    ATTACK_STARS        = JSONPath("stars")
    ATTACK_DESTRUCTION  = JSONPath("destructionPercentage")
    ATTACK_ORDER        = JSONPath("order")
    ATTACK_DURATION     = JSONPath("duration")


# ── json_get ──────────────────────────────────────────────────────────────────

def json_get(json_object: dict, key, default=None, raise_on_missing: bool = True):
    if json_object is None:
        if raise_on_missing:
            logging.error(f"json_get: json_object is None for key={key}")
            raise KeyError("json_object is None")
        return default

    if isinstance(key, str):
        path = key.split('.') if '.' in key else [key]
    else:
        try:
            path = list(key)
        except Exception:
            path = [str(key)]

    normalized = []
    for p in path:
        if isinstance(p, str) and '.' in p:
            normalized.extend(p.split('.'))
        else:
            normalized.append(p)
    path = normalized

    current = json_object
    for segment in path:
        if isinstance(current, list):
            try:
                idx = int(segment)
            except Exception:
                if raise_on_missing:
                    logging.error(f"json_get: expected numeric index for list but got '{segment}'")
                    raise KeyError(f"Expected numeric index for list but got '{segment}'")
                return default
            if idx < 0 or idx >= len(current):
                if raise_on_missing:
                    logging.error(f"json_get: list index {idx} out of range")
                    raise KeyError(f"List index {idx} out of range")
                return default
            current = current[idx]
            continue

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

    return current


# ── Misc helpers ──────────────────────────────────────────────────────────────

def get_resource_amount(looted_resources, resource_name):
    for resource in looted_resources:
        if json_get(resource, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES_NAME) == resource_name:
            return json_get(resource, JSON_BATTLE_LOG_DATA.ITEMS_LOOTED_RESOURCES_AMOUNT)
    return 0


def get_last_monday(ref_date=None):
    if ref_date is None:
        d = datetime.now().date()
    elif isinstance(ref_date, datetime):
        d = ref_date.date()
    else:
        d = ref_date
    return d - timedelta(days=d.weekday())


def get_next_monday(ref_date=None):
    if ref_date is None:
        d = datetime.now().date()
    elif isinstance(ref_date, datetime):
        d = ref_date.date()
    else:
        d = ref_date
    return d + timedelta(days=7 - d.weekday())


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


_LEAGUE_MAP = {
    105000000: "Unranked",
    105000001: "Skeleton League 1", 105000002: "Skeleton League 2", 105000003: "Skeleton League 3",
    105000004: "Barbarian League 4", 105000005: "Barbarian League 5", 105000006: "Barbarian League 6",
    105000007: "Archer League 7",   105000008: "Archer League 8",   105000009: "Archer League 9",
    105000010: "Wizard League 10",  105000011: "Wizard League 11",  105000012: "Wizard League 12",
    105000013: "Valkyrie League 13", 105000014: "Valkyrie League 14", 105000015: "Valkyrie League 15",
    105000016: "Witch League 16",   105000017: "Witch League 17",   105000018: "Witch League 18",
    105000019: "Golem League 19",   105000020: "Golem League 20",   105000021: "Golem League 21",
    105000022: "P.E.K.K.A League 22", 105000023: "P.E.K.K.A League 23", 105000024: "P.E.K.K.A League 24",
    105000025: "Titan League 25",   105000026: "Titan League 26",   105000027: "Titan League 27",
    105000028: "Dragon League 28",  105000029: "Dragon League 29",  105000030: "Dragon League 30",
    105000031: "Electro League 31", 105000032: "Electro League 32", 105000033: "Electro League 33",
    105000034: "Legend League III", 105000035: "Legend League II",  105000036: "Legend League I",
}
_LEAGUE_NAME_TO_RANK = {name: (lid - 105000000) for lid, name in _LEAGUE_MAP.items()}


def get_name_to_id(league_id: int) -> str:
    return _LEAGUE_MAP.get(league_id, "Unknown League")


def league_rank(name: str) -> int:
    """Returns 0 (Unranked) → 36 (Legend League I). Unknown names return 0."""
    return _LEAGUE_NAME_TO_RANK.get(name, 0)


_SKIP_LEAGUES = {"Unranked", "Unknown League", None}

def avg_league_name(members) -> str | None:
    """Average ranked league across all members, counting no-data as rank 0."""
    if not members:
        return None
    ranks = [league_rank(m.ranked_league) if m.ranked_league not in _SKIP_LEAGUES else 0 for m in members]
    avg_rank = round(sum(ranks) / len(ranks))
    if avg_rank <= 0:
        return None
    return get_name_to_id(105000000 + avg_rank)


def get_member_rank_by_tag(members, player_name):
    for index, member in enumerate(members, start=1):
        if member["playerTag"] == player_name:
            return index
    return None


def parse_iso_datetime(dt_val):
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        return dt_val
    if isinstance(dt_val, str):
        dt_val = dt_val.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_val)
    return dt_val


# ── League scoring helpers ────────────────────────────────────────────────────

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
        "skeleton 1": {"pro": 50, "dem": 0},  "skeleton 2": {"pro": 50, "dem": 5},
        "skeleton 3": {"pro": 50, "dem": 5},  "barbarian 4": {"pro": 50, "dem": 5},
        "barbarian 5": {"pro": 50, "dem": 5}, "barbarian 6": {"pro": 50, "dem": 5},
        "archer 7": {"pro": 50, "dem": 5},    "archer 8": {"pro": 50, "dem": 5},
        "archer 9": {"pro": 40, "dem": 10},   "wizard 10": {"pro": 35, "dem": 10},
        "wizard 11": {"pro": 50, "dem": 10},  "wizard 12": {"pro": 40, "dem": 10},
        "valkyrie 13": {"pro": 35, "dem": 10},"valkyrie 14": {"pro": 50, "dem": 10},
        "valkyrie 15": {"pro": 40, "dem": 10},"witch 16": {"pro": 35, "dem": 10},
        "witch 17": {"pro": 50, "dem": 10},   "witch 18": {"pro": 40, "dem": 10},
        "golem 19": {"pro": 35, "dem": 10},   "golem 20": {"pro": 50, "dem": 10},
        "golem 21": {"pro": 40, "dem": 10},   "pekka 22": {"pro": 30, "dem": 10},
        "pekka 23": {"pro": 50, "dem": 10},   "pekka 24": {"pro": 40, "dem": 10},
        "titan 25": {"pro": 30, "dem": 15},   "titan 26": {"pro": 50, "dem": 15},
        "titan 27": {"pro": 40, "dem": 15},   "dragon 28": {"pro": 30, "dem": 15},
        "dragon 29": {"pro": 25, "dem": 15},  "dragon 30": {"pro": 25, "dem": 15},
        "electro 31": {"pro": 20, "dem": 15}, "electro 32": {"pro": 20, "dem": 15},
        "electro 33": {"pro": 15, "dem": 15}, "legend iii": {"pro": 5, "dem": 15},
        "legend ii": {"pro": 3, "dem": 15},
    }
    return thresholds.get(name)


EXPECTED_LEAGUE_RANK = {
    7: 1, 8: 2, 9: 3, 10: 5, 11: 7, 12: 9,
    13: 11, 14: 14, 15: 17, 16: 21, 17: 23, 18: 26,
}
_LEGEND_LEAGUE_RANKS = {
    'legend league iii': 34, 'legend league ii': 35, 'legend league i': 36,
}


def _get_league_rank(league_tier):
    if not league_tier:
        return 0
    lower = league_tier.lower()
    if lower in _LEGEND_LEAGUE_RANKS:
        return _LEGEND_LEAGUE_RANKS[lower]
    m = re.search(r'(\d+)$', league_tier)
    return int(m.group(1)) if m else 0


def _calc_th_multiplier(diff, player_th):
    if player_th >= 18:
        if diff >= 0:   return 1.00
        if diff == -1:  return 0.90
        if diff <= -2:  return 0.75
    elif player_th == 17:
        if diff >= 1:   return 1.05
        if diff == 0:   return 0.95
        if diff == -1:  return 0.85
        if diff <= -2:  return 0.75
    else:
        if diff >= 2:  return 1.15
        if diff == 1:  return 1.05
        if diff == 0:  return 0.95
        if diff == -1: return 0.85
        if diff == -2: return 0.75
    return 0.01


def _league_mult(league_tier, player_th):
    rank = _get_league_rank(league_tier)
    expected = EXPECTED_LEAGUE_RANK.get(int(player_th) if player_th else 0, 1)
    diff = rank - expected
    if diff == 0:
        return 1.0
    if diff < 0:
        return 0.99 ** abs(diff)
    mult = 1.0
    for r in range(expected + 1, rank + 1):
        mult *= 1.015 if r >= 32 else 1.005
    return mult


def _ranked_verdict(score_100, att_count, max_attacks):
    missing = max(0, max_attacks - att_count)
    missing_text = f" ({missing} missing)" if missing else ""
    if att_count == 0:
        return 'badge-inactive', 'Inactive', score_100
    if score_100 >= 87: return 'badge-godlike',  'Godlike'  + missing_text, score_100
    if score_100 >= 80: return 'badge-dominant', 'Dominant' + missing_text, score_100
    if score_100 >= 65: return 'badge-wow',      'Very Good'+ missing_text, score_100
    if score_100 >= 58: return 'badge-good',     'Good'     + missing_text, score_100
    if score_100 >= 43: return 'badge-warning',  'Bad'      + missing_text, score_100
    if score_100 >= 29: return 'badge-suck',     'Disaster' + missing_text, score_100
    return 'badge-useless', 'Useless' + missing_text, score_100


def _district_stats(logs):
    district_hits = {}
    for l in logs:
        key = (l.districtName, l.defenderTag)
        district_hits.setdefault(key, []).append(l)
    cleanup_ids = set()
    solo_wipe_count = 0
    for hits in district_hits.values():
        district_done = any((l.percentageTotal or 0) == 100 for l in hits)
        player_total  = sum(l.percentage or 0 for l in hits)
        if len(hits) == 1 and district_done and (hits[0].percentage or 0) < CLEANUP_THRESHOLD:
            cleanup_ids.add(hits[0].id)
        if district_done and player_total == 100:
            solo_wipe_count += 1
    return cleanup_ids, solo_wipe_count


def _compute_cleanup_ids(logs):
    cleanup_ids, _ = _district_stats(logs)
    return cleanup_ids


def _raid_verdict(logs):
    cleanup_ids, solo_wipe_count = _district_stats(logs)
    non_cleanup_count = sum(1 for l in logs if l.id not in cleanup_ids)
    effective_max = max(1, non_cleanup_count)
    total_adj = 0.0
    for l in logs:
        if l.id in cleanup_ids:
            continue
        level = l.districLevel or 5
        try: level = int(level)
        except: level = 5
        level_mult = 1.0 + (level - 5) * (0.07 if level >= 5 else 0.05)
        total_adj += (l.percentage or 0) * level_mult
    adj_per_attack = total_adj / effective_max
    adj_per_attack = adj_per_attack * (1.10 ** solo_wipe_count)
    score_100 = min(round(adj_per_attack * 100 / 73.94), 100)
    if not logs:        return 'badge-inactive', 'Skipped',  score_100
    if score_100 >= 87: return 'badge-godlike',  'Godlike',  score_100
    if score_100 >= 80: return 'badge-dominant', 'Dominant', score_100
    if score_100 >= 65: return 'badge-wow',      'Very Good',score_100
    if score_100 >= 58: return 'badge-good',     'Good',     score_100
    if score_100 >= 43: return 'badge-warning',  'Bad',      score_100
    if score_100 >= 29: return 'badge-suck',     'Disaster', score_100
    return 'badge-useless', 'Useless', score_100
