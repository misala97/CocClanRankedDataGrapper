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
    CLUSTER_GAP_MIN,
    LANE_POINTS,
    TASKS,
    build_monitor_page,
    cause_label,
    correlate_incidents,
    downsample,
    find_gaps,
    group_errors,
    idle_windows,
    resolve_interval,
    normalize_runs,
    rollup_causes,
    task_stats,
)

T0 = dt.datetime(2026, 7, 31, 12, 0, 0)

MAINT = ('HTTP Error: 503 - {"reason":"inMaintenance","message":"API is '
         'currently in maintenance, please come back later"}')
UNKNOWN = 'HTTP Error: 500 - {"reason":"unknownException"}'
SEASON = "'Key: [season] could not be found'"


def row(fn, minutes, status='success', duration=1.0, error='', summary='', interval=None):
    """One UptimeTracker-shaped row, `minutes` after T0.

    `interval` is the schedule in force for the NEXT run, as the tasks record it.
    None models a path that returned before it knew its schedule.
    """
    return NS(function=fn, time=T0 + dt.timedelta(minutes=minutes),
              duration=duration, status=status,
              error_message=error, summary=summary,
              interval_minutes=interval)


def cadence_rows(fn, count, every, start=0, status='success', interval=-1):
    """A run of rows `every` minutes apart, recording that same interval."""
    iv = every if interval == -1 else interval
    return [row(fn, start + i * every, status=status, interval=iv) for i in range(count)]


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


# ── resolve_interval ─────────────────────────────────────────────────────────

def test_resolve_interval_reads_the_persisted_value():
    rows = cadence_rows('task_update_clan_war', 4, 60, interval=60)
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 60
    assert assumed is False


def test_null_intervals_carry_the_last_known_schedule_forward():
    """An API failure writes NULL because it returns before the task inspects
    game state. A burst of them must not lose the schedule."""
    rows = [row('task_update_clan_war', 0, 'skipped', summary='notInWar', interval=60)]
    rows += [row('task_update_clan_war', 60 + i, 'error', interval=None) for i in range(3)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 60
    assert assumed is False


def test_all_null_falls_back_to_the_declared_active_interval():
    rows = [row('task_update_clan_war', i, 'error', interval=None) for i in range(3)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 3
    assert assumed is True


def test_an_unknown_task_has_no_interval_to_fall_back_on():
    rows = [row('task_update_future', i, interval=None) for i in range(3)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_future'),
                                        'task_update_future')
    assert minutes is None
    assert assumed is True


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

WEEK_END = 60 * 24 * 3          # fixture runs span T0 → T0+3d
WEEK_NOW = T0 + dt.timedelta(minutes=WEEK_END + 2)


def _realistic_week():
    """A week shaped like production: six tasks still running right up to `now`,
    one 35-minute upstream outage hitting three of them, one unrelated
    single-task error days later."""
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, WEEK_END // 5 + 1, 5)
    for i in range(0, 35, 3):
        rows.append(row('task_update_raid_weekend', i, status='error', error=MAINT))
    for i in range(1, 35, 4):
        rows.append(row('task_update_clan_war', i, status='error', error=MAINT))
    for i in range(2, 35, 7):
        rows.append(row('task_update_clan_members', i, status='error', error=UNKNOWN))
    rows.append(row('task_update_cwl', 60 * 24 * 2, status='error', error=SEASON))
    return sorted(rows, key=lambda r: r.time)


def test_page_reports_all_six_tasks_in_registry_order():
    page = build_monitor_page(_realistic_week(), WEEK_NOW)
    assert [t['key'] for t in page['tasks']] == [k for k, _, _ in TASKS]


def test_page_attributes_the_bulk_of_failures_to_the_shared_outage():
    page = build_monitor_page(_realistic_week(), WEEK_NOW)
    s = page['summary']
    assert page['verdict']['kind'] == 'upstream'
    assert page['lead_incident'] is not None
    assert page['lead_incident']['kind'] == 'upstream'
    assert len(page['lead_incident']['tasks']) == 3
    assert s['explained_by_shared'] == s['total_errors'] - 1


def test_lead_incident_and_its_figure_describe_the_same_event():
    """They used to diverge: the sentence took the most RECENT shared outage
    while the number counted the LARGEST, so with two outages the headline
    described one event and quantified another."""
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, 600, 5)
    # Small outage first, large outage later, so recency and size disagree.
    for i in range(0, 10, 3):
        rows.append(row('task_update_clan_war', 100 + i, status='error', error=MAINT))
        rows.append(row('task_update_cwl', 100 + i, status='error', error=MAINT))
    for i in range(0, 40, 2):
        rows.append(row('task_update_raid_weekend', 2000 + i, status='error', error=UNKNOWN))
        rows.append(row('task_update_clan_members', 2000 + i, status='error', error=UNKNOWN))

    page = build_monitor_page(sorted(rows, key=lambda r: r.time),
                              T0 + dt.timedelta(minutes=3002))
    lead = page['lead_incident']
    shared = [e for e in page['incidents'] if e['kind'] == 'upstream']
    assert len(shared) == 2
    assert lead['failures'] == max(e['failures'] for e in shared)
    # The headline figure covers every shared outage, not just the lead one.
    assert page['summary']['explained_by_shared'] == sum(e['failures'] for e in shared)


def test_page_is_quiet_when_nothing_went_wrong():
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, 40, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=200))
    assert page['incidents'] == []
    assert page['causes'] == []
    assert page['lead_incident'] is None
    assert page['verdict']['kind'] == 'clear'
    assert page['summary']['total_errors'] == 0
    assert page['summary']['healthy'] == len(TASKS)


