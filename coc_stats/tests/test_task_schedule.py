# -*- coding: utf-8 -*-
"""The interval registry and the rules that pick between intervals.

run_scheduler.py, the three dynamic tasks and features/admin/monitor_stats.py
all read from here. Duplicating the numbers is what this module exists to stop.

The *_interval functions are total on purpose. raid_weekend shipped a bug where
state == 'ended' matched neither reschedule branch and the job silently kept its
3-minute war interval for two days; the exhaustiveness tests below are what
catch that class of defect.
"""

import pytest

from tasks.schedule import (
    TASK_SCHEDULE,
    active_minutes,
    cwl_interval,
    idle_minutes,
    is_dynamic,
    raid_interval,
    war_interval,
)


def test_every_task_declares_an_active_interval():
    assert all(v['active'] for v in TASK_SCHEDULE.values())


def test_the_three_dynamic_tasks_declare_an_idle_interval():
    dynamic = {k for k, v in TASK_SCHEDULE.items() if v['idle'] is not None}
    assert dynamic == {
        'task_update_clan_war',
        'task_update_cwl',
        'task_update_raid_weekend',
    }


def test_fixed_tasks_have_no_idle_mode():
    """A task with idle=None can never resolve to the 'Ruht' state."""
    for key in ('task_update_battle_logs', 'task_update_ranked_weeks',
                'task_update_clan_members'):
        assert idle_minutes(key) is None
        assert is_dynamic(key) is False


def test_idle_is_always_slower_than_active():
    for key, v in TASK_SCHEDULE.items():
        if v['idle'] is not None:
            assert v['idle'] > v['active'], key


def test_lookups_reject_unknown_tasks():
    with pytest.raises(KeyError):
        active_minutes('task_update_nonexistent')


# ── the decisions must be total ──────────────────────────────────────────────

@pytest.mark.parametrize('state', [
    'ongoing', 'ended', 'notStarted', 'unknown', '', None,
])
def test_every_raid_state_maps_to_a_real_interval(state):
    """Regression test for the two-day 3-minute poll: 'ended' matched no branch,
    so the job kept whatever interval it happened to hold."""
    assert raid_interval(state) in (3, 60)


def test_only_an_ongoing_raid_weekend_polls_fast():
    assert raid_interval('ongoing') == 3
    assert raid_interval('ended') == 60
    assert raid_interval('notStarted') == 60


@pytest.mark.parametrize('state', [
    'inWar', 'preparation', 'warEnded', 'notInWar', 'unknown', '', None,
])
def test_every_war_state_maps_to_a_real_interval(state):
    assert war_interval(state) in (3, 60)


def test_only_a_live_war_polls_fast():
    assert war_interval('inWar') == 3
    assert war_interval('preparation') == 3
    assert war_interval('warEnded') == 60
    assert war_interval('notInWar') == 60


@pytest.mark.parametrize('state,season', [
    ('inWar', '2026-08'), ('preparation', '2026-08'), ('notInWar', '2026-08'),
    ('inWar', ''), ('inWar', None), (None, None), ('', ''),
])
def test_every_cwl_input_maps_to_a_real_interval(state, season):
    assert cwl_interval(state, season) in (3, 60)


def test_cwl_polls_fast_only_with_a_live_season():
    assert cwl_interval('inWar', '2026-08') == 3
    assert cwl_interval('notInWar', '2026-08') == 60
    assert cwl_interval('inWar', '') == 60
