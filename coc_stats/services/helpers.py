import datetime as dt
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import g

from models import WarCombo

load_dotenv(override=True)
LOCAL_TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))

CLEANUP_THRESHOLD = 35
SKIP_LEAGUES      = {'Unranked', 'Unknown League', None, ''}
IMPORT_WINDOW     = timedelta(minutes=2)

RAID_DISTRICT_MEDALS     = {1: 135, 2: 225, 3: 350, 4: 405, 5: 460}
RAID_CAPITAL_PEAK_MEDALS = {2: 180, 3: 360, 4: 585, 5: 810, 6: 1115, 7: 1240, 8: 1260, 9: 1375, 10: 1450}


def get_combos():
    """Load the war_combo table once per request, cached on Flask's g.
    Returns {(label_a, label_b): (score, verdict_label)} for get_war_verdict()."""
    if 'war_combos' not in g:
        g.war_combos = {(c.label_a, c.label_b): (c.score, c.verdict_label) for c in WarCombo.query.all()}
    return g.war_combos


def _is_attack(log):
    return log.attack is True or log.attack == 1


def filter_import_window(attacks, first_log_time):
    return [
        b for b in attacks
        if not (b.time and first_log_time.get(b.player_tag) and
                b.time <= first_log_time[b.player_tag] + IMPORT_WINDOW)
    ]


def week_cutoff(now_utc, battle_days):
    if battle_days == 7:
        now_local = dt.datetime.now(LOCAL_TZ)
        week_start_date = (now_local - timedelta(days=now_local.weekday())).date()
        return dt.datetime(week_start_date.year, week_start_date.month, week_start_date.day,
                           tzinfo=LOCAL_TZ).astimezone(dt.timezone.utc).replace(tzinfo=None)
    return now_utc - timedelta(days=battle_days)


def is_capital_peak(name):
    return bool(name) and 'capital peak' in name.lower()


def raid_district_medal_value(name, level):
    lvl = int(level or 0)
    if is_capital_peak(name):
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
    WAR_WINS       = JSONPath("warWins")
    WAR_FREQUENCY  = JSONPath("warFrequency")
    WIN_STREAK     = JSONPath("warWinStreak")
    WAR_LOG_PUBLIC = JSONPath("isWarLogPublic")


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
    ITEMS_ATTACKLOG_DEFENDER.BADGE = JSONPath("badgeUrls.large")
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
    WAR_LEAGUE.NAME = JSONPath("name")
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
        d = datetime.now(LOCAL_TZ).date()
    elif isinstance(ref_date, datetime):
        d = ref_date.date()
    else:
        d = ref_date
    return d - timedelta(days=d.weekday())


def get_next_monday(ref_date=None):
    if ref_date is None:
        d = datetime.now(LOCAL_TZ).date()
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

