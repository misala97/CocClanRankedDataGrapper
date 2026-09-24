"""Calendar keys are the lifter's dates, not UTC's (walkthrough 2026-09-23,
G-129; G-032 and G-052 are the same bug on the client).

Timestamps are stored naive-UTC. Between midnight and 02:00 in Berlin (01:00
in winter) the UTC date is still yesterday, so any day, month or year taken
straight from a stored timestamp put a late-night workout on the wrong one.
The career strip, the export range and the monthly helpers live in their own
test files; these two had no home.
"""
import datetime as dt

from features.gym.routes import _chart_geometry
from features.gym.routes.exercise_detail import SAME_DAY_SPREAD
from features.gym.routes.reports import _year_bands


def _point(started_at, e1rm):
    return {'started_at': started_at, 'e1rm': e1rm, 'is_deload': False}


def test_the_chart_spreads_two_workouts_of_one_local_day():
    """00:30 and 08:00 on 23 September in Berlin are one day there -- and two
    in UTC, where the first is still the 22nd. Two workouts on one day are
    spread apart so neither hides the other; split across UTC dates, these
    two stacked 4 px apart."""
    series = [{'position': 1, 'points': [
        _point(dt.datetime(2026, 9, 1, 10, 0), 100.0),
        _point(dt.datetime(2026, 9, 22, 22, 30), 99.0),
        _point(dt.datetime(2026, 9, 23, 6, 0), 98.0),
    ]}]
    geometry = _chart_geometry(series)
    xs = [point['x'] for point in geometry['series'][0]['points']]
    assert xs[2] - xs[1] >= SAME_DAY_SPREAD - 0.01


def test_the_chart_leaves_two_local_days_apart():
    """The other direction: 23:45 on the 22nd and 00:15 on the 23rd in Berlin
    are the same UTC date, and were spread as if one day."""
    series = [{'position': 1, 'points': [
        _point(dt.datetime(2026, 9, 1, 10, 0), 100.0),
        _point(dt.datetime(2026, 9, 22, 21, 45), 99.0),
        _point(dt.datetime(2026, 9, 22, 22, 15), 98.0),
    ]}]
    geometry = _chart_geometry(series)
    xs = [point['x'] for point in geometry['series'][0]['points']]
    assert xs[2] - xs[1] < 1.0


def test_record_year_bands_follow_the_local_calendar():
    """00:30 on New Year's Day in Berlin is 23:30 on 31 December in UTC: that
    record was set in the new year."""
    records = [
        {'name': 'Neujahr', 'started_at': dt.datetime(2025, 12, 31, 23, 30)},
        {'name': 'Silvester', 'started_at': dt.datetime(2025, 12, 31, 12, 0)},
    ]
    bands = _year_bands(records)
    assert [(band['year'], [r['name'] for r in band['records']]) for band in bands] == [
        (2026, ['Neujahr']), (2025, ['Silvester'])]