# ── absence: the defect that let a dead scheduler render a green all-clear ────

def test_a_task_with_no_runs_still_occupies_its_row():
    """The registry is fixed. Dropping a silent task shortened the list and made
    its absence invisible on the one page whose job is to notice it."""
    rows = cadence_rows('task_update_battle_logs', 40, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=200))

    assert len(page['tasks']) == len(TASKS)
    absent = [t for t in page['tasks'] if t['key'] != 'task_update_battle_logs']
    assert all(t['health'] == 'absent' for t in absent)
    assert all(t['runs'] == 0 for t in absent)
    assert page['summary']['absent'] == len(TASKS) - 1


def test_a_window_where_tasks_vanished_does_not_read_as_all_clear():
    """The exact regression: one task logging, five gone, zero errors. The old
    build reported 'alle Tasks liefen fehlerfrei' in green."""
    rows = cadence_rows('task_update_battle_logs', 40, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=200))

    assert page['verdict']['kind'] == 'silence'
    assert page['verdict']['count'] == len(TASKS) - 1
    assert page['summary']['healthy'] < page['summary']['task_count']


def test_silence_outranks_failure_correlation_in_the_verdict():
    """A task that is not running matters more than one that ran and failed."""
    rows = cadence_rows('task_update_clan_war', 40, 5)
    for i in range(0, 20, 3):
        rows.append(row('task_update_clan_war', i, status='error', error=MAINT))
        rows.append(row('task_update_cwl', i, status='error', error=MAINT))
    page = build_monitor_page(sorted(rows, key=lambda r: r.time),
                              T0 + dt.timedelta(minutes=200))

    shared = [e for e in page['incidents'] if e['kind'] == 'upstream']
    assert shared, 'fixture must contain a genuine cross-task outage'
    assert page['verdict']['kind'] == 'silence'


def test_page_survives_an_empty_window():
    page = build_monitor_page([], T0)
    assert len(page['tasks']) == len(TASKS)
    assert all(t['health'] == 'absent' for t in page['tasks'])
    assert page['incidents'] == []
    assert page['summary']['total_runs'] == 0
    assert page['verdict']['kind'] == 'silence'


def test_unknown_task_names_still_appear():
    """A task logging under a name the registry doesn't know must not vanish
    from the one page whose job is to notice it."""
    rows = cadence_rows('task_update_battle_logs', 5, 5) + cadence_rows('task_update_future', 5, 5)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=30))
    assert 'task_update_future' in [t['key'] for t in page['tasks']]


# ── silence measurement ──────────────────────────────────────────────────────

def test_a_task_that_simply_stopped_produces_an_ongoing_gap():
    """Measuring only run-to-run intervals missed the most important silence
    there is: the one that hasn't ended. The lane just went blank."""
    rows = cadence_rows('t', 20, 5)
    runs = runs_of(rows, 't')
    gaps = find_gaps(runs, cadence=5.0, now=T0 + dt.timedelta(minutes=95 + 200))
    assert len(gaps) == 1
    assert gaps[0]['ongoing'] is True
    assert gaps[0]['minutes'] == 200.0


def test_no_trailing_gap_while_the_task_is_still_on_cadence():
    rows = cadence_rows('t', 20, 5)
    gaps = find_gaps(runs_of(rows, 't'), cadence=5.0,
                     now=T0 + dt.timedelta(minutes=95 + 4))
    assert gaps == []


