"""Training partners, seen from each other's side (D14, M5; I5): the live
screen's partner lines, the partner's list behind them, "mit <Name>" on the
debrief and in Verlauf, and the declined invite the leader's line reports.

What travels is only ever shown, read-only, through routes/partner_view.py:
names, what was lifted, how many sets are still open."""
import datetime as dt

from sqlalchemy import event

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym.routes.partner_view import partner_refs
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import Exercise, SharedSession, WorkoutSession, WorkoutTemplate

MIN = dt.timedelta(minutes=1)
DAY = dt.timedelta(days=1)
JSON = {'Accept': 'application/json'}
LIVE = {**JSON, 'X-Gym-Surface': 'live', 'X-Gym-Catalogue': 'kept'}


def _link(lifter, leader_workout, follower_id, follower_workout=None, accepted=True,
          declined=False, ended=False, created_ago=30 * MIN):
    """A SharedSession as the routes leave one: accepted five minutes after
    the invite, declined or ended when asked."""
    link = SharedSession(
        leader_session_id=leader_workout.id, leader_user_id=leader_workout.user_id,
        follower_user_id=follower_id,
        follower_session_id=follower_workout.id if follower_workout is not None else None,
        created_at=lifter.now - created_ago,
        accepted_at=lifter.now - created_ago + 5 * MIN if accepted else None,
        declined_at=lifter.now - 10 * MIN if declined else None,
        ended_at=lifter.now - 2 * MIN if ended else None)
    db.session.add(link)
    db.session.flush()
    return link


def _pair(lifter, follower_rows=None, leader_rows=None):
    """A leader's running workout and a joined partner's, each with rows
    built by the callables given (workout, exercises) -> None. Returns ids."""
    partner = lifter.partner()
    lifts = [lifter.exercise(name) for name in ('bench', 'row', 'press', 'curl')]
    leader = lifter.workout(40 * MIN)
    follower = lifter.workout(35 * MIN, user_id=partner)
    (leader_rows or (lambda w, e: lifter.row(w, e[0], 1, done=[(60, 8)],
                                             done_ago=[3 * MIN], open_=2)))(leader, lifts)
    (follower_rows or (lambda w, e: lifter.row(w, e[0], 1, done=[(40, 8)],
                                               done_ago=[3 * MIN], open_=2)))(follower, lifts)
    link = _link(lifter, leader, partner, follower)
    return {'partner': partner, 'leader': leader.id, 'follower': follower.id,
            'link': link.id, 'lifts': [e.id for e in lifts]}


def _lines(lifter, workout_id, user_id=None):
    response = lifter.client(user_id).get(f'/gym/session/{workout_id}/sync.json')
    assert response.status_code == 200
    return response.get_json()['partner_links']


def _list(lifter, link_id, user_id=None):
    return lifter.client(user_id).get(f'/gym/shared/{link_id}/list.json')


# --- A declined invite -------------------------------------------------------


def test_a_declined_invite_stays_on_the_leaders_line_until_ok(lifter):
    """Declining stamps the invite instead of deleting it (D14): the leader's
    line says "hat abgelehnt" until their OK takes it away; the partner's
    Start forgets it at once, and the invite cannot be taken up any more."""
    with flask_app.app_context():
        partner = lifter.partner()
        leader = lifter.workout(20 * MIN)
        lifter.row(leader, lifter.exercise('bench'), 1, done=[(60, 8)], done_ago=[MIN], open_=2)
        link = _link(lifter, leader, partner, accepted=False)
        leader_id, link_id = leader.id, link.id
        db.session.commit()

    you = lifter.client(partner)
    assert [i['shared_id'] for i in embedded_payload(
        you.get('/gym').get_data(as_text=True))['pending_invites']] == [link_id]
    assert you.post(f'/gym/shared/{link_id}/decline').status_code == 302

    with flask_app.app_context():
        declined_at = db.session.get(SharedSession, link_id).declined_at
    assert declined_at is not None
    assert embedded_payload(you.get('/gym').get_data(as_text=True))['pending_invites'] == []
    assert you.get(f'/gym/shared/{link_id}/confirm').status_code == 404
    assert you.post(f'/gym/shared/{link_id}/accept').status_code == 404

    [line] = _lines(lifter, leader_id)
    assert (line['state'], line['since']) == ('declined', declined_at.isoformat())
    assert line['username'] == 'pytest gym partner 0'
    assert line['viewer_leads'] is True

    response = lifter.client().post(f'/gym/shared/{link_id}/dismiss', headers=JSON)
    assert response.status_code == 200
    assert _lines(lifter, leader_id) == []
    with flask_app.app_context():
        assert db.session.get(SharedSession, link_id) is None


