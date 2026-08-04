# -*- coding: utf-8 -*-
"""Unit tests for features.admin.monitor_stats — the pure Monitor aggregation.

Everything under test takes UptimeTracker-shaped rows and returns plain dicts,
so these fixtures are SimpleNamespace objects and need no database, no app
context and no environment variables.

The correlation tests carry the weight. The Monitor redesign exists because a
single upstream outage was being reported as three unrelated per-task error
counts; if `correlate_incidents` merges what it shouldn't, or fails to merge
what it should, the page is back to lying in a new layout.
"""

import datetime as dt
from types import SimpleNamespace as NS

import pytest

from features.admin.monitor_stats import (
    CADENCE_SAMPLE,
    CLUSTER_GAP_MIN,
    LANE_POINTS,
    TASKS,
    build_monitor_page,
    cause_label,
    correlate_incidents,
    downsample,
    find_gaps,
    group_errors,
    infer_cadence,
    normalize_runs,
    rollup_causes,
    task_stats,
)

T0 = dt.datetime(2026, 7, 31, 12, 0, 0)

MAINT = ('HTTP Error: 503 - {"reason":"inMaintenance","message":"API is '
         'currently in maintenance, please come back later"}')
UNKNOWN = 'HTTP Error: 500 - {"reason":"unknownException"}'
SEASON = "'Key: [season] could not be found'"


def row(fn, minutes, status='success', duration=1.0, error='', summary=''):
    """One UptimeTracker-shaped row, `minutes` after T0."""
    return NS(function=fn, time=T0 + dt.timedelta(minutes=minutes),
              duration=duration, status=status,
              error_message=error, summary=summary)


def cadence_rows(fn, count, every, start=0, status='success'):
    return [row(fn, start + i * every, status=status) for i in range(count)]


def runs_of(rows, fn):
    return normalize_runs(rows)[fn]


# ── cause_label ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('message, expected', [
    (MAINT,   'API in Wartung (503)'),
    (UNKNOWN, 'API-Ausnahme (500)'),
    (SEASON,  'Saison-Key fehlt'),
    ('HTTP Error: 429 - rate limited', 'Ratenlimit erreicht (429)'),
    ('Connection timed out after 10s', 'Zeitüberschreitung'),
    ('',      'Unbekannter Fehler'),
])
def test_cause_label_collapses_known_shapes(message, expected):
    assert cause_label(message) == expected


def test_cause_label_truncates_unknown_messages():
    out = cause_label('x' * 200)
    assert len(out) <= 49 and out.endswith('…')


def test_cause_label_keeps_distinct_causes_distinct():
    """The rollup counts by label — collapsing 503 and 500 would merge two
    genuinely different failures into one row."""
    assert cause_label(MAINT) != cause_label(UNKNOWN)


# ── infer_cadence ─────────────────────────────────────────────────────────────

def test_infer_cadence_is_the_median_interval():
    runs = runs_of(cadence_rows('t', 10, 5), 't')
    assert infer_cadence(runs) == 5.0


def test_infer_cadence_ignores_skipped_runs():
    rows = cadence_rows('t', 6, 5) + [row('t', 7, status='skipped')]
    assert infer_cadence(runs_of(rows, 't')) == 5.0


def test_infer_cadence_follows_the_current_schedule_not_the_history():
    """clan_war alternates between a 3- and a 60-minute schedule. Averaging
    across both describes neither, so only the recent window counts."""
    old = cadence_rows('t', 30, 60)
    recent_start = 30 * 60
    new = cadence_rows('t', CADENCE_SAMPLE, 3, start=recent_start)
    assert infer_cadence(runs_of(old + new, 't')) == 3.0


def test_infer_cadence_is_none_without_two_runs():
    assert infer_cadence(runs_of([row('t', 0)], 't')) is None
    assert infer_cadence([]) is None


# ── find_gaps ─────────────────────────────────────────────────────────────────

def test_find_gaps_flags_intervals_past_the_threshold():
    rows = cadence_rows('t', 5, 10) + [row('t', 40 + 60)]
    gaps = find_gaps(runs_of(rows, 't'), cadence=10.0)
    assert len(gaps) == 1
    assert gaps[0]['minutes'] == 60.0


