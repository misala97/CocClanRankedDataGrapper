import math

# ── Per-attack label constants ──────────────────────────────────────────────

CLEAR           = 'clear'
FAILED_CLEAR    = 'failed_clear'
HIGH_CLEAR      = 'high_clear'
FARM            = 'farm'
FAILED_FARM     = 'failed_farm'
LOW_CLEAR       = 'low_clear'
LOW_CLEAR_FAIL  = 'low_clear_fail'
CLEAN_UP        = 'clean_up'
FAILED_CLEAN_UP = 'failed_clean_up'
WASTED          = 'wasted'
NO_ATTACK       = 'no_attack'


def classify_attack(stars, attacker_th, dfn_th, already_3starred, partially_attacked):
    """Return the label string for a single war attack."""
    th_diff = dfn_th - attacker_th  # positive = attacking up, negative = attacking down

    if already_3starred:
        if th_diff > 1 or attacker_th >= 16:
            return FAILED_FARM if stars == 0 else FARM
        return WASTED

    if abs(th_diff) <= 2:
        return CLEAR if stars == 3 else FAILED_CLEAR

    if th_diff > 1:  # attacking significantly up
        if stars == 3:
            return HIGH_CLEAR
        return FAILED_FARM if stars == 0 else FARM

    # th_diff < -2: attacking significantly down
    if partially_attacked:
        return CLEAN_UP if stars == 3 else FAILED_CLEAN_UP
    return LOW_CLEAR if stars == 3 else LOW_CLEAR_FAIL


# ── Combination verdicts ─────────────────────────────────────────────────────
# Key:   tuple(sorted([label_a, label_b]))  — order does not matter
# Value: (score_0_to_100, 'Verdict Label')
#
# Add entries here whenever you see a new 'Undefined' combination in a war.
# Example entries:
   
#   (CLEAR, FAILED_CLEAR):             (75,  'Solid'),
#   (CLEAR, NO_ATTACK):                (40,  'Half Job'),
#   (NO_ATTACK, NO_ATTACK):            (0,   'No Show'),

WAR_COMBOS = {
    (CLEAR, CLEAR):                    (100, 'Flawless'),
    
    (LOW_CLEAR, CLEAN_UP):             (90,  'War Crimes'),
    (CLEAR, LOW_CLEAR):                (90, 'Scaredy Cat'),
    
    (LOW_CLEAR, FARM):                 (75,  'Lazy Farmer'),
    
    (CLEAR, FAILED_CLEAR):              (50,  'Fumble'),
    (FARM, FARM):                      (50,  'Farmer'),
    
    
    (FAILED_FARM, FARM):                (25,  'Inconsitend Farmer'),
    (WASTED, FARM):                     (25,  'Inconsitend Farmer'),
    
    (FAILED_CLEAR, FAILED_CLEAR):       (15, 'Failure'),
    (WASTED, WASTED):                  (15, 'Wasted'),
    (NO_ATTACK, NO_ATTACK):            (0,   'No Show'),
}

# Normalize all keys so write order never matters
WAR_COMBOS = {tuple(sorted(k)): v for k, v in WAR_COMBOS.items()}

_DEFAULT_SCORE = 50
_DEFAULT_LABEL = 'First Time Combination'


def get_war_verdict(label_a, label_b):
    """Look up the combined verdict for two attack labels. Returns (score, label, badge)."""
    key = tuple(sorted([label_a, label_b]))
    score, label = WAR_COMBOS.get(key, (_DEFAULT_SCORE, _DEFAULT_LABEL))

    if label == _DEFAULT_LABEL:
        badge = 'badge-undefined'
    elif score >= 80:
        badge = 'badge-godlike'
    elif score >= 65:
        badge = 'badge-dominant'
    elif score >= 50:
        badge = 'badge-wow'
    elif score >= 30:
        badge = 'badge-good'
    elif score >= 10:
        badge = 'badge-warning'
    else:
        badge = 'badge-suck'

    return score, label, badge


def get_attack_context(attack, attacks_on_defender):
    """Return (already_3star, partially_attacked) for an attack given prior attacks on the same defender."""
    prior = [x for x in attacks_on_defender.get(attack.defender_tag, [])
             if (x.attack_order or 0) < (attack.attack_order or 0)]
    already_3star = any(x.stars >= 3 for x in prior)
    partially_attacked = len(prior) > 0 and not already_3star
    return already_3star, partially_attacked


def get_cwl_verdict(stars, avg_stars=None):
    """
    Score a CWL attack vs the global average for this TH matchup.
    score = base_for_stars * sqrt(stars / avg_stars), capped at 100.
    Baselines: 3★=90, 2★=60, 1★=25, 0★=0.
    Call only when an attack exists; 'No Attack' is handled by the caller.
    Returns (score_0_to_100, verdict_label, badge_class).
    """
    if stars == 0:
        return 0, 'Disaster', 'badge-useless'

    BASE = {3: 90, 2: 60, 1: 25}
    base = BASE.get(stars, 0)

    if avg_stars and avg_stars > 0:
        score = min(100, round(base * math.sqrt(stars / avg_stars)))
    else:
        score = base  # no matchup data: use raw baseline

    if score >= 88: return score, 'Godlike',  'badge-godlike'
    if score >= 70: return score, 'Dominant', 'badge-dominant'
    if score >= 60: return score, 'Very Good', 'badge-wow'
    if score >= 50: return score, 'Good',      'badge-good'
    if score >= 32: return score, 'Okay',      'badge-warning'
    if score >= 18: return score, 'Poor',      'badge-suck'
    return score, 'Disaster', 'badge-useless'
