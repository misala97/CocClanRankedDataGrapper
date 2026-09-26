"""B11a: how training together ends, the server half (G-137, D14 c).

Live means both workouts still run. An invite into a workout that is over,
or that nobody came back to, is off Start. A partner nobody came back to
ends the link on the other's next page. Either side ends it by hand, and
the leader takes back an invite nobody joined. Every end hands the
follower their order without moving their card (the carry from I5)."""
import datetime as dt

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym import sharing
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import SessionExercise, SessionSet, SharedSession, WorkoutSession

MIN = dt.timedelta(minutes=1)
HOUR = dt.timedelta(hours=1)
JSON = {'Accept': 'application/json'}

# The follower's rows as _dragged builds them, before and after the handover.
FOLLOWED = [('bench', 1), ('row', 2), ('press', 3), ('curl', 4)]
HANDED_OVER = [('bench', 1), ('press', 2), ('row', 3), ('curl', 4)]


def _link(lifter, leader_workout, follower_id, follower_workout=None, accepted=True,
          declined=False):
    link = SharedSession(
        leader_session_id=leader_workout.id, leader_user_id=leader_workout.user_id,
        follower_user_id=follower_id,
        follower_session_id=follower_workout.id if follower_workout is not None else None,
        created_at=lifter.now - 30 * MIN,
        accepted_at=lifter.now - 25 * MIN if accepted else None,
        declined_at=lifter.now - 10 * MIN if declined else None)
    db.session.add(link)
    db.session.flush()
    return link


def _dragged(lifter, workout, lifts, quiet=dt.timedelta()):
    """The leader's order as the follower holds it: bench done; row open --
    the leader dragged it up; press, which the follower had started; curl
    open. The newest set `quiet` plus two minutes ago."""
    lifter.row(workout, lifts[0], 1, done=[(40, 8)] * 2,
               done_ago=[quiet + 20 * MIN, quiet + 17 * MIN])
    lifter.row(workout, lifts[1], 2, open_=3)
    lifter.row(workout, lifts[2], 3, done=[(30, 10)], done_ago=[quiet + 2 * MIN], open_=2)
    lifter.row(workout, lifts[3], 4, open_=3)


def _pair(lifter, leader_quiet=3 * MIN, follower_quiet=dt.timedelta(), leader_lifted=True):
    """A leader's running workout and a joined follower's (_dragged), each
    left alone for about as long as given. Returns ids."""
    partner = lifter.partner()
    lifts = [lifter.exercise(name) for name in ('bench', 'row', 'press', 'curl')]
    leader = lifter.workout(leader_quiet + 40 * MIN)
    lifter.row(leader, lifts[0], 1, done=[(60, 8)] if leader_lifted else (),
               done_ago=[leader_quiet] if leader_lifted else None, open_=2)
    follower = lifter.workout(follower_quiet + 35 * MIN, user_id=partner)
    _dragged(lifter, follower, lifts, follower_quiet)
    link = _link(lifter, leader, partner, follower)
    return {'partner': partner, 'leader': leader.id, 'follower': follower.id, 'link': link.id}


def _order(workout_id):
    """Every row of the workout, hidden originals too: (name, position)."""
    with flask_app.app_context():
        rows = SessionExercise.query.filter_by(session_id=workout_id).all()
        return [(se.exercise.name.removeprefix('pytest gym '), se.position)
                for se in sorted(rows, key=lambda se: (se.position, se.id))]


def _live(lifter, workout_id, user_id=None):
    """The exercise the lifter's own screen has live."""
    detail = lifter.client(user_id).get(f'/gym/session/{workout_id}/detail.json').get_json()
    return next(se['name'] for se in detail['visible_exercises']
                if se['id'] == detail['live_id']).removeprefix('pytest gym ')


def _ended(link_id):
    with flask_app.app_context():
        link = db.session.get(SharedSession, link_id)
        return link is not None and link.ended_at is not None