def test_find_gaps_ignores_normal_jitter():
    rows = cadence_rows('t', 5, 10) + [row('t', 40 + 24)]   # 24 < 10 × 2.5
    assert find_gaps(runs_of(rows, 't'), cadence=10.0) == []


def test_find_gaps_needs_a_cadence():
    rows = cadence_rows('t', 3, 10)
    assert find_gaps(runs_of(rows, 't'), cadence=None) == []


# ── group_errors ──────────────────────────────────────────────────────────────

def test_group_errors_counts_each_message_once():
    rows = [row('t', i, status='error', error=MAINT) for i in range(9)] \
         + [row('t', 20 + i, status='error', error=UNKNOWN) for i in range(3)] \
         + cadence_rows('t', 4, 5, start=100)
    groups = group_errors(runs_of(rows, 't'))
    assert [(g['label'], g['count']) for g in groups] == [
        ('API in Wartung (503)', 9),
        ('API-Ausnahme (500)', 3),
    ]


def test_group_errors_records_the_window_each_cause_spanned():
    rows = [row('t', 0, status='error', error=MAINT),
            row('t', 35, status='error', error=MAINT)]
    g = group_errors(runs_of(rows, 't'))[0]
    assert g['first'] == T0
    assert g['last'] == T0 + dt.timedelta(minutes=35)


def test_group_errors_is_empty_for_a_clean_task():
    assert group_errors(runs_of(cadence_rows('t', 5, 5), 't')) == []


# ── correlate_incidents ───────────────────────────────────────────────────────

def _tasks_from(rows, now=None):
    by_task = normalize_runs(rows)
    now = now or (T0 + dt.timedelta(hours=2))
    tasks = [task_stats(k, v, now) for k, v in by_task.items()]
    return by_task, tasks


def test_one_outage_across_three_tasks_is_one_incident():
    """The whole point of the redesign: 2026-07-31 produced 31 failures across
    raid_weekend, clan_war and clan_members inside 35 minutes. That is one API
    outage, not three task problems."""
    rows = []
    for i in range(0, 35, 3):
        rows.append(row('task_update_raid_weekend', i, status='error', error=MAINT))
    for i in range(1, 35, 4):
        rows.append(row('task_update_clan_war', i, status='error', error=MAINT))
    for i in range(2, 35, 7):
        rows.append(row('task_update_clan_members', i, status='error', error=UNKNOWN))

    by_task, tasks = _tasks_from(rows)
    incidents = [e for e in correlate_incidents(by_task, tasks) if e['kind'] != 'silence']

    assert len(incidents) == 1
    e = incidents[0]
    assert e['kind'] == 'upstream'
    assert set(e['tasks']) == {'task_update_raid_weekend',
                               'task_update_clan_war',
                               'task_update_clan_members'}
    assert e['failures'] == len(rows)
    assert e['minutes'] == 33


def test_unrelated_single_task_errors_stay_separate():
    """The negative case. If clustering ignored the time distance, two failures
    days apart would be reported as one incident touching two tasks — inventing
    a correlation that isn't there, which is the same lie in the other
    direction."""
    rows = [row('task_update_cwl', 0, status='error', error=SEASON),
            row('task_update_clan_war', 60 * 24 * 3, status='error', error=UNKNOWN)]

    by_task, tasks = _tasks_from(rows, now=T0 + dt.timedelta(days=4))
    incidents = [e for e in correlate_incidents(by_task, tasks) if e['kind'] != 'silence']

    assert len(incidents) == 2
    assert all(e['kind'] == 'task' for e in incidents)
    assert all(len(e['tasks']) == 1 for e in incidents)


