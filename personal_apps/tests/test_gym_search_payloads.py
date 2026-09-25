"""Übungen and Verlauf search with the add sheet's text.

A word that found an exercise in the add sheet found nothing on Übungen
("bench", G-020) or in Verlauf, which matched the bare names (G-145). Both
pages now get the list's search text -- aliases, English names, movement
aliases -- and search it with the one matcher (static/gym/src/search.ts).
"""
import datetime as dt

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym import stats
from features.gym.library import BY_KEY, fold
from features.gym.routes.helpers import MONTH_NAMES
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import Exercise

DAY = dt.timedelta(days=1)
BENCH = 'barbell_bench_press'


def _bench_workout(lifter):
    """A finished workout of the list's bench press; its local start."""
    with flask_app.app_context():
        bench = Exercise.query.filter_by(library_key=BENCH).one()
        workout = lifter.workout(2 * DAY, finished=True)
        lifter.row(workout, bench, 1, done=[(60, 8)])
        db.session.commit()
        return stats.to_local(workout.started_at)


def test_an_uebungen_row_carries_the_add_sheet_text(lifter):
    _bench_workout(lifter)
    page = lifter.client().get('/gym/uebungen').get_data(as_text=True)

    rows = [e for g in embedded_payload(page)['groups'] for e in g['entries']]
    row = next(e for e in rows if e['exercise']['name'] == BY_KEY[BENCH].name)
    assert row['search'] == BY_KEY[BENCH].search_text
    assert 'bench press' in row['search']


def test_a_verlauf_row_is_searched_by_name_date_and_its_exercises(lifter):
    started = _bench_workout(lifter)
    page = lifter.client().get('/gym/verlauf').get_data(as_text=True)

    payload = embedded_payload(page)
    entry = payload['months'][0]['entries'][0]
    # Apart: "gym 2" would otherwise be this workout by its name's end and
    # its date's start.
    assert entry['search'] == '%s\n%s' % (fold('pytest gym'), fold('%s %s %d' % (
        started.strftime('%d.%m.%Y'), MONTH_NAMES[started.month - 1], started.year)))
    # Once per exercise, not once per row it is in.
    assert payload['exercise_search'] == {BY_KEY[BENCH].name: BY_KEY[BENCH].search_text}