def _recording(monkeypatch, module):
    """Every id set `module`'s lock_sessions is asked for, passed through."""
    calls, lock = [], module.lock_sessions
    monkeypatch.setattr(module, 'lock_sessions',
                        lambda ids: (calls.append(set(ids)), lock(ids))[1])
    return calls


# --- Live means both still run -------------------------------------------------


def test_a_link_is_live_only_while_both_workouts_run(lifter):
    """A finished workout ends the sharing even where no stamp says so: its
    partner followed an order nobody set any more, and a leader's changes
    kept landing in a workout that was over (prod rows 2334, 12687)."""
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()
        assert sharing.is_live_follower(pair['follower'])
        assert [link.id for link in sharing.active_links_led_by(pair['leader'])] == [pair['link']]
        for finished, other in (('leader', 'follower'), ('follower', 'leader')):
            db.session.get(WorkoutSession, pair[finished]).finished_at = lifter.now - MIN
            db.session.get(WorkoutSession, pair[other]).finished_at = None
            db.session.commit()
            assert not sharing.is_live_follower(pair['follower'])
            assert sharing.active_links_led_by(pair['leader']) == []
            assert sharing.live_links_of(pair['leader']) == []
            assert sharing.live_links_of(pair['follower']) == []
        db.session.get(WorkoutSession, pair['follower']).finished_at = None
        db.session.get(WorkoutSession, pair['leader']).finished_at = lifter.now - MIN
        db.session.commit()

    detail = lifter.client(pair['partner']).get(
        f"/gym/session/{pair['follower']}/detail.json").get_json()
    assert detail['session_is_shared'] is False


# --- Invites that no longer hold -------------------------------------------------


def test_start_offers_no_invite_into_a_workout_that_is_over_or_left_alone(lifter):
    """The confirm page refused them; Start kept the card until the leader's
    own next page ended the workout -- days, for one who never came back."""
    with flask_app.app_context():
        partner = lifter.partner()
        bench = lifter.exercise('bench')
        live = lifter.workout(40 * MIN)
        lifter.row(live, bench, 1, done=[(60, 8)], done_ago=[5 * MIN], open_=2)
        never_began = lifter.workout(4 * HOUR)
        lifter.row(never_began, bench, 1, open_=3)
        gone_quiet = lifter.workout(5 * HOUR)
        lifter.row(gone_quiet, bench, 1, done=[(60, 8)], done_ago=[210 * MIN], open_=2)
        # Finished an hour ago without the invite stamped (a finish from
        # before B11), and not three hours old: over, not left alone.
        over = lifter.workout(2 * HOUR, finished=True)
        ids = [_link(lifter, workout, partner, accepted=False).id
               for workout in (live, never_began, gone_quiet, over)]
        db.session.commit()

    start = embedded_payload(lifter.client(partner).get('/gym').get_data(as_text=True))
    assert [invite['shared_id'] for invite in start['pending_invites']] == [ids[0]]
    # Only read: the leader's own next page ends the workout, and the
    # invite with it (sharing.end_links_for).
    assert not any(_ended(link_id) for link_id in ids)


# --- A partner nobody came back to ----------------------------------------------


def test_a_leader_nobody_came_back_to_ends_the_link_on_the_followers_page(lifter, monkeypatch):
    """Four hours without a set: the follower's next page ends the link, and
    their card stays on the exercise they are at. The leader's workout is
    the leader's own to end -- their phone may still hold sets for it. Both
    workouts are locked first: the leader's own settle may be deleting the
    link at that moment."""
    from features.gym.routes import helpers
    locked = _recording(monkeypatch, helpers)
    with flask_app.app_context():
        pair = _pair(lifter, leader_quiet=4 * HOUR)
        db.session.commit()

    assert lifter.client(pair['partner']).get('/gym').status_code == 200
    assert _ended(pair['link'])
    assert {pair['follower'], pair['leader']} in locked
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['leader']).finished_at is None
    assert _order(pair['follower']) == HANDED_OVER
    assert _live(lifter, pair['follower'], pair['partner']) == 'press'


