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

from features.gym.routes.reports import _year_bands


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