_B = "https://api-assets.clashofclans.com/leaguetiers/326/"
LEAGUE_ICONS: dict[str, str] = {
    "Unranked":             _B + "yyYo5DUFeFBZvmMEQh0ZxvG-1sUOZ_S3kDMB7RllXX0.png",
    "Skeleton League 1":    _B + "CiSJYHyhMuloCpIIJ3n5-xCnRWrEd9vcq_zu6Ahkl3o.png",
    "Skeleton League 2":    _B + "CmM-Tihn6ojPGJstmTK_HC-QairrpYLyRhdKhQjkacQ.png",
    "Skeleton League 3":    _B + "YMnWU25Xs2SvtAkVS2WDDbcUQY-PTfCK9OSvCKJnwJU.png",
    "Barbarian League 4":   _B + "CoTrW7nhyiNIDCI4WHUK-0BuhOxibwd_tfASdtmMWFE.png",
    "Barbarian League 5":   _B + "7Alm6gwA1lYoRn5m8vrXAfbTKIK2fFU7OxfYhYwWJYM.png",
    "Barbarian League 6":   _B + "pQHVG1p0IboE8Ggp0U1YR7U8dWhVn4YSS1zSPH61F0I.png",
    "Archer League 7":      _B + "x1c7byHQmOHQVKGxAn1sqOW2XOCzTYW-e6OKjq-FBco.png",
    "Archer League 8":      _B + "lzneKpnJ_ADL1Xb1rceH7-svqRN1UaLnI7ldd8BbyxI.png",
    "Archer League 9":      _B + "ieEdz9Mqbo7g9iJfXwTnIh7Iwz-37aPEmWma1ENEwXE.png",
    "Wizard League 10":     _B + "3kJYaYpDwKF8AEkwRLkm-947_t2mAhpEQcZJYulPPIA.png",
    "Wizard League 11":     _B + "XazuJHG2wjBq39KEA4g4hh1nKJQwVO0fRoVDPHvWwAY.png",
    "Wizard League 12":     _B + "A_ZoGbh1g8wYRWygsQ_wMgbVz8GXvvfavKwlSx8C8PQ.png",
    "Valkyrie League 13":   _B + "6BwmbzkNm6p2unZonTauFQ_683uNl4NYtoOXJmEs78c.png",
    "Valkyrie League 14":   _B + "7AbbZbiV6whmfa6CZtqt6Ml4NgFH1B-UqCxc59ziqfk.png",
    "Valkyrie League 15":   _B + "vT-0ssHYx5zJbBbbjB5NHPXnlHk76MDxJmG7iKmghc4.png",
    "Witch League 16":      _B + "a3zg3PSqri2WrWD8tGzKs0hJ5OrND1Rx1SJ45f5O0gE.png",
    "Witch League 17":      _B + "3mEMvpajLceJ3EKu7u_JIh_cOEsT7wyh701zum9hqCY.png",
    "Witch League 18":      _B + "GeLamlTvRYNnZp5lEW64pyaORN30rCdrxTjU7oJoTN8.png",
    "Golem League 19":      _B + "yS8XBv_a_SNtCpcofsWMFaojRNwO504Py7HyDCBCjYU.png",
    "Golem League 20":      _B + "uizNRh8glQZuAbLdCa-EQSf3oJnge3nqoXHjtQ6O8pw.png",
    "Golem League 21":      _B + "WkqDvnK0CXI-Nc0TNTKG_fSuzRYoLRC54HFOdMCxVTI.png",
    "P.E.K.K.A League 22":  _B + "iTWXPUUFQy0uEb7NDpMTyzGMFOJvlC4SLAqlHYgC8do.png",
    "P.E.K.K.A League 23":  _B + "0eDMQmsiZ0gs8xzViGfVETnYjwzgELTKwYhH3izevT4.png",
    "P.E.K.K.A League 24":  _B + "vxV7LI0votsz0_n-8lW-Lag96D5HwKsEgEk_7247zC4.png",
    "Titan League 25":      _B + "JLqVXdNkAGjD_yqMRDgu9KK-hDrulNPjsKU4EugHqX8.png",
    "Titan League 26":      _B + "yIfqSgrhiYRcuMbAPCoeCj1FTmfylCLxnrAljEZc8K0.png",
    "Titan League 27":      _B + "1AhObOl55grQIWnGmn1J9qMWq5pmRA3aBObfYkQEjko.png",
    "Dragon League 28":     _B + "YCZ7O_3_c8eCBYvX-92qiWeLc6Md6eNJ5A8O-2vUg7I.png",
    "Dragon League 29":     _B + "DIMeRH3N4lrNObA3zAmk_eUin8nvNeLR89qYznnA--s.png",
    "Dragon League 30":     _B + "g7m9aF8YoYj9b0olPsyT4eUIxyYEmkqr53wYxWmzpE4.png",
    "Electro League 31":    _B + "qVORiRguZ-xMq8L0g7rE1-rZuiA-lKlI8VKuMndRy4w.png",
    "Electro League 32":    _B + "iX8uNhG6jBcQATWFS8a0gtidGy9O1PRYtXZZMTtUK3U.png",
    "Electro League 33":    _B + "VFqkaQimExWtSmIf9PC8WEpj4Vd58oLjPWyZqfVb5VE.png",
    "Legend League III":    _B + "BvEu_UE53UzADvTRiU9AdyOrlvb1RqvBmMau_uX6xm0.png",
    "Legend League II":     _B + "2fQPjjBJCXzHdYY8Eul4DQUBB232Bhiw5KPv6TOLMgQ.png",
    "Legend League I":      _B + "s5Y12RDRg7tgznd2RwU9kgLbedC5Not4peiHfOaWfJo.png",
}

def league_icon_url(league_name: str | None) -> str:
    """Return the large CDN icon URL for a league name, or empty string if unknown."""
    return LEAGUE_ICONS.get(league_name or "", "")
_LEAGUE_NAME_TO_RANK = {name: (lid - 105000000) for lid, name in _LEAGUE_MAP.items()}


def get_name_to_id(league_id: int) -> str:
    return _LEAGUE_MAP.get(league_id, "Unknown League")