def test_a_follower_nobody_came_back_to_keeps_their_card_all_the_same(lifter, monkeypatch):
    """From the leader's page: the link ends and the follower's order is
    handed over, as at every end -- one offline with sets still on the phone
    comes back to the exercise they were at (B11a review). Their workout is
    theirs to end. A follower still training stays linked."""
    from features.gym.routes import helpers
    locked = _recording(monkeypatch, helpers)
    with flask_app.app_context():
        pair = _pair(lifter, follower_quiet=4 * HOUR)
        second = lifter.partner()
        theirs = lifter.workout(30 * MIN, user_id=second)
        lifter.row(theirs, lifter.exercise('squat'), 1, done=[(80, 5)], done_ago=[MIN], open_=2)
        still_there = _link(lifter, db.session.get(WorkoutSession, pair['leader']), second, theirs)
        still_there_id = still_there.id
        db.session.commit()

    assert lifter.client().get(f"/gym/session/{pair['leader']}").status_code == 200
    assert _ended(pair['link'])
    assert not _ended(still_there_id)
    assert {pair['leader'], pair['follower']} in locked
    assert _order(pair['follower']) == HANDED_OVER
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['follower']).finished_at is None


def test_partners_who_are_both_there_stay_linked(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()

    for user_id, workout_id in ((None, pair['leader']), (pair['partner'], pair['follower'])):
        assert lifter.client(user_id).get(f'/gym/session/{workout_id}').status_code == 200
    assert not _ended(pair['link'])
    assert _order(pair['follower']) == FOLLOWED


def test_a_partner_back_by_the_time_the_lock_is_had_stays_linked(lifter, monkeypatch):
    """Judged again under the lock: a set the leader logged while this page
    waited for it keeps the link."""
    from features.gym.routes import helpers
    with flask_app.app_context():
        pair = _pair(lifter, leader_quiet=4 * HOUR)
        leader_row = SessionExercise.query.filter_by(session_id=pair['leader']).one().id
        db.session.commit()
    lock = helpers.lock_sessions

    def back_meanwhile(ids):
        db.session.add(SessionSet(session_exercise_id=leader_row, position=9, weight=60.0,
                                  reps=8, completed=True, completed_at=dt.datetime.utcnow()))
        db.session.commit()
        lock(ids)

    monkeypatch.setattr(helpers, 'lock_sessions', back_meanwhile)
    assert lifter.client(pair['partner']).get('/gym').status_code == 200
    assert not _ended(pair['link'])
    assert _order(pair['follower']) == FOLLOWED


def test_a_workout_ended_meanwhile_is_not_the_pages_running_one(lifter, monkeypatch):
    """Finished from the other phone while this page waited for the lock:
    the page finds no running workout, as it would a moment later."""
    from features.gym.routes import helpers
    with flask_app.app_context():
        pair = _pair(lifter, leader_quiet=4 * HOUR)
        db.session.commit()
    lock = helpers.lock_sessions

    def finished_meanwhile(ids):
        db.session.get(WorkoutSession, pair['follower']).finished_at = dt.datetime.utcnow()
        db.session.commit()
        lock(ids)

    monkeypatch.setattr(helpers, 'lock_sessions', finished_meanwhile)
    start = embedded_payload(lifter.client(pair['partner']).get('/gym').get_data(as_text=True))
    assert start['active_session_id'] is None
    assert _order(pair['follower']) == FOLLOWED


# --- Ending it by hand -----------------------------------------------------------


def test_the_follower_trains_on_alone_on_the_exercise_they_are_at(lifter, monkeypatch):
    """ "Nicht mehr mitmachen": the link ends and the order is theirs --
    the row the leader had dragged above the one they were at used to take
    their card, and the next set landed on a lift they were not at."""
    from features.gym.routes import partners
    locked = _recording(monkeypatch, partners)
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()
    assert _live(lifter, pair['follower'], pair['partner']) == 'press'

    response = lifter.client(pair['partner']).post(
        f"/gym/shared/{pair['link']}/end", headers=JSON)
    assert (response.status_code, response.get_json()) == (200, {'ok': True})
    assert _ended(pair['link'])
    assert {pair['leader'], pair['follower']} in locked
    assert _order(pair['follower']) == HANDED_OVER
    assert _live(lifter, pair['follower'], pair['partner']) == 'press'
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['leader']).finished_at is None
        assert db.session.get(WorkoutSession, pair['follower']).finished_at is None

    # Once: a second end, from either side, is told it is over.
    for user_id in (pair['partner'], None):
        assert lifter.client(user_id).post(
            f"/gym/shared/{pair['link']}/end", headers=JSON).status_code == 409