def test_only_the_leader_clears_a_declined_invite_and_only_a_declined_one(lifter):
    with flask_app.app_context():
        partner, stranger = lifter.partner(), lifter.partner()
        leader = lifter.workout(20 * MIN)
        pending = _link(lifter, leader, partner, accepted=False)
        other = lifter.workout(20 * MIN)
        declined = _link(lifter, other, stranger, accepted=False, declined=True)
        # Declined from one phone as the other joined: both stamps.
        third, theirs = lifter.workout(20 * MIN), lifter.workout(15 * MIN, user_id=partner)
        joined = _link(lifter, third, partner, theirs, declined=True)
        pending_id, declined_id, joined_id = pending.id, declined.id, joined.id
        db.session.commit()

    assert lifter.client().post(f'/gym/shared/{pending_id}/dismiss').status_code == 404
    assert lifter.client(stranger).post(f'/gym/shared/{declined_id}/dismiss').status_code == 404
    assert lifter.client(partner).post(f'/gym/shared/{declined_id}/dismiss').status_code == 404
    # Never a link somebody trains on: 409, and the line comes back.
    assert lifter.client().post(f'/gym/shared/{joined_id}/dismiss').status_code == 409
    with flask_app.app_context():
        assert db.session.get(SharedSession, pending_id) is not None
        assert db.session.get(SharedSession, declined_id) is not None
        assert db.session.get(SharedSession, joined_id) is not None


def test_a_decline_waits_for_the_recipients_lock_as_the_accept_does(lifter, monkeypatch):
    """A "Nein" from one phone and a "Mitmachen" from the other both read the
    invite as open and stamped it twice. The decline now queues behind the
    accept's lock and finds the invite taken up (a 404) -- the lock first,
    or the read it guards is the stale one."""
    from features.gym.routes import partners
    steps, lock, read = [], partners.lock_user, partners._invite_for_recipient
    monkeypatch.setattr(partners, 'lock_user',
                        lambda user_id: (steps.append(('lock', user_id)), lock(user_id))[1])
    monkeypatch.setattr(partners, '_invite_for_recipient',
                        lambda shared_id: (steps.append(('read', shared_id)), read(shared_id))[1])
    with flask_app.app_context():
        partner = lifter.partner()
        link = _link(lifter, lifter.workout(20 * MIN), partner, accepted=False)
        link_id = link.id
        db.session.commit()

    assert lifter.client(partner).post(f'/gym/shared/{link_id}/decline').status_code == 302
    assert steps == [('lock', partner), ('read', link_id)]


def test_asking_again_after_a_no_sends_a_fresh_invite(lifter, monkeypatch):
    """The key allows one row per partner and workout: the same row is sent
    afresh -- unstamped, "seit" from now, pushed like the first time."""
    from features.gym import push
    sent = []
    monkeypatch.setattr(push, 'send_push_later', lambda user_id, payload: sent.append(user_id))
    with flask_app.app_context():
        partner = lifter.partner()
        leader = lifter.workout(20 * MIN)
        lifter.row(leader, lifter.exercise('bench'), 1, done=[(60, 8)], done_ago=[MIN], open_=2)
        link = _link(lifter, leader, partner, accepted=False, declined=True)
        leader_id, link_id, first_sent = leader.id, link.id, link.created_at
        db.session.commit()

    lifter.client().post(f'/gym/session/{leader_id}/invite', data={'partner_id': partner})

    assert sent == [partner]
    with flask_app.app_context():
        link = db.session.get(SharedSession, link_id)
        assert link.declined_at is None
        assert link.created_at > first_sent
    [line] = _lines(lifter, leader_id)
    assert line['state'] == 'invited'
    assert lifter.client(partner).get(f'/gym/shared/{link_id}/confirm').status_code == 200