def league_rank(name: str) -> int:
    """Returns 0 (Unranked) → 36 (Legend League I). Unknown names return 0."""
    return _LEAGUE_NAME_TO_RANK.get(name, 0)


_SKIP_LEAGUES = SKIP_LEAGUES

def avg_league_name(members) -> str | None:
    """Average ranked league across members who have a league, excluding unranked."""
    if not members:
        return None
    ranks = [league_rank(m.ranked_league) for m in members if m.ranked_league not in _SKIP_LEAGUES]
    if not ranks:
        return None
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


def trophies_at_rank(members_sorted_by_rank, rank):
    """1-indexed rank lookup into a league-group members list (list order = rank order)."""
    if not rank or rank < 1 or rank > len(members_sorted_by_rank):
        return None
    return members_sorted_by_rank[rank - 1].get('leagueTrophies')


# Max hero level achievable at each TH level (home village heroes only)
HERO_TH_MAX = {
    'Barbarian King': {7: 10, 8: 20, 9: 30, 10: 40, 11: 50, 12: 65, 13: 75, 14: 85, 15: 90, 16: 95, 17: 100, 18: 110},
    'Archer Queen': { 8: 10, 9: 30, 10: 40, 11: 50, 12: 65, 13: 75, 14: 85, 15: 90, 16: 95, 17: 100, 18: 110},
    'Minion Prince':  {9: 10, 10: 20, 11:30, 12:40, 13:50, 14:60,15:70,16:80,17:90,18:95},
    'Grand Warden':   {11: 20, 12: 40, 13: 50, 14: 60, 15: 65, 16: 70, 17: 75, 18: 85},
    'Royal Champion': {13: 25, 14: 30, 15: 40, 16: 45, 17: 50, 18: 55},
    'Dragon Duke': { 15: 10, 16: 15, 17: 20, 18: 25},
}


def hero_th_max(hero_name, th_level):
    mapping = HERO_TH_MAX.get(hero_name)
    if not mapping:
        return None
    for th in sorted(mapping.keys(), reverse=True):
        if th_level >= th:
            return mapping[th]
    return None


def compute_hero_pct(heroes_raw, th_level):
    """% of TH-appropriate max hero levels for a home-village heroes list."""
    hero_total = sum(h.get('level', 0) for h in heroes_raw)
    hero_max_sum = sum(hero_th_max(h.get('name', ''), th_level) or h.get('maxLevel', 1) for h in heroes_raw)
    return round(hero_total / hero_max_sum * 100) if hero_max_sum else 0


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


def _max_th_multiplier(player_th):
    if player_th >= 18: return 1.00
    if player_th == 17: return 1.05
    return 1.15


def _ranked_score_from_adj(adj_scores, max_attacks, league_tier, player_th):
    lm = _league_mult(league_tier, player_th)
    if not max_attacks:
        return 0, 0.0, lm
    th_adj = sum(adj_scores) / max_attacks
    ceiling = 3 * _max_th_multiplier(player_th)
    return min(round(th_adj * lm * 100 / ceiling), 100), th_adj, lm


def _calc_ranked_score(battle_logs, player_th, max_attacks, league_tier):
    adj = []
    for l in battle_logs:
        if _is_attack(l):
            try: opp_th = int(l.opponent_th)
            except: opp_th = player_th
            adj.append((l.stars or 0) * _calc_th_multiplier(opp_th - player_th, player_th))
    return _ranked_score_from_adj(adj, max_attacks, league_tier, player_th)


def _ranked_verdict(score_100, att_count, max_attacks):
    missing = max(0, max_attacks - att_count)
    missing_text = f" ({missing} missing)" if missing else ""
    if att_count == 0:
        return 'badge-useless', 'No Attacks', score_100
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
        key = (l.district_name, l.defender_tag)
        district_hits.setdefault(key, []).append(l)
    cleanup_ids = set()
    solo_wipe_count = 0
    for hits in district_hits.values():
        district_done = any((l.percentage_total or 0) == 100 for l in hits)
        player_total  = sum(l.percentage or 0 for l in hits)
        if len(hits) == 1 and district_done and (hits[0].percentage or 0) < CLEANUP_THRESHOLD:
            cleanup_ids.add(hits[0].id)
        if district_done and player_total == 100:
            solo_wipe_count += 1
    return cleanup_ids, solo_wipe_count


def _compute_cleanup_ids(logs):
    cleanup_ids, _ = _district_stats(logs)
    return cleanup_ids


def _raid_level_mult(level):
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 5
    return 1.0 + (level - 4) * (0.175 if level >= 5 else 0.05)


