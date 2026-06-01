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
    
    (CLEAR, FAILED_CLEAR):              (50,  'Fumble'),
    
    (LOW_CLEAR, FARM):                 (75,  'Lazy Farmer'),
    (FARM, FARM):                      (50,  'Farmer'),
    (FAILED_FARM, FARM):               (25,  'Inconsitend Farmer'),
    (WASTED, FARM):                    (25,  'Inconsitend Farmer'),
    (WASTED, WASTED):                  (0, 'Wasted'),
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