def test_the_leader_ends_training_together_and_the_follower_keeps_their_card(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()

    response = lifter.client().post(f"/gym/shared/{pair['link']}/end", headers=JSON)
    assert (response.status_code, response.get_json()) == (200, {'ok': True})
    assert _ended(pair['link'])
    assert _order(pair['follower']) == HANDED_OVER
    assert _live(lifter, pair['follower'], pair['partner']) == 'press'


def test_only_the_two_sides_of_a_joined_link_end_it(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        stranger = lifter.partner()
        invited = lifter.partner()
        pending = _link(lifter, db.session.get(WorkoutSession, pair['leader']), invited,
                        accepted=False)
        pending_id = pending.id
        db.session.commit()

    assert lifter.client(stranger).post(f"/gym/shared/{pair['link']}/end").status_code == 404
    for user_id in (None, invited):
        assert lifter.client(user_id).post(f'/gym/shared/{pending_id}/end').status_code == 404
    assert lifter.client().post('/gym/shared/2147483000/end').status_code == 404
    assert not _ended(pair['link'])
    assert not _ended(pending_id)


def test_a_link_to_a_workout_that_is_over_is_not_ended_again(lifter):
    """Finished with no stamp on the link: over all the same (409)."""
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.get(WorkoutSession, pair['leader']).finished_at = lifter.now - MIN
        db.session.commit()

    assert lifter.client(pair['partner']).post(
        f"/gym/shared/{pair['link']}/end").status_code == 409
    assert not _ended(pair['link'])
    assert _order(pair['follower']) == FOLLOWED


def test_ending_it_from_a_workout_nobody_came_back_to_files_that_workout_first(lifter):
    """The caller's own workout, three hours without a set: settled first,
    like any write -- filed at its last set, which ends the link (409)."""
    with flask_app.app_context():
        pair = _pair(lifter, follower_quiet=4 * HOUR)
        db.session.commit()

    assert lifter.client(pair['partner']).post(
        f"/gym/shared/{pair['link']}/end", headers=JSON).status_code == 409
    assert _ended(pair['link'])
    with flask_app.app_context():
        follower = db.session.get(WorkoutSession, pair['follower'])
        assert (follower.finished_at is not None, follower.auto_finished) == (True, True)
        assert db.session.get(WorkoutSession, pair['leader']).finished_at is None


def test_ending_it_from_an_empty_workout_nobody_came_back_to_throws_that_away_first(lifter):
    """Nothing lifted in it: thrown away, the link with it (404) -- and the
    follower keeps the exercise they are at, as after any end."""
    with flask_app.app_context():
        pair = _pair(lifter, leader_quiet=4 * HOUR, leader_lifted=False)
        db.session.commit()

    assert lifter.client().post(
        f"/gym/shared/{pair['link']}/end", headers=JSON).status_code == 404
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['leader']) is None
        assert db.session.get(SharedSession, pair['link']) is None
    assert _order(pair['follower']) == HANDED_OVER


# --- Taking an invite back -------------------------------------------------------


def test_the_leader_takes_back_an_invite_nobody_joined(lifter, monkeypatch):
    """Open or declined: the row goes, so the same person can be asked again
    -- the key allows one per workout and invitee."""
    from features.gym import push
    from features.gym.routes import partners
    sent, locked, lock = [], [], partners.lock_user
    monkeypatch.setattr(push, 'send_push_later', lambda user_id, payload: sent.append(user_id))
    monkeypatch.setattr(partners, 'lock_user',
                        lambda user_id: (locked.append(user_id), lock(user_id))[1])
    with flask_app.app_context():
        partner, other = lifter.partner(), lifter.partner()
        leader = lifter.workout(20 * MIN)
        lifter.row(leader, lifter.exercise('bench'), 1, done=[(60, 8)], done_ago=[MIN], open_=2)
        pending = _link(lifter, leader, partner, accepted=False)
        declined = _link(lifter, leader, other, accepted=False, declined=True)
        leader_id, pending_id, declined_id = leader.id, pending.id, declined.id
        db.session.commit()

    you = lifter.client()
    for link_id in (pending_id, declined_id):
        response = you.post(f'/gym/shared/{link_id}/withdraw', headers=JSON)
        assert (response.status_code, response.get_json()) == (200, {'ok': True})
    # Under the invitee's lock, which their "Mitmachen" and "Nein" take.
    assert locked == [partner, other]
    with flask_app.app_context():
        assert db.session.get(SharedSession, pending_id) is None
        assert db.session.get(SharedSession, declined_id) is None

    them = lifter.client(partner)
    assert embedded_payload(them.get('/gym').get_data(as_text=True))['pending_invites'] == []
    confirm = them.get(f'/gym/shared/{pending_id}/confirm')
    assert confirm.status_code == 404
    assert 'zurückgezogen' in confirm.get_data(as_text=True)

    assert you.post(f'/gym/session/{leader_id}/invite',
                    data={'partner_id': partner}).status_code == 302
    assert sent == [partner]
    with flask_app.app_context():
        [again] = SharedSession.query.filter_by(leader_session_id=leader_id,
                                                follower_user_id=partner).all()
        assert (again.accepted_at, again.declined_at, again.ended_at) == (None, None, None)


def test_an_invite_somebody_joined_is_not_taken_back(lifter):
    """Somebody trains on it: the leader ends it instead (409). Nobody but
    the leader takes an invite back (404)."""
    with flask_app.app_context():
        pair = _pair(lifter)
        invited = lifter.partner()
        pending = _link(lifter, db.session.get(WorkoutSession, pair['leader']), invited,
                        accepted=False)
        pending_id = pending.id
        db.session.commit()

    assert lifter.client().post(f"/gym/shared/{pair['link']}/withdraw").status_code == 409
    for user_id in (invited, pair['partner']):
        assert lifter.client(user_id).post(f'/gym/shared/{pending_id}/withdraw').status_code == 404
    assert lifter.client().post('/gym/shared/2147483000/withdraw').status_code == 404
    with flask_app.app_context():
        assert db.session.get(SharedSession, pair['link']).ended_at is None
        assert db.session.get(SharedSession, pending_id) is not None


# --- The handover ------------------------------------------------------------------


def _end(link_id):
    with flask_app.app_context():
        link = db.session.get(SharedSession, link_id)
        sharing.end_link(link)
        db.session.commit()


def test_a_substitute_moves_with_the_original_it_replaced(lifter):
    """One slot: the hidden original goes where its substitute goes, as a
    drag moves it (_close_position_gaps)."""
    with flask_app.app_context():
        partner = lifter.partner()
        lifts = [lifter.exercise(name) for name in ('bench', 'row', 'press', 'curl')]
        leader = lifter.workout(40 * MIN)
        follower = lifter.workout(35 * MIN, user_id=partner)
        lifter.row(follower, lifts[0], 1, open_=3)
        original = lifter.row(follower, lifts[1], 2, open_=3)
        lifter.row(follower, lifts[2], 2, done=[(30, 10)], done_ago=[2 * MIN], open_=2,
                   replaces=original)
        lifter.row(follower, lifts[3], 3, open_=3)
        link_id, follower_id = _link(lifter, leader, partner, follower).id, follower.id
        db.session.commit()

    _end(link_id)
    assert _order(follower_id) == [('row', 1), ('press', 1), ('bench', 2), ('curl', 3)]


def test_the_newest_started_row_is_the_one_handed_over(lifter):
    """Two started (the follower's own screen keeps the most recent): that
    one moves to the front of the open rows, the other with the rest."""
    with flask_app.app_context():
        partner = lifter.partner()
        lifts = [lifter.exercise(name) for name in ('bench', 'row', 'press')]
        leader = lifter.workout(40 * MIN)
        follower = lifter.workout(35 * MIN, user_id=partner)
        lifter.row(follower, lifts[0], 1, open_=3)
        lifter.row(follower, lifts[1], 2, done=[(50, 8)], done_ago=[12 * MIN], open_=2)
        lifter.row(follower, lifts[2], 3, done=[(30, 10)], done_ago=[2 * MIN], open_=2)
        link_id, follower_id = _link(lifter, leader, partner, follower).id, follower.id
        db.session.commit()

    _end(link_id)
    assert _order(follower_id) == [('press', 1), ('bench', 2), ('row', 3)]


def test_nothing_moves_where_the_card_would_not(lifter):
    """Nothing started, the started row already the first open one, or a
    follower who has finished: the order stays as it is."""
    with flask_app.app_context():
        partner = lifter.partner()
        lifts = [lifter.exercise(name) for name in ('bench', 'row')]
        untouched = lifter.workout(35 * MIN, user_id=partner)
        lifter.row(untouched, lifts[0], 1, open_=3)
        lifter.row(untouched, lifts[1], 2, open_=3)
        at_the_top = lifter.workout(34 * MIN, user_id=partner)
        lifter.row(at_the_top, lifts[0], 1, done=[(40, 8)], done_ago=[2 * MIN], open_=2)
        lifter.row(at_the_top, lifts[1], 2, open_=3)
        finished = lifter.workout(33 * MIN, user_id=partner)
        lifter.row(finished, lifts[0], 1, open_=3)
        lifter.row(finished, lifts[1], 2, done=[(40, 8)], done_ago=[2 * MIN], open_=2)
        finished.finished_at = lifter.now - MIN
        links = {workout.id: _link(lifter, lifter.workout(40 * MIN), partner, workout).id
                 for workout in (untouched, at_the_top, finished)}
        db.session.commit()

    for workout_id, link_id in links.items():
        before = _order(workout_id)
        _end(link_id)
        assert _order(workout_id) == before


def test_the_handover_reseeds_what_it_moves_from_the_followers_history(lifter, monkeypatch):
    """A row that moves is planned for its new slot (reseed_for_slot, which
    leaves anything ticked, skipped or typed alone), from the follower's own
    history -- never the leader's. No structure_version bump: the follower's
    page asks for the workout again as it stops following, and a bump would
    say the leader changed the plan."""
    calls, reseed = [], sharing.reseed_for_slot
    monkeypatch.setattr(sharing, 'reseed_for_slot', lambda session_, se, old, new, user_id=None: (
        calls.append((se.exercise.name.removeprefix('pytest gym '), old, new, user_id)),
        reseed(session_, se, old, new, user_id=user_id))[1])
    with flask_app.app_context():
        pair = _pair(lifter)
        follower = db.session.get(WorkoutSession, pair['follower'])
        follower.structure_version = 7
        db.session.commit()

    _end(pair['link'])
    assert sorted(calls) == [('press', 3, 2, pair['partner']), ('row', 2, 3, pair['partner'])]
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['follower']).structure_version == 7


