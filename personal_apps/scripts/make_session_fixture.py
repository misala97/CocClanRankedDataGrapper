"""Capture a real live-workout payload as a test fixture.

    python scripts/make_session_fixture.py

Builds a throwaway session with two exercises -- one part-completed and live,
one skipped -- hits /gym/session/<id>/detail.json, writes the response to
static/gym/src/session/__fixtures__/session-payload.json, and deletes the
session again.

Two exercises rather than one on purpose: a single-exercise session cannot
exercise the queue, the live/not-live distinction, or the tick strip's
per-exercise grouping, and those are most of what the components do.

Generated rather than hand-written because step 1's hand-written fixture was
wrong in five places -- and every one of those would have been a component
built against a contract the server does not serve.
"""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))

from app import app as flask_app                                   # noqa: E402
from conftest import _admin_id                                     # noqa: E402
from extensions import db                                          # noqa: E402
from features.gym.exercises import touched_exercises               # noqa: E402
from models import (                                               # noqa: E402
    PendingPush, SessionExercise, SessionSet, WorkoutSession,
)

DEST = (pathlib.Path(__file__).resolve().parent.parent
        / 'static' / 'gym' / 'src' / 'session' / '__fixtures__'
        / 'session-payload.json')


def main():
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        user_id = _admin_id()
        exercises = sorted(touched_exercises(user_id), key=lambda e: e.id)[:2]
        if len(exercises) < 2:
            raise SystemExit('the dev database needs at least two exercises')

        session_ = WorkoutSession(user_id=user_id, name='Fixture Workout',
                                  started_at=dt.datetime.utcnow())
        db.session.add(session_)
        db.session.flush()

        live = SessionExercise(session_id=session_.id,
                               exercise_id=exercises[0].id, position=1)
        skipped = SessionExercise(session_id=session_.id,
                                  exercise_id=exercises[1].id, position=2,
                                  skipped=True)
        db.session.add_all([live, skipped])
        db.session.flush()
        db.session.add_all([
            # One done, one open: the live exercise is mid-set, which is the
            # state the panel is designed around.
            SessionSet(session_exercise_id=live.id, weight=60.0, reps=8, completed=True),
            SessionSet(session_exercise_id=live.id, weight=60.0, reps=8, completed=False),
            SessionSet(session_exercise_id=live.id, weight=62.5, reps=6, completed=False),
            SessionSet(session_exercise_id=skipped.id, weight=40.0, reps=10, completed=False),
        ])
        db.session.commit()
        session_id = session_.id

    try:
        with flask_app.test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session['user_id'] = user_id
            response = client.get(f'/gym/session/{session_id}/detail.json')
            if response.status_code != 200:
                raise SystemExit(
                    f'endpoint returned {response.status_code}, not 200')
            payload = response.get_json()
    finally:
        with flask_app.app_context():
            row = db.session.get(WorkoutSession, session_id)
            if row is not None:
                row.resting_set_id = None
                row.rest_ends_at = None
                PendingPush.query.filter_by(session_id=row.id).delete()
                db.session.flush()
                db.session.delete(row)
                db.session.commit()

    # Ids are database-assigned and change every run, which would make the
    # fixture churn on every regeneration. Normalised to stable values so a
    # diff of this file only ever shows a real contract change.
    payload = _stabilise(payload)

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    print(f'wrote {DEST.name}: {len(payload["visible_exercises"])} exercises, '
          f'{payload["sets_total"]} sets, live_id={payload["live_id"]}')


def _stabilise(payload):
    """Renumber ids deterministically so regeneration produces a stable file."""
    se_map = {se['id']: 10 + i for i, se in enumerate(payload['visible_exercises'])}
    set_map = {}
    for se in payload['visible_exercises']:
        for s in se['sets']:
            set_map[s['id']] = 100 + len(set_map)

    payload['session']['id'] = 1
    for se in payload['visible_exercises']:
        se['id'] = se_map[se['id']]
        for s in se['sets']:
            s['id'] = set_map[s['id']]
    if payload['live_id'] is not None:
        payload['live_id'] = se_map[payload['live_id']]
    payload['record_set_ids'] = sorted(
        set_map[i] for i in payload['record_set_ids'] if i in set_map)
    # Keyed by Set.id, not SessionExercise.id -- so it renumbers with set_map,
    # not with the loop below.
    payload['record_details'] = {
        str(set_map[int(k)]): v for k, v in payload['record_details'].items()
        if int(k) in set_map
    }
    payload['suggestions'] = {
        str(se_map[int(k)]): v for k, v in payload['suggestions'].items()
        if int(k) in se_map
    }
    payload['stagnation_counts'] = {
        str(se_map[int(k)]): v for k, v in payload['stagnation_counts'].items()
        if int(k) in se_map
    }
    # Every dict keyed by SessionExercise.id has to be renumbered with the
    # rows, or the fixture names exercises it does not contain.
    for keyed_by_se in ('seed_sources', 'next_targets', 'deload_hints', 'routine_plans'):
        payload[keyed_by_se] = {
            str(se_map[int(k)]): v for k, v in payload[keyed_by_se].items()
            if int(k) in se_map
        }
    if payload['session'].get('resting_set_id') in set_map:
        payload['session']['resting_set_id'] = set_map[payload['session']['resting_set_id']]
    # Other lifters' account names are theirs, not test data: the fixture is
    # committed, and the partner picker only needs someone to pick.
    names = {p['username']: f'Partner {i}' for i, p in enumerate(payload['partners'], start=1)}
    payload['partners'] = [{'id': 1000 + i, 'username': f'Partner {i}'}
                           for i, _ in enumerate(payload['partners'], start=1)]
    payload['partner_status'] = [{**s, 'username': names.get(s['username'], 'Partner')}
                                 for s in payload['partner_status']]
    return payload


if __name__ == '__main__':
    main()
