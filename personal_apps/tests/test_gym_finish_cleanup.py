"""The one-time cleanup of finished workouts (scripts/gym_finish_cleanup.py,
the walkthrough's P): every workout the old finish closed made to look as
today's finish leaves one, with the app's own rules -- and nothing else
touched, a backup of every row first, and the backup enough to put it all
back.

Each test scopes the script to its own throwaway lifters, and every dry run
here checks that its plan stays with them (dry) before anything commits."""
import datetime as dt
import json
import os
import types
from pathlib import Path

import pytest
from sqlalchemy import or_, select, text
from sqlalchemy.exc import OperationalError

from app import app as flask_app
from extensions import db
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import PendingPush, SessionExercise, SessionSet, SharedSession, WorkoutSession
from scripts import gym_finish_cleanup as cleanup

HOUR = dt.timedelta(hours=1)


def quiet(_line):
    pass


def snapshot(user_ids):
    """Every row of these lifters' workouts, their rows, sets, pushes and
    links, as stored."""
    with flask_app.app_context():
        def rows(table, *where):
            found = db.session.execute(select(table).where(*where).order_by(table.c.id))
            return [dict(row) for row in found.mappings()]
        workouts = rows(cleanup.WORKOUTS, cleanup.WORKOUTS.c.user_id.in_(user_ids))
        ids = [w['id'] for w in workouts]
        exercise_rows = rows(cleanup.ROWS, cleanup.ROWS.c.session_id.in_(ids))
        return {
            'workouts': workouts,
            'rows': exercise_rows,
            'sets': rows(cleanup.SETS, cleanup.SETS.c.session_exercise_id.in_(
                [r['id'] for r in exercise_rows])),
            'pushes': rows(cleanup.PUSHES, cleanup.PUSHES.c.session_id.in_(ids)),
            'links': rows(cleanup.LINKS, or_(cleanup.LINKS.c.leader_user_id.in_(user_ids),
                                             cleanup.LINKS.c.follower_user_id.in_(user_ids))),
        }


def dry(user_ids, say=quiet):
    """The dry run -- and never a plan reaching past these lifters: every
    commit here follows one, and a scope gone wrong must not clean the rest
    of the local database."""
    with flask_app.app_context():
        plan = cleanup.run(user_ids, say=say)
        touched = plan.workouts() + [workout for workout, _ in plan.pointers]
        owners = {w.user_id for w in WorkoutSession.query.filter(WorkoutSession.id.in_(touched))}
    assert owners <= set(user_ids), f'the plan reaches past its lifters: {owners}'
    return plan


def cleaned(user_ids, backup, say=quiet):
    """The dry run, then the cleanup it reported."""
    plan = dry(user_ids)
    with flask_app.app_context():
        return cleanup.run(user_ids, commit=cleanup.digest(plan), backup_path=backup, say=say)


def elsewhere(sql, **params):
    """A write from another connection -- another request of the app's --
    that waits a second at most for a lock: 'held' when it had to give up."""
    with db.engine.connect() as other:
        try:
            other.execute(text('SET SESSION innodb_lock_wait_timeout = 1'))
            other.execute(text(sql), params)
            other.commit()
            return 'written'
        except OperationalError as error:
            if error.orig.args[0] != 1205:  # Lock wait timeout exceeded
                raise
            other.rollback()
            return 'held'
        finally:
            other.invalidate()  # not back to the pool with a one-second wait


def link(leader, follower_user, follower=None, accepted=True, declined=False):
    row = SharedSession(leader_session_id=leader.id, leader_user_id=leader.user_id,
                        follower_session_id=follower.id if follower is not None else None,
                        follower_user_id=follower_user, created_at=leader.started_at,
                        accepted_at=leader.started_at if accepted else None,
                        declined_at=leader.started_at if declined else None)
    db.session.add(row)
    db.session.flush()
    return row


def push(workout, sent=False):
    row = PendingPush(session_id=workout.id, fire_at=workout.started_at, sent=sent)
    db.session.add(row)
    db.session.flush()
    return row