# --- The leader's workout ends ------------------------------------------------------


def test_the_leaders_finish_hands_the_follower_their_order(lifter, monkeypatch):
    from features.gym.routes import workout
    locked = _recording(monkeypatch, workout)
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()

    assert lifter.client().post(f"/gym/session/{pair['leader']}/finish").status_code == 302
    assert {pair['leader'], pair['follower']} in locked
    assert _ended(pair['link'])
    assert _order(pair['follower']) == HANDED_OVER


def test_an_invite_taken_back_as_the_workout_finishes_leaves_the_finish_whole(
        lifter, monkeypatch):
    """The leader's "zurückziehen" deletes an invite under the invitee's
    lock, their OK on a "no" under none: neither waits for the workout's.
    Landing between the finish's read of its links and its write, the
    finish's update of a row gone was a StaleDataError, a 500 (B11a review):
    invites nobody joined are stamped in one statement -- and the ones still
    there are stamped all the same."""
    from sqlalchemy import event, text
    from features.gym.routes import workout
    with flask_app.app_context():
        leader = lifter.workout(40 * MIN)
        lifter.row(leader, lifter.exercise('bench'), 1, done=[(60, 8)], done_ago=[MIN], open_=2)
        leader_id = leader.id
        invite_id = _link(lifter, leader, lifter.partner(), accepted=False).id
        declined_id = _link(lifter, leader, lifter.partner(), accepted=False, declined=True).id
        db.session.commit()
        engine = db.engine

    finishing, taken_back = [], []
    lock = workout.lock_sessions
    monkeypatch.setattr(workout, 'lock_sessions',
                        lambda ids: (lock(ids), finishing.append(True))[0])

    def withdraw_lands(conn, cursor, statement, parameters, context, executemany):
        # Right after the finish's first read of the links, under its lock.
        if (finishing and not taken_back and statement.lstrip().upper().startswith('SELECT')
                and 'gym_shared_sessions' in statement.split('FROM', 1)[-1][:40]):
            taken_back.append(True)
            with engine.begin() as other:
                other.execute(text('DELETE FROM gym_shared_sessions WHERE id = :id'),
                              {'id': invite_id})

    event.listen(engine, 'after_cursor_execute', withdraw_lands)
    try:
        response = lifter.client().post(f'/gym/session/{leader_id}/finish')
    finally:
        event.remove(engine, 'after_cursor_execute', withdraw_lands)
    assert taken_back
    assert response.status_code == 302
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, leader_id).finished_at is not None
    assert _ended(declined_id)