def test_longest_gap_ignores_error_bursts():
    """`longest_gap` is rendered as 'längste Lücke'. Ranging over every incident
    let it report the duration of a failure storm instead."""
    rows = []
    for key, _, _ in TASKS:
        rows += cadence_rows(key, 200, 5)
    for i in range(0, 300, 5):
        rows.append(row('task_update_cwl', i, status='error', error=MAINT))
        rows.append(row('task_update_clan_war', i, status='error', error=MAINT))

    page = build_monitor_page(sorted(rows, key=lambda r: r.time),
                              T0 + dt.timedelta(minutes=997))
    burst = max(e['minutes'] for e in page['incidents'] if e['kind'] != 'silence')
    assert burst >= 295
    silences = [e['minutes'] for e in page['incidents'] if e['kind'] == 'silence']
    assert page['summary']['longest_gap'] == (max(silences) if silences else 0)
    assert page['summary']['longest_gap'] < burst


def test_sparse_data_escalates_to_down_rather_than_delayed():
    """One run leaves no interval, so cadence is unknowable. Without an absolute
    escalation a task last seen eleven days ago reported 'delayed' forever."""
    rows = [row('t', 0)]
    runs = runs_of(rows, 't')
    assert task_stats('t', runs, T0 + dt.timedelta(minutes=30))['health'] == 'up'
    assert task_stats('t', runs, T0 + dt.timedelta(hours=5))['health'] == 'warn'
    assert task_stats('t', runs, T0 + dt.timedelta(days=11))['health'] == 'down'


# ── schedule awareness ───────────────────────────────────────────────────────

def test_an_idle_task_is_not_reported_as_down():
    """The bug this whole change exists to fix: clan_war polling correctly on
    its hourly idle schedule was reported Still, because cadence was inferred
    from war-time runs days earlier."""
    rows = cadence_rows('task_update_clan_war', 5, 60, status='skipped', interval=60)
    now = T0 + dt.timedelta(minutes=4 * 60 + 30)
    s = task_stats('task_update_clan_war', runs_of(rows, 'task_update_clan_war'), now)
    assert s['health'] == 'idle'
    assert s['mode'] == 'idle'
    assert s['cadence'] == 60


def test_an_idle_task_that_stops_polling_still_goes_down():
    """Scaling the threshold to the schedule must not mean never alerting."""
    rows = cadence_rows('task_update_clan_war', 5, 60, status='skipped', interval=60)
    runs = runs_of(rows, 'task_update_clan_war')
    base = T0 + dt.timedelta(minutes=4 * 60)
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=80))['health'] == 'idle'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=100))['health'] == 'warn'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=200))['health'] == 'down'


def test_an_active_task_still_uses_its_fast_threshold():
    rows = cadence_rows('task_update_clan_war', 8, 3, interval=3)
    runs = runs_of(rows, 'task_update_clan_war')
    base = T0 + dt.timedelta(minutes=21)
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=2))['health'] == 'up'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=6))['health'] == 'warn'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=12))['health'] == 'down'


def test_a_fixed_task_can_never_be_idle():
    rows = cadence_rows('task_update_battle_logs', 6, 5, interval=5)
    s = task_stats('task_update_battle_logs',
                   runs_of(rows, 'task_update_battle_logs'),
                   T0 + dt.timedelta(minutes=27))
    assert s['mode'] == 'active'
    assert s['health'] == 'up'


def test_idle_reason_ignores_whatever_the_summary_happens_to_say():
    """The reason follows from which task is dormant, not from a summary string
    that differs per code path within the same task."""
    rows = cadence_rows('task_update_raid_weekend', 3, 60,
                        status='skipped', interval=60)
    for r in rows:
        r.summary = 'not ongoing'
    s = task_stats('task_update_raid_weekend',
                   runs_of(rows, 'task_update_raid_weekend'),
                   T0 + dt.timedelta(minutes=130))
    assert s['idle_reason'] == 'kein Raid aktiv'


def test_an_active_task_has_no_idle_reason():
    rows = cadence_rows('task_update_clan_war', 6, 3, interval=3)
    s = task_stats('task_update_clan_war', runs_of(rows, 'task_update_clan_war'),
                   T0 + dt.timedelta(minutes=16))
    assert s['idle_reason'] is None


def test_hourly_polling_is_not_counted_as_a_gap():
    """find_gaps compared hourly idle polls against a 3-minute cadence."""
    rows = cadence_rows('task_update_clan_war', 6, 60, status='skipped', interval=60)
    s = task_stats('task_update_clan_war', runs_of(rows, 'task_update_clan_war'),
                   T0 + dt.timedelta(minutes=5 * 60 + 10))
    assert s['gaps'] == []