# --- The lines -----------------------------------------------------------------


def test_an_invited_partner_is_waited_for_since_the_invite(lifter):
    with flask_app.app_context():
        partner = lifter.partner()
        leader = lifter.workout(40 * MIN)
        lifter.row(leader, lifter.exercise('bench'), 1, open_=3)
        link = _link(lifter, leader, partner, accepted=False, created_ago=12 * MIN)
        leader_id, created = leader.id, link.created_at
        db.session.commit()

    [line] = _lines(lifter, leader_id)
    assert line == {
        'id': line['id'], 'username': 'pytest gym partner 0', 'viewer_leads': True,
        'state': 'invited', 'since': created.isoformat(), 'finished_at': None,
        'exercise': None, 'set_no': None, 'done_in_exercise': 0, 'sets_in_exercise': 0,
        'last_set': None, 'rest_left': None, 'sets_done': 0, 'sets_total': 0, 'list_key': 0,
    }


def test_a_joined_partners_line_names_their_set_and_their_last_lift(lifter):
    """The partner's live row: its name, the set they are on, their newest
    set on it (by when it was ticked, not by its place), and their whole
    tick strip -- sets carried over from a swapped exercise included."""
    def follower_rows(workout, lifts):
        swapped = lifter.row(workout, lifts[3], 1, done=[(10, 12)], done_ago=[30 * MIN])
        lifter.row(workout, lifts[0], 2, done=[(40, 10), (42.5, 9)],
                   done_ago=[2 * MIN, 5 * MIN], open_=1, replaces=swapped)
        lifter.row(workout, lifts[1], 3, open_=3)
        lifter.row(workout, lifts[2], 4, open_=2, skipped=True)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        accepted = db.session.get(SharedSession, pair['link']).accepted_at
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    assert line['state'] == 'joined'
    assert line['since'] == accepted.isoformat()
    assert line['exercise'] == 'pytest gym bench'
    assert (line['set_no'], line['done_in_exercise'], line['sets_in_exercise']) == (3, 2, 3)
    assert line['last_set'] == {'weight': 40.0, 'reps': 10}
    assert line['rest_left'] is None
    # 1 carried + 2 on bench done; bench's open one and row's three ahead;
    # the skipped press holds nothing.
    assert (line['sets_done'], line['sets_total']) == (3, 7)


def test_a_resting_partner_shows_the_rest_left_as_an_age(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        follower = db.session.get(WorkoutSession, pair['follower'])
        # Whole seconds: the column rounds a fraction, up to a second later.
        follower.rest_ends_at = (dt.datetime.utcnow().replace(microsecond=0)
                                 + dt.timedelta(seconds=90))
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    assert 85 <= line['rest_left'] <= 90

    with flask_app.app_context():
        follower = db.session.get(WorkoutSession, pair['follower'])
        follower.rest_ends_at = dt.datetime.utcnow() - dt.timedelta(seconds=5)
        db.session.commit()
    [line] = _lines(lifter, pair['leader'])
    assert line['rest_left'] is None


def test_resting_into_the_next_exercise_shows_no_set_of_the_last_one(lifter):
    """The chip stands beside an exercise's name, so it is a set OF that
    exercise: none, while the partner walks over to the next one."""
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 10)] * 3, done_ago=[9 * MIN, 6 * MIN, MIN])
        lifter.row(workout, lifts[1], 2, open_=3)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    assert line['exercise'] == 'pytest gym row'
    assert (line['set_no'], line['done_in_exercise'], line['last_set']) == (1, 0, None)


