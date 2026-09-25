"""Calendar keys are the lifter's dates, not UTC's (walkthrough 2026-09-23,
G-129; G-032 and G-052 are the same bug on the client).

Timestamps are stored naive-UTC. Between midnight and 02:00 in Berlin (01:00
in winter) the UTC date is still yesterday, so any day, month or year taken
straight from a stored timestamp put a late-night workout on the wrong one.
The career strip, the export range and the monthly helpers live in their own
test files; this one had no home. (The exercise page's chart spread two
workouts of one day apart and had two here; its Rekordtreppe places workouts
by their order, not their date -- D9.)
"""
import datetime as dt

from features.gym.routes.reports import _month_index


def test_the_running_month_of_the_verlauf_index_is_the_local_one():
    """00:30 on New Year's Day in Berlin is 23:30 on 31 December in UTC: the
    month still running is January, and the workout lifted then is in it."""
    now = dt.datetime(2025, 12, 31, 23, 30)
    index = _month_index([], [dt.datetime(2025, 11, 20, 18, 0), now], now)
    assert [(m['slug'], m['is_current']) for m in index] == [
        ('2025-11', False), ('2025-12', False), ('2026-01', True)]
    assert [m['is_gap'] for m in index] == [False, True, False]