def sets_of(workout_id):
    return sorted(s.id for s in SessionSet.query.join(SessionExercise)
                  .filter(SessionExercise.session_id == workout_id))


def test_a_finished_workout_without_a_set_that_counts_goes_with_its_links_and_pushes(
        lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        partner = lifter.partner()
        led = lifter.workout(5 * HOUR, finished=True)
        lifter.row(led, bench, 1, done=[(60, 8), (60, 8)])
        # Joined, ticked a set without reps and left the rest open.
        empty = lifter.workout(5 * HOUR, user_id=partner, finished=True)
        lifter.row(empty, bench, 1, ticked_empty=1, open_=2)
        link(led, partner, empty)
        push(empty)
        push(empty, sent=True)
        db.session.commit()
        led_id, empty_id, led_sets = led.id, empty.id, sets_of(led.id)

    plan = cleaned([lifter.user_id, partner], tmp_path / 'backup.json')
    assert list(plan.empty) == [empty_id]
    assert plan.left == {}
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, empty_id) is None
        assert SessionExercise.query.filter_by(session_id=empty_id).count() == 0
        assert PendingPush.query.filter_by(session_id=empty_id).count() == 0
        assert SharedSession.query.filter(or_(
            SharedSession.leader_session_id == empty_id,
            SharedSession.follower_session_id == empty_id)).count() == 0
        # The partner's workout stays as it was.
        assert db.session.get(WorkoutSession, led_id) is not None
        assert sets_of(led_id) == led_sets


def test_a_set_lifted_before_its_exercise_was_skipped_or_replaced_counts(lifter):
    with flask_app.app_context():
        bench, dip = lifter.exercise('Bank'), lifter.exercise('Dips')
        skipped = lifter.workout(6 * HOUR, finished=True)
        lifter.row(skipped, bench, 1, done=[(60, 8)], open_=1, skipped=True)
        lifter.row(skipped, dip, 2, open_=2)
        replaced = lifter.workout(4 * HOUR, finished=True)
        original = lifter.row(replaced, bench, 1, done=[(60, 8)], open_=1)
        lifter.row(replaced, dip, 1, open_=2, replaces=original)
        db.session.commit()
        ids = [skipped.id, replaced.id]

    plan = dry([lifter.user_id])
    assert plan.empty == {}
    assert list(plan.trimmed) == ids


def test_a_finished_workout_keeps_its_planned_count_and_loses_what_was_never_lifted(
        lifter, tmp_path):
    with flask_app.app_context():
        bench, row_ex, dip, fly = (lifter.exercise(name) for name in ('Bank', 'Rudern', 'Dips', 'Fly'))
        workout = lifter.workout(5 * HOUR, finished=True)
        lifted = lifter.row(workout, bench, 1, done=[(60, 8), (60, 8)], ticked_empty=1, open_=1)
        lifter.row(workout, row_ex, 2, done=[(50, 10)], open_=2, skipped=True)
        original = lifter.row(workout, dip, 3, open_=1)
        lifter.row(workout, fly, 4, done=[(20, 12)], open_=1, replaces=original)
        workout.rest_ends_at = workout.finished_at
        workout.resting_set_id = max(s.id for s in lifted.sets)  # an open one
        db.session.commit()
        workout_id = workout.id
        kept = sorted(s.id for se in workout.exercises for s in se.sets if s.completed and s.reps)
        rows = sorted(se.id for se in workout.exercises)

    cleaned([lifter.user_id], tmp_path / 'backup.json')
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        # Counted before anything went, as the finish counts it: 4 that
        # count, and the open ones still ahead -- not the skipped row's, not
        # the replaced original's.
        assert workout.planned_sets == 6
        assert sets_of(workout_id) == kept
        assert sorted(se.id for se in workout.exercises) == rows
        assert workout.rest_ends_at is None and workout.resting_set_id is None