def test_the_partners_live_row_is_the_one_their_own_screen_has(lifter):
    """A follower's started exercise stays live on their screen even with an
    earlier one open (keep_started); a leader's is the first open one. Each
    side's line shows what the OTHER's screen shows."""
    def started_second(workout, lifts):
        lifter.row(workout, lifts[0], 1, open_=3)
        lifter.row(workout, lifts[1], 2, done=[(50, 8)], done_ago=[MIN], open_=2)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=started_second, leader_rows=started_second)
        db.session.commit()

    [of_follower] = _lines(lifter, pair['leader'])
    assert of_follower['exercise'] == 'pytest gym row'
    [of_leader] = _lines(lifter, pair['follower'], pair['partner'])
    assert of_leader['viewer_leads'] is False
    assert of_leader['exercise'] == 'pytest gym bench'
    # Their list marks the same row as where they are.
    states = lambda response: [r['state'] for r in response.get_json()['rows']]  # noqa: E731
    assert states(_list(lifter, pair['link'])) == ['open', 'now']
    assert states(_list(lifter, pair['link'], pair['partner'])) == ['now', 'open']


def test_a_partner_with_every_set_done_has_no_set_to_be_on(lifter):
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 10)] * 2, done_ago=[9 * MIN, 6 * MIN])
        lifter.row(workout, lifts[1], 2, done=[(30, 12)], done_ago=[MIN])

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    assert (line['exercise'], line['set_no']) == ('pytest gym row', None)
    assert (line['done_in_exercise'], line['sets_in_exercise']) == (1, 1)
    assert (line['sets_done'], line['sets_total']) == (3, 3)


def test_a_finished_partner_counts_what_their_finish_kept(lifter):
    """After a finish the open sets are gone: "von Y" is the count the
    finish kept (planned_sets), or before B4 kept one, the sets still there."""
    with flask_app.app_context():
        pair = _pair(lifter)
        follower = db.session.get(WorkoutSession, pair['follower'])
        follower.finished_at = lifter.now - MIN
        follower.planned_sets = 21
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    assert line['state'] == 'finished'
    assert line['finished_at'] == (lifter.now - MIN).isoformat()
    assert (line['sets_done'], line['sets_total']) == (1, 21)
    assert line['exercise'] is None

    with flask_app.app_context():
        db.session.get(WorkoutSession, pair['follower']).planned_sets = None
        db.session.commit()
    [line] = _lines(lifter, pair['leader'])
    assert (line['sets_done'], line['sets_total']) == (1, 3)