def test_failures_just_inside_the_window_merge_and_just_outside_do_not():
    inside = [row('a', 0, status='error', error=MAINT),
              row('b', CLUSTER_GAP_MIN, status='error', error=MAINT)]
    outside = [row('a', 0, status='error', error=MAINT),
               row('b', CLUSTER_GAP_MIN + 1, status='error', error=MAINT)]

    by_a, ta = _tasks_from(inside, now=T0 + dt.timedelta(hours=5))
    by_b, tb = _tasks_from(outside, now=T0 + dt.timedelta(hours=5))

    merged = [e for e in correlate_incidents(by_a, ta) if e['kind'] != 'silence']
    split = [e for e in correlate_incidents(by_b, tb) if e['kind'] != 'silence']

    assert len(merged) == 1 and merged[0]['kind'] == 'upstream'
    assert len(split) == 2 and all(e['kind'] == 'task' for e in split)


def test_a_long_burst_chains_into_one_incident():
    """Consecutive failures each within the window chain together even when the
    burst as a whole is far longer than CLUSTER_GAP_MIN."""
    rows = [row('a', i * 5, status='error', error=MAINT) for i in range(30)]
    by_task, tasks = _tasks_from(rows, now=T0 + dt.timedelta(hours=6))
    incidents = [e for e in correlate_incidents(by_task, tasks) if e['kind'] != 'silence']
    assert len(incidents) == 1
    assert incidents[0]['minutes'] == 145


def test_silence_becomes_its_own_incident():
    rows = cadence_rows('task_update_clan_war', 5, 3) + \
           [row('task_update_clan_war', 12 + 2122)]
    by_task, tasks = _tasks_from(rows, now=T0 + dt.timedelta(minutes=2140))
    silences = [e for e in correlate_incidents(by_task, tasks) if e['kind'] == 'silence']
    assert len(silences) == 1
    assert silences[0]['failures'] == 0
    assert silences[0]['minutes'] == 2122


def test_no_failures_no_incidents():
    rows = cadence_rows('task_update_cwl', 12, 5)
    by_task, tasks = _tasks_from(rows, now=T0 + dt.timedelta(minutes=60))
    assert correlate_incidents(by_task, tasks) == []


# ── rollup_causes ─────────────────────────────────────────────────────────────

def test_rollup_counts_one_cause_once_across_every_task_it_hit():
    rows = ([row('task_update_raid_weekend', i, status='error', error=MAINT) for i in range(9)]
          + [row('task_update_clan_war', i, status='error', error=MAINT) for i in range(9)]
          + [row('task_update_clan_members', i, status='error', error=MAINT) for i in range(5)])
    by_task, tasks = _tasks_from(rows)
    rows_out = rollup_causes(correlate_incidents(by_task, tasks))

    assert len(rows_out) == 1
    assert rows_out[0]['label'] == 'API in Wartung (503)'
    assert rows_out[0]['count'] == 23
    assert len(rows_out[0]['tasks']) == 3


def test_rollup_orders_by_weight():
    rows = ([row('a', i, status='error', error=MAINT) for i in range(9)]
          + [row('a', 10 + i, status='error', error=UNKNOWN) for i in range(3)]
          + [row('b', 12, status='error', error=SEASON)])
    by_task, tasks = _tasks_from(rows)
    out = rollup_causes(correlate_incidents(by_task, tasks))
    assert [r['count'] for r in out] == [9, 3, 1]


# ── task_stats ────────────────────────────────────────────────────────────────

def test_health_reads_up_warn_down_off_the_cadence():
    rows = cadence_rows('t', 10, 10)
    last = 90
    for offset, expected in [(5, 'up'), (20, 'warn'), (40, 'down')]:
        now = T0 + dt.timedelta(minutes=last + offset)
        assert task_stats('t', runs_of(rows, 't'), now)['health'] == expected


def test_a_recent_skip_still_proves_the_task_is_alive():
    """raid_weekend skips on weekdays; treating a skip as absence would report
    a perfectly healthy task as down."""
    rows = cadence_rows('t', 10, 5) + [row('t', 47, status='skipped')]
    stats = task_stats('t', runs_of(rows, 't'), T0 + dt.timedelta(minutes=49))
    assert stats['health'] == 'up'