def test_a_workout_todays_finish_closed_is_left_as_it_is(lifter):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        partner = lifter.partner()
        # Its last set deleted in the debrief since: the app keeps it.
        emptied = lifter.workout(6 * HOUR, finished=True)
        lifter.row(emptied, bench, 1)
        emptied.planned_sets = 3
        # A set open again since.
        opened = lifter.workout(4 * HOUR, finished=True)
        lifter.row(opened, bench, 1, done=[(60, 8)], open_=1)
        opened.planned_sets = 2
        # An old partner's link to the emptied one: stamped, not thrown away.
        joined = lifter.workout(6 * HOUR, user_id=partner, finished=True)
        lifter.row(joined, bench, 1, done=[(60, 8)])
        link_id = link(emptied, partner, joined).id
        db.session.commit()

    plan = dry([lifter.user_id, partner])
    assert plan.empty == {} and plan.trimmed == {}
    assert list(plan.links) == [link_id]


def test_a_rest_still_running_on_a_finished_workout_is_cleared(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        workout = lifter.workout(5 * HOUR, finished=True)
        lifted = lifter.row(workout, bench, 1, done=[(60, 8), (60, 8)])
        workout.rest_ends_at = workout.finished_at
        workout.resting_set_id = lifted.sets[-1].id
        db.session.commit()
        workout_id, lifted_sets = workout.id, sets_of(workout.id)

    plan = cleaned([lifter.user_id], tmp_path / 'backup.json')
    assert list(plan.trimmed) == [workout_id]
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        assert workout.rest_ends_at is None and workout.resting_set_id is None
        assert sets_of(workout_id) == lifted_sets


def test_pushes_still_waiting_for_a_finished_workout_go_and_no_other(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        finished = lifter.workout(5 * HOUR, finished=True)
        lifter.row(finished, bench, 1, done=[(60, 8)])
        waiting, sent = push(finished), push(finished, sent=True)
        running = lifter.workout(HOUR)
        lifter.row(running, bench, 1, done=[(60, 8)])
        running_push = push(running)
        db.session.commit()
        waiting_id, sent_id, running_push_id = waiting.id, sent.id, running_push.id

    cleaned([lifter.user_id], tmp_path / 'backup.json')
    with flask_app.app_context():
        assert db.session.get(PendingPush, waiting_id) is None
        assert db.session.get(PendingPush, sent_id) is not None
        assert db.session.get(PendingPush, running_push_id) is not None


def test_links_neither_side_of_which_runs_are_stamped_at_the_first_finish(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        partner, other, third = lifter.partner(), lifter.partner(), lifter.partner()
        led = lifter.workout(6 * HOUR, finished=True)
        lifter.row(led, bench, 1, done=[(60, 8)])
        # They finished first: an hour before the leader.
        followed = lifter.workout(7 * HOUR, user_id=partner, finished=True)
        lifter.row(followed, bench, 1, done=[(60, 8)])
        both = link(led, partner, followed)
        invite = link(led, other, accepted=False)
        declined = link(led, third, accepted=False, declined=True)
        # A leader still training, a follower who finished: the app's.
        running = lifter.workout(HOUR)
        lifter.row(running, bench, 1, done=[(60, 8)])
        gone_first = lifter.workout(3 * HOUR, user_id=other, finished=True)
        lifter.row(gone_first, bench, 1, done=[(60, 8)])
        left = link(running, other, gone_first)
        # Both still training: live.
        live_follower = lifter.workout(HOUR, user_id=third)
        lifter.row(live_follower, bench, 1, done=[(60, 8)])
        live = link(running, third, live_follower)
        db.session.commit()
        expected = {both.id: followed.finished_at, invite.id: led.finished_at,
                    declined.id: led.finished_at}
        left_id, live_id = left.id, live.id

    plan = cleaned([lifter.user_id, partner, other, third], tmp_path / 'backup.json')
    assert plan.left == {left_id: 'one side still runs: the app ends it'}
    with flask_app.app_context():
        for link_id, ended_at in expected.items():
            assert db.session.get(SharedSession, link_id).ended_at == ended_at
        assert db.session.get(SharedSession, left_id).ended_at is None
        assert db.session.get(SharedSession, live_id).ended_at is None


def test_a_run_for_some_lifters_reads_only_theirs(lifter):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        partner, third = lifter.partner(), lifter.partner()
        mine = lifter.workout(6 * HOUR, finished=True)
        lifter.row(mine, bench, 1, done=[(60, 8)], open_=1)
        my_empty = lifter.workout(9 * HOUR, finished=True)
        lifter.row(my_empty, bench, 1, open_=2)
        # Out of the run: the partner's empty workout, joined to mine ...
        theirs = lifter.workout(6 * HOUR, user_id=partner, finished=True)
        lifter.row(theirs, bench, 1, open_=2)
        to_them = link(mine, partner, theirs)
        # ... and two lifters' workouts with work of their own.
        other = lifter.workout(5 * HOUR, user_id=partner, finished=True)
        lifter.row(other, bench, 1, done=[(60, 8)], open_=1)
        thirds = lifter.workout(5 * HOUR, user_id=third, finished=True)
        lifter.row(thirds, bench, 1, done=[(60, 8)])
        link(other, third, thirds)
        db.session.commit()
        mine_id, my_empty_id, theirs_id, to_them_id = mine.id, my_empty.id, theirs.id, to_them.id
    everyone = [lifter.user_id, partner, third]
    before = snapshot(everyone)

    plan = dry([lifter.user_id])
    assert list(plan.empty) == [my_empty_id]
    assert list(plan.trimmed) == [mine_id]
    assert plan.links == {}
    # The partner's workout goes in a run for them, and the link with it.
    assert plan.left == {to_them_id: f'workout {theirs_id} of user {partner} goes, '
                                     'and the link with it, in a run for that lifter'}
    assert snapshot(everyone) == before


def test_a_running_workout_is_left_alone(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        running = lifter.workout(HOUR)
        lifted = lifter.row(running, bench, 1, done=[(60, 8)], ticked_empty=1, open_=2)
        running.rest_ends_at = lifter.now
        running.resting_set_id = lifted.sets[0].id
        push(running)
        # And one with nothing that counts yet.
        lifter.row(lifter.workout(2 * HOUR), bench, 1, open_=3)
        db.session.commit()
    before = snapshot([lifter.user_id])

    plan = cleaned([lifter.user_id], tmp_path / 'backup.json')
    assert plan.nothing()
    assert snapshot([lifter.user_id]) == before
    assert not (tmp_path / 'backup.json').exists()


def test_the_dry_run_writes_nothing(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        lifter.row(lifter.workout(5 * HOUR, finished=True), bench, 1, done=[(60, 8)], open_=2)
        lifter.row(lifter.workout(3 * HOUR, finished=True), bench, 1, open_=2)
        db.session.commit()
    before = snapshot([lifter.user_id])
    said = []

    with flask_app.app_context():
        plan = cleanup.run([lifter.user_id], backup_path=tmp_path / 'backup.json',
                           say=said.append)
    assert len(plan.empty) == 1 and len(plan.trimmed) == 1
    assert snapshot([lifter.user_id]) == before
    assert not (tmp_path / 'backup.json').exists()
    assert said[-1] == ('Dry run -- nothing written. To do exactly this: '
                        f'--commit {cleanup.digest(plan)}')


def test_the_report_names_what_goes_and_what_the_lifter_put_on_it(lifter):
    # Stored in UTC; Verlauf, which the report is checked against, shows
    # Berlin time: 21:30 UTC is 23:30, and 22:40 is 00:40 the next day.
    start, end = dt.datetime(2026, 9, 22, 21, 30), dt.datetime(2026, 9, 22, 22, 40)
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        partner, third = lifter.partner(), lifter.partner()
        empty = lifter.workout(5 * HOUR, user_id=partner, finished=True)
        empty.started_at, empty.finished_at = start, end
        empty.notes = 'Beine schwer'
        empty.bodyweight_kg = 81.5
        sore = lifter.row(empty, bench, 1, open_=2)
        sore.notes = 'Schulter\n zwickt'
        sore.pain = True
        followed = lifter.workout(5 * HOUR, finished=True)
        followed.started_at, followed.finished_at = start, end
        mirror = lifter.row(followed, bench, 1, done=[(60, 8)], open_=1)
        mirror.mirrors_id = sore.id
        joined = link(empty, lifter.user_id, followed)
        beside = lifter.workout(5 * HOUR, user_id=third, finished=True)
        beside.started_at, beside.finished_at = start, end - dt.timedelta(minutes=30)
        lifter.row(beside, bench, 1, done=[(60, 8)])
        stamped = link(followed, third, beside)
        db.session.commit()
        empty_id, followed_id, mirror_id, link_id = empty.id, followed.id, mirror.id, joined.id
        beside_id, stamped_id = beside.id, stamped.id
    said = []

    dry([lifter.user_id, partner, third], say=said.append)
    assert said[1] == 'Times are local, as the app shows them.'
    assert f'  {empty_id}  user {partner}  2026-09-22 23:30 to 2026-09-23 00:40  1 row, 2 sets, ' \
           f'0 pushes; links {link_id} (with workout {followed_id}); bodyweight 81.5 kg; ' \
           'pain: pytest gym Bank; notes: "Beine schwer" / "Schulter zwickt"' in said
    pointers = said.index('Rows of other workouts that lose their pointer to a row thrown away '
                          '(the database sets it NULL; their sets stay): 1')
    assert said[pointers + 1] == f'  row {mirror_id} of workout {followed_id}'
    assert (f'  {followed_id}  user {lifter.user_id}  finished 2026-09-23  planned_sets 2 stored; '
            'open sets go: 1') in said
    assert (f'  {stamped_id}  workouts {followed_id} and {beside_id}  '
            'ended_at 2026-09-23 00:10:00') in said


def test_it_is_done_once(lifter, tmp_path):
    with flask_app.app_context():
        bench = lifter.exercise('Bank')
        lifter.row(lifter.workout(5 * HOUR, finished=True), bench, 1, done=[(60, 8)], open_=2)
        lifter.row(lifter.workout(3 * HOUR, finished=True), bench, 1, open_=2)
        db.session.commit()

    plan = dry([lifter.user_id])
    with flask_app.app_context():
        cleanup.run([lifter.user_id], commit=cleanup.digest(plan),
                    backup_path=tmp_path / 'first.json', say=quiet)
    said = []
    with flask_app.app_context():
        assert cleanup.run([lifter.user_id], commit=cleanup.digest(plan),
                           backup_path=tmp_path / 'second.json', say=said.append).nothing()
    assert said[-1] == 'Nothing to do.'
    assert not (tmp_path / 'second.json').exists()


def build_everything(lifter):
    """One of each: an empty leader whose row a follower mirrors, and a
    stray row mirroring it without a link; an empty follower whose rows
    mirror, replace and rest on rows of its own; a trimmed workout with a
    rest, a tick without reps and pushes; a link to stamp."""
    with flask_app.app_context():
        bench, dip = lifter.exercise('Bank'), lifter.exercise('Dips')
        partner, other = lifter.partner(), lifter.partner()
        empty_leader = lifter.workout(8 * HOUR, finished=True)
        led_row = lifter.row(empty_leader, bench, 1, open_=3)
        push(empty_leader)
        follower = lifter.workout(8 * HOUR, user_id=partner, finished=True)
        lifter.row(follower, bench, 1, done=[(60, 8)], open_=1).mirrors_id = led_row.id
        link(empty_leader, partner, follower)
        # A partner whose link went long ago: the pointer stayed.
        stray = lifter.workout(7 * HOUR, user_id=other, finished=True)
        stray_row = lifter.row(stray, bench, 1, done=[(60, 8)])
        stray_row.mirrors_id = led_row.id
        trimmed = lifter.workout(5 * HOUR, finished=True)
        lifted = lifter.row(trimmed, bench, 1, done=[(60, 8)], ticked_empty=1, open_=2)
        trimmed.rest_ends_at = trimmed.finished_at
        trimmed.resting_set_id = lifted.sets[-1].id
        waiting = push(trimmed)
        push(trimmed, sent=True)
        joined = lifter.workout(4 * HOUR, user_id=partner, finished=True)
        lifter.row(joined, bench, 1, done=[(60, 8)])
        stamped = link(trimmed, partner, joined)
        # Joined the trimmed one and lifted nothing: its rows point at the
        # leader's and at each other, its rest at a set of its own.
        empty_follower = lifter.workout(5 * HOUR, user_id=other, finished=True)
        lifter.row(empty_follower, bench, 1, open_=1).mirrors_id = lifted.id
        original = lifter.row(empty_follower, dip, 2, open_=1)
        substitute = lifter.row(empty_follower, bench, 2, ticked_empty=1, replaces=original)
        empty_follower.resting_set_id = substitute.sets[0].id
        link(trimmed, other, empty_follower)
        db.session.commit()
        return types.SimpleNamespace(
            scope=[lifter.user_id, partner, other], empty_leader=empty_leader.id,
            led_row=led_row.id, stray_row=stray_row.id, lifted_row=lifted.id,
            open_set=max(s.id for s in lifted.sets if not s.completed),
            waiting_push=waiting.id, stamped=stamped.id)


def test_the_backup_puts_every_row_back(lifter, tmp_path):
    scope = build_everything(lifter).scope
    before = snapshot(scope)
    backup = tmp_path / 'backup.json'

    plan = cleaned(scope, backup)
    assert (len(plan.empty), len(plan.pointers), len(plan.trimmed), len(plan.links)) == (2, 2, 2, 1)
    assert snapshot(scope) != before

    with flask_app.app_context():
        cleanup.restore(json.loads(backup.read_text(encoding='utf-8')))
    assert snapshot(scope) == before


def test_a_restore_refuses_rows_that_are_back_already(lifter, tmp_path):
    scope = build_everything(lifter).scope
    backup = tmp_path / 'backup.json'
    cleaned(scope, backup)
    with flask_app.app_context():
        cleanup.restore(json.loads(backup.read_text(encoding='utf-8')))
    restored = snapshot(scope)

    with flask_app.app_context(), pytest.raises(SystemExit):
        cleanup.restore(json.loads(backup.read_text(encoding='utf-8')))
    assert snapshot(scope) == restored


TICK = 'UPDATE gym_session_sets SET completed = 1, reps = 8 WHERE id = :id'


def test_it_stops_when_the_rows_moved_since_the_dry_run(lifter, tmp_path):
    built = build_everything(lifter)
    plan = dry(built.scope)
    with flask_app.app_context():
        assert elsewhere(TICK, id=built.open_set) == 'written'
    moved = snapshot(built.scope)
    backup = tmp_path / 'backup.json'

    with flask_app.app_context(), pytest.raises(SystemExit):
        cleanup.run(built.scope, commit=cleanup.digest(plan), backup_path=backup, say=quiet)
    assert snapshot(built.scope) == moved
    assert not backup.exists()


def test_it_reads_the_rows_again_under_the_lock(lifter, tmp_path, monkeypatch):
    built = build_everything(lifter)
    plan = dry(built.scope)
    real, calls = cleanup.survey, []

    def ticked_meanwhile(user_ids):
        found = real(user_ids)
        calls.append(found)
        if len(calls) == 1:
            # On the phone, between the first read and the lock.
            assert elsewhere(TICK, id=built.open_set) == 'written'
        return found
    monkeypatch.setattr(cleanup, 'survey', ticked_meanwhile)
    backup = tmp_path / 'backup.json'

    with flask_app.app_context(), pytest.raises(SystemExit):
        cleanup.run(built.scope, commit=cleanup.digest(plan), backup_path=backup, say=quiet)
    with flask_app.app_context():
        lifted = db.session.get(SessionSet, built.open_set)
        assert lifted is not None and lifted.completed and lifted.reps == 8
    assert not backup.exists()


def test_the_lock_holds_every_write_of_the_app_until_the_commit(lifter, tmp_path, monkeypatch):
    built = build_everything(lifter)
    plan = dry(built.scope)
    note = 'UPDATE {} SET notes = :note WHERE id = :id'
    writes = {
        'the workout': (note.format('gym_workout_sessions'),
                        {'id': built.empty_leader, 'note': 'x'}),
        'its row': (note.format('gym_session_exercises'), {'id': built.led_row, 'note': 'x'}),
        'a row pointing at it': (note.format('gym_session_exercises'),
                                 {'id': built.stray_row, 'note': 'x'}),
        'a set': (TICK, {'id': built.open_set}),
        'a new set': ('INSERT INTO gym_session_sets (session_exercise_id, position, weight, '
                      'reps, completed) VALUES (:id, 99, 60, 8, 1)', {'id': built.lifted_row}),
        'a push': ('UPDATE gym_pending_pushes SET sent = 1 WHERE id = :id',
                   {'id': built.waiting_push}),
        'a link': ('UPDATE gym_shared_sessions SET ended_at = UTC_TIMESTAMP() WHERE id = :id',
                   {'id': built.stamped}),
    }
    tried, real_apply = {}, cleanup.apply

    def apply_after_the_phone(found):
        for name, (sql, params) in writes.items():
            tried[name] = elsewhere(sql, **params)
        real_apply(found)
    monkeypatch.setattr(cleanup, 'apply', apply_after_the_phone)

    with flask_app.app_context():
        cleanup.run(built.scope, commit=cleanup.digest(plan), backup_path=tmp_path / 'backup.json',
                    say=quiet)
    assert tried == {name: 'held' for name in writes}


def test_it_writes_nothing_when_the_cleanup_left_work_behind(lifter, tmp_path, monkeypatch):
    scope = build_everything(lifter).scope
    before = snapshot(scope)
    monkeypatch.setattr(cleanup, 'apply', lambda plan: None)

    with pytest.raises(SystemExit):
        cleaned(scope, tmp_path / 'backup.json')
    assert snapshot(scope) == before


def test_it_will_not_write_over_a_backup(lifter, tmp_path):
    scope = build_everything(lifter).scope
    before = snapshot(scope)
    backup = tmp_path / 'backup.json'
    backup.write_text('mine', encoding='utf-8')

    with pytest.raises(SystemExit):
        cleaned(scope, backup)
    assert snapshot(scope) == before
    assert backup.read_text(encoding='utf-8') == 'mine'


def test_the_backup_is_on_disk_before_anything_changes(lifter, tmp_path, monkeypatch):
    scope = build_everything(lifter).scope
    plan = dry(scope)
    synced, seen = [], []
    monkeypatch.setattr(cleanup, 'os', types.SimpleNamespace(
        name='posix', O_RDONLY=os.O_RDONLY,
        open=lambda path, flags: synced.append(('open', Path(path), flags)) or -1,
        fsync=lambda fd: synced.append(('fsync', fd)),
        close=lambda fd: synced.append(('close', fd))))
    real_apply = cleanup.apply
    monkeypatch.setattr(cleanup, 'apply', lambda found: seen.append(list(synced))
                        or real_apply(found))

    with flask_app.app_context():
        cleanup.run(scope, commit=cleanup.digest(plan), backup_path=tmp_path / 'backup.json',
                    say=quiet)
    (kind, fd), *directory = seen[0]
    assert kind == 'fsync' and fd >= 0  # the file's bytes
    assert directory == [('open', tmp_path, os.O_RDONLY), ('fsync', -1), ('close', -1)]
