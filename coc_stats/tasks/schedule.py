"""The only place background-task intervals are written, and the rules that
choose between them.

Three of the six tasks retune themselves at runtime — clan_war, cwl and
raid_weekend drop from a 3-minute cadence to hourly when there is nothing to
poll for. That interval used to be written in run_scheduler.py and again inside
each task's reschedule call, with the Monitor reverse-engineering it from
timestamps a third time. Three copies of one number is how they drift.

The *_interval functions are total: every possible state maps to an interval.
raid_weekend previously decided this with an if/elif covering 'ongoing' and
"neither ongoing nor ended", leaving state == 'ended' to match neither branch
and the job to keep whatever interval it held. It polled every 3 minutes for
two days — 480 runs in 24 hours against ~24 expected.
"""

TASK_SCHEDULE = {
    'task_update_battle_logs':  {'active': 5,  'idle': None},
    'task_update_ranked_weeks': {'active': 10, 'idle': None},
    'task_update_clan_members': {'active': 5,  'idle': None},
    'task_update_clan_war':     {'active': 3,  'idle': 60},
    'task_update_cwl':          {'active': 3,  'idle': 60},
    'task_update_raid_weekend': {'active': 3,  'idle': 60},
}


def active_minutes(key):
    """Interval while the task has work to poll for."""
    return TASK_SCHEDULE[key]['active']


def idle_minutes(key):
    """Interval while the task is dormant, or None if it has no dormant mode."""
    return TASK_SCHEDULE[key]['idle']


def is_dynamic(key):
    """True when the task switches interval at runtime."""
    return TASK_SCHEDULE.get(key, {}).get('idle') is not None


def _pick(key, active):
    return active_minutes(key) if active else idle_minutes(key)


def war_interval(state):
    """Clan war: only a live war is worth polling every few minutes.

    'warEnded' is still polled so the final result lands, but hourly is plenty.
    """
    return _pick('task_update_clan_war',
                 state not in ('notInWar', 'warEnded', None, ''))


def cwl_interval(state, season):
    """CWL: needs both a season and a state that is not 'notInWar'."""
    return _pick('task_update_cwl',
                 bool(season) and state not in ('notInWar', None, ''))


def raid_interval(state):
    """Raid weekend: only an ongoing weekend polls fast.

    'ended' is polled hourly so a late-arriving attack log still gets picked up.
    """
    return _pick('task_update_raid_weekend', state == 'ongoing')