def test_idle_windows_group_contiguous_dormant_stretches():
    """Task 6 shades these behind the lane; a wrong grouping paints the wrong
    span of history as dormant."""
    rows  = cadence_rows('task_update_clan_war', 5, 3, interval=3)
    rows += cadence_rows('task_update_clan_war', 4, 60, start=60,
                         status='skipped', interval=60)
    rows += cadence_rows('task_update_clan_war', 3, 3, start=400, interval=3)
    windows = idle_windows(runs_of(rows, 'task_update_clan_war'), 'task_update_clan_war')
    assert len(windows) == 1
    assert windows[0]['start'] == T0 + dt.timedelta(minutes=60)


def test_a_fixed_task_has_no_idle_windows():
    rows = cadence_rows('task_update_battle_logs', 6, 5, interval=5)
    assert idle_windows(runs_of(rows, 'task_update_battle_logs'),
                        'task_update_battle_logs') == []


def test_a_skipped_run_proves_the_task_is_alive():
    """An idle task only ever writes `skipped` rows. Excluding them made a
    perfectly healthy dormant task look silent for the whole idle stretch —
    which is the same mistake, one layer down, that this change exists to fix."""
    rows = cadence_rows('task_update_clan_war', 6, 60, status='skipped', interval=60)
    gaps = find_gaps(runs_of(rows, 'task_update_clan_war'), cadence=60.0,
                     now=T0 + dt.timedelta(minutes=5 * 60 + 20))
    assert gaps == []


def test_idle_tasks_count_as_healthy_in_the_summary():
    """The verdict said 'alle Tasks im Takt' while the figure beside it read
    4/6 in red, because dormant counted as neither healthy nor stalled."""
    rows = []
    for key in ('task_update_battle_logs', 'task_update_ranked_weeks',
                'task_update_clan_members'):
        rows += cadence_rows(key, 40, 5, interval=5)
    for key in ('task_update_clan_war', 'task_update_cwl', 'task_update_raid_weekend'):
        rows += cadence_rows(key, 4, 60, status='skipped', interval=60)
    page = build_monitor_page(rows, T0 + dt.timedelta(minutes=200))
    assert page['verdict']['kind'] == 'clear'
    assert page['summary']['healthy'] == page['summary']['task_count']


def test_gaps_are_judged_against_the_interval_in_force_at_the_time():
    """A task that switched schedule mid-window was judged entirely against its
    CURRENT interval, so every legitimate hourly poll during a dormant stretch
    read as a gap. Live data showed 122 false gaps on clan_war."""
    rows  = cadence_rows('task_update_clan_war', 5, 60, status='skipped', interval=60)
    rows += cadence_rows('task_update_clan_war', 10, 3, start=300, interval=3)
    runs = runs_of(rows, 'task_update_clan_war')
    # resolve_interval returns 3 — the schedule it is on NOW.
    assert resolve_interval(runs, 'task_update_clan_war')[0] == 3
    gaps = find_gaps(runs, cadence=3, now=T0 + dt.timedelta(minutes=330))
    assert gaps == [], f"hourly polls misread as gaps: {len(gaps)}"


def test_a_real_gap_during_a_dormant_stretch_is_still_caught():
    """Scaling per row must not mean never detecting silence."""
    rows  = cadence_rows('task_update_clan_war', 3, 60, status='skipped', interval=60)
    rows += cadence_rows('task_update_clan_war', 2, 60, start=120 + 400,
                         status='skipped', interval=60)
    gaps = find_gaps(runs_of(rows, 'task_update_clan_war'), cadence=60,
                     now=T0 + dt.timedelta(minutes=600))
    assert len(gaps) == 1
    assert gaps[0]['minutes'] == 400.0


def test_idle_reason_does_not_leak_a_raw_summary():
    """raid_weekend's 'ended' path writes status=success with summary
    'logs_added=0' while on the hourly schedule, so a summary-derived reason
    rendered that string straight into the UI."""
    rows = cadence_rows('task_update_raid_weekend', 4, 60, interval=60)
    for r in rows:
        r.summary = 'logs_added=0'
    s = task_stats('task_update_raid_weekend',
                   runs_of(rows, 'task_update_raid_weekend'),
                   T0 + dt.timedelta(minutes=200))
    assert s['health'] == 'idle'
    assert s['idle_reason'] == 'kein Raid aktiv'


def test_each_dynamic_task_has_its_own_idle_reason():
    for key, expected in [('task_update_clan_war', 'kein Krieg aktiv'),
                          ('task_update_cwl', 'keine CWL aktiv'),
                          ('task_update_raid_weekend', 'kein Raid aktiv')]:
        rows = cadence_rows(key, 4, 60, status='skipped', interval=60)
        s = task_stats(key, runs_of(rows, key), T0 + dt.timedelta(minutes=200))
        assert s['idle_reason'] == expected, key