def test_skipped_runs_are_counted_apart_from_errors():
    rows = (cadence_rows('t', 5, 5)
            + [row('t', 30, status='skipped'), row('t', 35, status='skipped')]
            + [row('t', 40, status='error', error=UNKNOWN)])
    stats = task_stats('t', runs_of(rows, 't'), T0 + dt.timedelta(minutes=42))
    assert stats['skipped'] == 2
    assert stats['errors'] == 1
    assert stats['runs'] == 8


def test_durations_exclude_skipped_runs():
    """A skip records a near-zero duration; letting it into the average would
    make a slow task look fast in exactly the periods it wasn't running."""
    rows = [row('t', 0, duration=10.0), row('t', 5, duration=20.0),
            row('t', 10, duration=0.0, status='skipped')]
    stats = task_stats('t', runs_of(rows, 't'), T0 + dt.timedelta(minutes=12))
    assert stats['avg_duration'] == 15.0
    assert stats['max_duration'] == 20.0


def test_unparseable_duration_does_not_crash():
    rows = [NS(function='t', time=T0, duration='n/a', status='success',
               error_message='', summary='')]
    assert task_stats('t', runs_of(rows, 't'), T0)['avg_duration'] == 0


def test_task_stats_carries_the_registry_labels():
    rows = cadence_rows('task_update_cwl', 3, 5)
    stats = task_stats('task_update_cwl', runs_of(rows, 'task_update_cwl'), T0)
    assert stats['label'] == 'CWL'
    assert stats['short'] == 'cwl'


# ── downsample ────────────────────────────────────────────────────────────────

def test_downsample_bounds_a_large_series():
    rows = cadence_rows('t', 5000, 1)
    out = downsample(runs_of(rows, 't'))
    assert len(out) <= LANE_POINTS + 1
    assert out[0]['t'] == T0


def test_downsample_leaves_small_series_intact():
    rows = cadence_rows('t', 12, 5)
    assert len(downsample(runs_of(rows, 't'))) == 12


def test_downsample_handles_an_empty_series():
    assert downsample([]) == []


# ── build_monitor_page ────────────────────────────────────────────────────────

def _realistic_week():
    """A week shaped like production: six healthy tasks, one 35-minute upstream
    outage hitting three of them, one unrelated single-task error days later."""
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, 60, 5, start=-60 * 5)
    for i in range(0, 35, 3):
        rows.append(row('task_update_raid_weekend', i, status='error', error=MAINT))
    for i in range(1, 35, 4):
        rows.append(row('task_update_clan_war', i, status='error', error=MAINT))
    for i in range(2, 35, 7):
        rows.append(row('task_update_clan_members', i, status='error', error=UNKNOWN))
    rows.append(row('task_update_cwl', 60 * 24 * 2, status='error', error=SEASON))
    return rows


def test_page_reports_all_six_tasks_in_registry_order():
    page = build_monitor_page(_realistic_week(), T0 + dt.timedelta(days=3))
    assert [t['key'] for t in page['tasks']] == [k for k, _, _ in TASKS]


def test_page_attributes_the_bulk_of_failures_to_the_shared_outage():
    page = build_monitor_page(_realistic_week(), T0 + dt.timedelta(days=3))
    s = page['summary']
    assert page['lead_incident'] is not None
    assert page['lead_incident']['kind'] == 'upstream'
    assert len(page['lead_incident']['tasks']) == 3
    assert s['explained_by_shared'] == s['total_errors'] - 1


def test_page_is_quiet_when_nothing_went_wrong():
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, 40, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=200))
    assert page['incidents'] == []
    assert page['causes'] == []
    assert page['lead_incident'] is None
    assert page['summary']['total_errors'] == 0
    assert page['summary']['healthy'] == len(TASKS)


def test_page_survives_an_empty_window():
    page = build_monitor_page([], T0)
    assert page['tasks'] == []
    assert page['incidents'] == []
    assert page['summary']['total_runs'] == 0


def test_unknown_task_names_still_appear():
    """A task logging under a name the registry doesn't know must not vanish
    from the one page whose job is to notice it."""
    rows = cadence_rows('task_update_battle_logs', 5, 5) + cadence_rows('task_update_future', 5, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=30))
    assert 'task_update_future' in [t['key'] for t in page['tasks']]