def raid_score_verdict(adj_per_attack, solo_wipes, att_count, missing_text=''):
    adj = adj_per_attack * (1.18 ** solo_wipes)
    score_100 = min(round(adj * 100 / 90.0), 100)
    if att_count == 0:
        return score_100, round(adj, 2), 'badge-inactive', 'Inactive'
    if score_100 >= 87: return score_100, round(adj, 2), 'badge-godlike',  'Godlike'  + missing_text
    if score_100 >= 75: return score_100, round(adj, 2), 'badge-dominant', 'Dominant' + missing_text
    if score_100 >= 62: return score_100, round(adj, 2), 'badge-wow',      'Very Good'+ missing_text
    if score_100 >= 50: return score_100, round(adj, 2), 'badge-good',     'Good'     + missing_text
    if score_100 >= 40: return score_100, round(adj, 2), 'badge-warning',  'Bad'      + missing_text
    if score_100 >= 35: return score_100, round(adj, 2), 'badge-suck',     'Disaster' + missing_text
    return score_100, round(adj, 2), 'badge-useless', 'Useless' + missing_text


_STAR_KEYS = ('zero_stars', 'one_stars', 'two_stars', 'three_stars')

def inc_star_bucket(d, stars, suffix=''):
    """Increment the zero/one/two/three_stars counter in dict d for the given star count."""
    d[_STAR_KEYS[max(0, min(3, stars))] + suffix] += 1


def compute_cwl_win_status(war, our_tag):
    """Return 'safe_win', 'cant_win', 'undecided', or None if war is not inWar."""
    if war.state != 'inWar':
        return None
    our_side = war.clan_tag == our_tag
    our_s    = (war.clan_stars  if our_side else war.opp_stars)  or 0
    opp_s    = (war.opp_stars   if our_side else war.clan_stars) or 0
    our_done = (war.clan_attacks if our_side else war.opp_attacks) or 0
    opp_done = (war.opp_attacks  if our_side else war.clan_attacks) or 0
    our_pct  = float((war.clan_destruction_pct if our_side else war.opp_destruction_pct) or 0)
    opp_pct  = float((war.opp_destruction_pct  if our_side else war.clan_destruction_pct) or 0)
    size     = war.team_size or 15
    our_max  = our_s + max(0, size - our_done) * 3
    opp_max  = opp_s + max(0, size - opp_done) * 3
    if our_s > opp_max or (our_s == opp_max and our_pct > opp_pct):
        return 'safe_win'
    if opp_s > our_max or (opp_s == our_max and opp_pct > our_pct):
        return 'cant_win'
    return 'undecided'


def compute_war_win_status(war, our_tag):
    """Same logic as compute_cwl_win_status, for a regular ClanWar (different field names)."""
    if war.state != 'inWar':
        return None
    our_side = war.clan_tag == our_tag
    our_s    = (war.clan_stars  if our_side else war.opponent_stars)  or 0
    opp_s    = (war.opponent_stars if our_side else war.clan_stars) or 0
    our_done = (war.clan_attacks if our_side else war.opponent_attacks) or 0
    opp_done = (war.opponent_attacks if our_side else war.clan_attacks) or 0
    our_pct  = float((war.clan_destruction_pct if our_side else war.opponent_destruction_pct) or 0)
    opp_pct  = float((war.opponent_destruction_pct if our_side else war.clan_destruction_pct) or 0)
    size     = war.team_size or 15
    our_max  = our_s + max(0, size - our_done) * 3
    opp_max  = opp_s + max(0, size - opp_done) * 3
    if our_s > opp_max or (our_s == opp_max and our_pct > opp_pct):
        return 'safe_win'
    if opp_s > our_max or (opp_s == our_max and opp_pct > our_pct):
        return 'cant_win'
    return 'undecided'


def _raid_verdict(logs):
    if not logs:
        return 'badge-inactive', 'Skipped', 0
    cleanup_ids, solo_wipe_count = _district_stats(logs)
    non_cleanup_count = sum(1 for l in logs if l.id not in cleanup_ids)
    effective_max = max(1, non_cleanup_count)
    total_adj = 0.0
    for l in logs:
        if l.id in cleanup_ids:
            continue
        total_adj += (l.percentage or 0) * _raid_level_mult(l.district_level or 5)
    adj_per_attack = total_adj / effective_max
    score_100, _, badge_class, label = raid_score_verdict(adj_per_attack, solo_wipe_count, len(logs))
    return badge_class, label, score_100