def test_a_follower_sees_their_leader_and_never_the_other_follower(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        second = lifter.partner()
        theirs = lifter.workout(30 * MIN, user_id=second)
        lifter.row(theirs, lifter.exercise('squat'), 1, done=[(80, 5)], done_ago=[MIN], open_=2)
        leader = db.session.get(WorkoutSession, pair['leader'])
        other = _link(lifter, leader, second, theirs)
        other_id, theirs_id = other.id, theirs.id
        db.session.commit()

    assert [l['id'] for l in _lines(lifter, pair['leader'])] == [pair['link'], other_id]
    for workout, user, link in ((pair['follower'], pair['partner'], pair['link']),
                                (theirs_id, second, other_id)):
        [line] = _lines(lifter, workout, user)
        assert (line['id'], line['username'], line['viewer_leads']) == (
            link, 'pytest gym lifter', False)
        assert line['exercise'] == 'pytest gym bench'


def test_the_follower_sees_their_leader_finish(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        leader = db.session.get(WorkoutSession, pair['leader'])
        leader.finished_at = lifter.now - MIN
        leader.planned_sets = 3
        db.session.get(SharedSession, pair['link']).ended_at = lifter.now - MIN
        db.session.commit()

    [line] = _lines(lifter, pair['follower'], pair['partner'])
    assert (line['state'], line['viewer_leads']) == ('finished', False)
    assert (line['sets_done'], line['sets_total']) == (1, 3)


def test_a_link_that_ended_with_the_partner_still_training_has_no_line(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.get(SharedSession, pair['link']).ended_at = lifter.now - MIN
        db.session.commit()

    assert _lines(lifter, pair['leader']) == []


def test_a_link_naming_someone_elses_workout_shows_nothing_of_it(lifter):
    """The users on a link must own the sessions it names -- or a bad row
    would show a third lifter's workout to the leader."""
    with flask_app.app_context():
        pair = _pair(lifter)
        third = lifter.partner()
        db.session.get(WorkoutSession, pair['follower']).user_id = third
        db.session.commit()

    assert _lines(lifter, pair['leader']) == []
    assert _list(lifter, pair['link']).status_code == 404
    # Nor is the third lifter named as the one it was done with.
    with flask_app.app_context():
        assert partner_refs([pair['leader']]) == {}


# --- Where the lines travel ---------------------------------------------------


def test_the_page_carries_the_lines_and_a_writes_answer_leaves_them_out(lifter):
    """One source for the line: the page's payload, then sync.json. A write's
    answer leaves the lines out like the catalogue, so an older answer can
    never put back an older partner. sync.json keeps what a page from before
    I5 reads."""
    with flask_app.app_context():
        pair = _pair(lifter)
        db.session.commit()

    you = lifter.client()
    page = embedded_payload(you.get(f"/gym/session/{pair['leader']}").get_data(as_text=True))
    assert [l['id'] for l in page['partner_links']] == [pair['link']]
    detail = you.get(f"/gym/session/{pair['leader']}/detail.json").get_json()
    assert [l['id'] for l in detail['partner_links']] == [pair['link']]

    kept = you.post(f"/gym/session/{pair['leader']}/rest/skip", headers=LIVE).get_json()
    assert 'partner_links' not in kept
    assert 'exercises' not in kept
    whole = you.post(f"/gym/session/{pair['leader']}/rest/skip", headers=JSON).get_json()
    assert [l['id'] for l in whole['partner_links']] == [pair['link']]

    sync = you.get(f"/gym/session/{pair['leader']}/sync.json").get_json()
    assert set(sync) == {'version', 'shared', 'partner_links'}
    assert [l['id'] for l in sync['partner_links']] == [pair['link']]
    assert sync['shared'] is True


# --- The list ------------------------------------------------------------------


def test_the_list_shows_what_the_partner_lifted_and_how_many_are_open(lifter):
    """Each row: what was lifted, how many sets are still open -- never what
    the open ones are planned at, and nothing else of theirs (Michi)."""
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 10), (40, 9)], done_ago=[9 * MIN, 6 * MIN])
        now = lifter.row(workout, lifts[1], 2, done=[(30, 12)], done_ago=[MIN], open_=2)
        now.notes = 'pytest secret note'
        now.pain = True
        lifter.row(workout, lifts[2], 3, open_=3)
        lifter.row(workout, lifts[3], 4, done=[(12, 15)], done_ago=[20 * MIN], open_=1,
                   skipped=True)
        lifter.row(workout, lifter.exercise('squat'), 5, skipped=True)
        workout.notes = 'pytest secret workout note'
        workout.bodyweight_kg = 81.3

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        accepted = db.session.get(SharedSession, pair['link']).accepted_at
        started = db.session.get(WorkoutSession, pair['follower']).started_at
        db.session.commit()

    response = _list(lifter, pair['link'])
    assert response.status_code == 200
    body = response.get_json()
    text = response.get_data(as_text=True)
    assert 'secret' not in text and '81.3' not in text
    assert set(body) == {'id', 'username', 'viewer_leads', 'link_live', 'since', 'started_at',
                         'finished_at', 'sets_done', 'sets_total', 'rest_left', 'rows'}
    assert (body['username'], body['viewer_leads'], body['link_live']) == (
        'pytest gym partner 0', True, True)
    assert (body['since'], body['started_at']) == (accepted.isoformat(), started.isoformat())
    assert (body['sets_done'], body['sets_total']) == (4, 9)
    rows = [(r['name'], r['state'], r['sets'], r['done'], r['open'], r['set_no'])
            for r in body['rows']]
    assert rows == [
        ('pytest gym bench', 'done',
         [{'weight': 40.0, 'reps': 10}, {'weight': 40.0, 'reps': 9}], 2, 0, None),
        ('pytest gym row', 'now', [{'weight': 30.0, 'reps': 12}], 1, 2, 2),
        ('pytest gym press', 'open', [], 0, 3, None),
        # Skipped after a set: what it got stays said, as in their own queue.
        ('pytest gym curl', 'skipped', [{'weight': 12.0, 'reps': 15}], 1, 0, None),
        ('pytest gym squat', 'skipped', [], 0, 0, None),
    ]
    assert all(set(r) == {'id', 'name', 'picture', 'state', 'sets', 'done', 'open', 'set_no'}
               for r in body['rows'])


