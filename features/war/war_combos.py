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


def get_cwl_verdict(stars, attacker_th, defender_th, destruction_pct=0, defender_is_rushed=False, defender_is_troll=False):
    """
    Evaluate CWL performance based on expected vs actual performance.
    
    Expectation logic:
    - 3 stars always expected against same TH or lower
    - 2 stars always expected against anyone
    - Against +1 TH: 3 stars is really good (unless defender is rushed/trolled, then treat as same TH)
    - Against +2+ TH: 3 stars is amazing (unless defender is rushed/trolled, then treat as +1 TH)
    
    Returns (score_0_to_100, verdict_label, badge_class)
    """
    th_diff = defender_th - attacker_th  # positive = attacking up
    is_weak_target = defender_is_rushed or defender_is_troll
    
    # Adjust th_diff if target is weak (rushed/trolled)
    if is_weak_target:
        th_diff = max(th_diff - 1, 0)  # reduce difficulty by 1
    
    # If no attack, score is 0
    if stars == 0:
        return 0, 'No Attack', 'badge-suck'
    
    # Calculate expected stars based on adjusted TH difference
    if th_diff <= 0:  # same or lower TH
        expected_stars = 3.0  # 3 stars expected
    elif th_diff == 1:  # up 1 TH
        expected_stars = 2.0  # 2 stars expected, 3 is really good
    else:  # th_diff >= 2, up 2+ TH
        expected_stars = 1.0  # 2 stars is bonus, 3 is amazing
    
    # Calculate performance delta
    delta = stars - expected_stars

    # 1 star is never acceptable in CWL, even against a +2+ target.
    if stars == 1:
        if expected_stars == 3.0:
            score, label = 10, 'Poor'
            badge = 'badge-warning'
        else:
            score, label = 25, 'Below Expected'
            badge = 'badge-warning'
        return score, label, badge
    
    # Map delta to score and label
    if delta >= 2.0:
        score, label = 100, 'Godlike'
        badge = 'badge-godlike'
    elif delta >= 1.0:
        score, label = 85, 'Dominant'
        badge = 'badge-dominant'
    elif delta >= 0.5:
        score, label = 75, 'Excellent'
        badge = 'badge-wow'
    elif delta >= 0.0:
        score, label = 55, 'Solid'
        badge = 'badge-good'
    elif delta >= -0.5:
        score, label = 40, 'Good'
        badge = 'badge-good'
    elif delta >= -1.0:
        score, label = 25, 'Below Expected'
        badge = 'badge-warning'
    else:
        score, label = 10, 'Poor'
        badge = 'badge-warning'
    
    return score, label, badge