def test_a_leader_settled_for_nobody_coming_back_hands_the_follower_their_order(
        lifter, monkeypatch):
    from features.gym.routes import helpers
    locked = _recording(monkeypatch, helpers)
    with flask_app.app_context():
        pair = _pair(lifter, leader_quiet=4 * HOUR)
        db.session.commit()

    assert lifter.client().get('/gym').status_code == 200
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['leader']).auto_finished is True
    assert {pair['leader'], pair['follower']} in locked
    assert _ended(pair['link'])
    assert _order(pair['follower']) == HANDED_OVER


def test_a_leaders_discard_hands_the_follower_their_order(lifter, monkeypatch):
    """Nothing lifted, so thrown away, the link with it: the follower trains
    on alone like after a finish, on the exercise they are at."""
    from features.gym.routes import workout
    locked = _recording(monkeypatch, workout)
    with flask_app.app_context():
        pair = _pair(lifter, leader_lifted=False)
        db.session.commit()

    assert lifter.client().post(f"/gym/session/{pair['leader']}/discard").status_code == 302
    assert {pair['leader'], pair['follower']} in locked
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, pair['leader']) is None
        assert db.session.get(SharedSession, pair['link']) is None
    assert _order(pair['follower']) == HANDED_OVER
    assert _live(lifter, pair['follower'], pair['partner']) == 'press'


# --- What the page no longer carries -------------------------------------------------


def test_the_inert_partner_fields_are_gone(lifter):
    """partner_status and sync.json's `shared` were kept one deploy for pages
    open across I5's; nothing reads either since."""
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()

    detail = lifter.client().get(f"/gym/session/{pair['leader']}/detail.json").get_json()
    assert 'partner_status' not in detail
    sync = lifter.client(pair['partner']).get(
        f"/gym/session/{pair['follower']}/sync.json").get_json()
    assert set(sync) == {'version', 'partner_links'}