def test_the_lists_now_row_is_on_the_set_the_line_names(lifter):
    """A tick without reps keeps its place in the row: after one lifted set
    and one such tick the partner is on set 3 of 4, in the line and in the
    list alike, and the row counts "2/4" as their own queue does -- the list
    once said "jetzt Satz 2", then "Satz 3" beside "1/3"."""
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 8)], done_ago=[3 * MIN], ticked_empty=1,
                   open_=2)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        db.session.commit()

    [line] = _lines(lifter, pair['leader'])
    [row] = _list(lifter, pair['link']).get_json()['rows']
    assert (line['set_no'], line['sets_in_exercise']) == (3, 4)
    assert (row['state'], row['set_no'], row['done'], row['open'], len(row['sets'])) == (
        'now', 3, 2, 2, 1)


def test_the_lines_key_moves_whenever_the_list_would(lifter):
    """An open sheet asks for the list again when the line's key moves: for a
    swap further down, or a lift corrected -- not only when the live row
    does -- and never for a planned weight, which the list does not show."""
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 8)], done_ago=[3 * MIN], open_=2)
        lifter.row(workout, lifts[1], 2, open_=3)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        db.session.commit()

    def key_after(edit):
        with flask_app.app_context():
            edit(db.session.get(WorkoutSession, pair['follower']).exercises)
            db.session.commit()
        [line] = _lines(lifter, pair['leader'])
        return line['list_key']

    first = key_after(lambda rows: None)
    assert key_after(lambda rows: setattr(rows[1].sets[0], 'weight', 55.0)) == first
    swapped = key_after(lambda rows: setattr(rows[1], 'exercise_id', pair['lifts'][2]))
    corrected = key_after(lambda rows: setattr(rows[0].sets[0], 'weight', 42.5))
    assert len({first, swapped, corrected}) == 3


def test_only_the_two_parties_read_the_list(lifter):
    with flask_app.app_context():
        pair = _pair(lifter)
        second, stranger = lifter.partner(), lifter.partner()
        theirs = lifter.workout(30 * MIN, user_id=second)
        leader = db.session.get(WorkoutSession, pair['leader'])
        _link(lifter, leader, second, theirs)
        db.session.commit()

    assert _list(lifter, pair['link'], stranger).status_code == 404
    assert _list(lifter, pair['link'], second).status_code == 404
    mine = _list(lifter, pair['link'], pair['partner']).get_json()
    assert (mine['username'], mine['viewer_leads']) == ('pytest gym lifter', False)
    assert [r['sets'] for r in mine['rows']] == [[{'weight': 60.0, 'reps': 8}]]


def test_an_unanswered_or_declined_invite_has_no_list(lifter):
    with flask_app.app_context():
        partner = lifter.partner()
        leader = lifter.workout(20 * MIN)
        pending = _link(lifter, leader, partner, accepted=False)
        other = lifter.workout(20 * MIN)
        declined = _link(lifter, other, partner, accepted=False, declined=True)
        ids = (pending.id, declined.id)
        db.session.commit()

    for link_id in ids:
        assert _list(lifter, link_id).status_code == 404
        assert _list(lifter, link_id, partner).status_code == 404


def test_the_list_runs_to_the_partners_own_finish(lifter):
    """Past the link's end (Michi): the leader finished first, the partner
    trained on alone, and the leader's debrief still shows all of it."""
    with flask_app.app_context():
        pair = _pair(lifter)
        leader = db.session.get(WorkoutSession, pair['leader'])
        leader.finished_at = lifter.now - 10 * MIN
        db.session.get(SharedSession, pair['link']).ended_at = lifter.now - 10 * MIN
        follower = db.session.get(WorkoutSession, pair['follower'])
        lifter.row(follower, db.session.get(Exercise, pair['lifts'][1]), 2,
                   done=[(35, 10)], done_ago=[2 * MIN], open_=1)
        db.session.commit()

    body = _list(lifter, pair['link']).get_json()
    assert body['link_live'] is False
    assert body['finished_at'] is None
    assert [r['sets'] for r in body['rows']] == [[{'weight': 40.0, 'reps': 8}],
                                                 [{'weight': 35.0, 'reps': 10}]]


def test_a_finished_list_reads_a_row_nothing_was_lifted_on_as_not_done(lifter):
    """A finish takes the open sets (D5): what stays is what was lifted, and
    a row without any was not done, not "0/0"."""
    def follower_rows(workout, lifts):
        lifter.row(workout, lifts[0], 1, done=[(40, 10)], done_ago=[9 * MIN])
        lifter.row(workout, lifts[1], 2)

    with flask_app.app_context():
        pair = _pair(lifter, follower_rows=follower_rows)
        follower = db.session.get(WorkoutSession, pair['follower'])
        follower.finished_at = lifter.now - MIN
        follower.planned_sets = 4
        db.session.commit()

    body = _list(lifter, pair['link']).get_json()
    assert body['finished_at'] == (lifter.now - MIN).isoformat()
    assert body['rest_left'] is None
    assert (body['sets_done'], body['sets_total']) == (1, 4)
    assert [(r['state'], r['done'], r['open']) for r in body['rows']] == [
        ('done', 1, 0), ('skipped', 0, 0)]


# --- "mit <Name>" -------------------------------------------------------------


def test_the_debrief_names_a_partner_who_joined_and_lifted(lifter):
    """Michi: "mit <Name>" only for a partner who joined and logged a set --
    not for an invite nobody took, nor for one who ticked sets without reps."""
    with flask_app.app_context():
        lifted, idle, invited = lifter.partner(), lifter.partner(), lifter.partner()
        mine = lifter.workout(DAY, finished=True)
        lifter.row(mine, lifter.exercise('bench'), 1, done=[(60, 8)])
        theirs = lifter.workout(DAY, user_id=lifted, finished=True)
        lifter.row(theirs, lifter.exercise('row'), 1, done=[(40, 8)])
        empty = lifter.workout(DAY, user_id=idle, finished=True)
        lifter.row(empty, lifter.exercise('press'), 1, ticked_empty=2)
        link = _link(lifter, mine, lifted, theirs, ended=True)
        _link(lifter, mine, idle, empty, ended=True)
        _link(lifter, mine, invited, accepted=False, ended=True)
        mine_id, theirs_id, link_id = mine.id, theirs.id, link.id
        db.session.commit()

    page = embedded_payload(lifter.client().get(f'/gym/session/{mine_id}').get_data(as_text=True))
    assert page['partners'] == [{'id': link_id, 'username': 'pytest gym partner 0'}]
    theirs_page = embedded_payload(
        lifter.client(lifted).get(f'/gym/session/{theirs_id}').get_data(as_text=True))
    assert theirs_page['partners'] == [{'id': link_id, 'username': 'pytest gym lifter'}]


def test_a_workout_that_followed_offers_no_routine_update(lifter):
    """Its order was the leader's (Michi): offering to write it into the
    follower's own routine is gone. The leader's own debrief keeps it."""
    with flask_app.app_context():
        partner = lifter.partner()
        bench, row = lifter.exercise('bench'), lifter.exercise('row')
        routine = lifter.routine('partner', [bench, row], user_id=partner)
        mine_routine = lifter.routine('mine', [bench, row])
        mine = lifter.workout(DAY, template=mine_routine, finished=True)
        lifter.row(mine, row, 1, done=[(60, 8)])
        lifter.row(mine, bench, 2, done=[(60, 8)])
        theirs = lifter.workout(DAY, user_id=partner, template=routine, finished=True)
        lifter.row(theirs, row, 1, done=[(40, 8)])
        lifter.row(theirs, bench, 2, done=[(40, 8)])
        _link(lifter, mine, partner, theirs, ended=True)
        mine_id, theirs_id = mine.id, theirs.id
        ids = {'theirs': routine.id, 'mine': mine_routine.id, 'bench': bench.id, 'row': row.id}
        db.session.commit()

    followed = embedded_payload(
        lifter.client(partner).get(f'/gym/session/{theirs_id}').get_data(as_text=True))
    assert (followed['template_exercises'], followed['template_next_exercises']) == (None, None)
    led = embedded_payload(lifter.client().get(f'/gym/session/{mine_id}').get_data(as_text=True))
    assert led['template_next_exercises'] == ['pytest gym row', 'pytest gym bench']

    # ...nor takes one from a debrief still showing the offer.
    def order(template_id):
        with flask_app.app_context():
            return [te.exercise_id for te in db.session.get(WorkoutTemplate, template_id).exercises]
    for user_id, workout_id in ((partner, theirs_id), (None, mine_id)):
        response = lifter.client(user_id).post(f'/gym/session/{workout_id}/update_template')
        assert response.status_code == 302
    assert order(ids['theirs']) == [ids['bench'], ids['row']]
    assert order(ids['mine']) == [ids['row'], ids['bench']]


def _queries(call):
    seen = []

    def count(*_args):
        seen.append(1)

    with flask_app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', count)
    try:
        response = call()
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    assert response.status_code == 200
    return response, len(seen)


def test_verlauf_names_each_workouts_partners_in_a_fixed_number_of_queries(lifter):
    def partnered(days):
        with flask_app.app_context():
            partner = lifter.partner()
            mine = lifter.workout(days * DAY, finished=True)
            lifter.row(mine, lifter.exercise(f'lift {days}'), 1, done=[(60, 8)])
            theirs = lifter.workout(days * DAY, user_id=partner, finished=True)
            lifter.row(theirs, lifter.exercise(f'their lift {days}'), 1, done=[(40, 8)])
            link = _link(lifter, mine, partner, theirs, ended=True)
            ids = (mine.id, link.id, partner)
            db.session.commit()
            return ids

    with flask_app.app_context():
        alone = lifter.workout(9 * DAY, finished=True)
        lifter.row(alone, lifter.exercise('alone'), 1, done=[(50, 8)])
        alone_id = alone.id
        db.session.commit()
    first = partnered(8)

    def verlauf():
        return lifter.client().get('/gym/verlauf')

    _response, few = _queries(verlauf)
    more = [partnered(days) for days in (7, 6, 5)]
    response, many = _queries(verlauf)
    assert many == few

    body = embedded_payload(response.get_data(as_text=True))
    by_id = {e['session_id']: e['partners'] for m in body['months'] for e in m['entries']}
    assert by_id[alone_id] == []
    for mine, link, partner in [first, *more]:
        name = f'pytest gym partner {lifter.partner_ids.index(partner)}'
        assert by_id[mine] == [{'id': link, 'username': name}]
