"""Shared constants, request-value coercion, and the gym nav context.

Every coercion here answers the same question: what does this value mean when
the input is missing, blank, or not a number. They arrive from form posts and
query strings, so none of them may raise anything but InvalidInput -- the
typed-field parsers raise it for a value a lifter typed that cannot be stored,
and the blueprint answers it with the reason (routes/__init__.py).

This is a leaf module -- it imports no other routes module, which is what lets
every other one import it. _cancel_pending_push lives here rather than with the
workout routes for exactly that reason: _get_active_session calls it, and
leaving it in workout.py would make helpers and workout import each other.

Moved verbatim from the pre-split routes.py.
"""
import datetime as dt
import math

from flask import (
    flash, has_request_context, jsonify, redirect, request, session as flask_session, url_for,
)

from auth import wants_json
from extensions import db
from models import (
    AppUser, WorkoutSession, PendingPush, SessionExercise, SessionSet, SharedSession,
    STALE_SESSION_TIMEOUT,
)
from features.gym import stats
from features.gym.exercises import (
    REST_MAX_SECONDS, REST_MIN_SECONDS, list_values, settle_rests,
)
from features.gym.locking import lock_sessions
from features.gym.scope import LIVE_SURFACE_HEADER, my_sessions
from .. import sharing
from ._blueprint import gym_bp


# The UI is German regardless of the server's locale, so month names are stated
# rather than taken from strftime('%B') -- which follows LC_TIME and would give
# English on this machine and German on the VPS, or vice versa.
# analytics.py speaks in keys and indexes, not in UI language: dayparts come
# back as 'morning'/'evening' and weekdays as 0-6. Naming them is presentation,
# so it happens here rather than in the analysis.
DAYPART_NAMES = {'morning': 'Vormittags', 'evening': 'Abends'}
WEEKDAY_NAMES = ('Montag', 'Dienstag', 'Mittwoch', 'Donnerstag',
                 'Freitag', 'Samstag', 'Sonntag')

MONTH_NAMES = (
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
)

# stats.exercise_state()'s return value -> (chip CSS modifier, display label),
# spec 5.6's table. A state of None means "no chip" and has no entry here --
# callers must check before indexing.
EXERCISE_STATE_CHIP = {
    'neu': ('neu', 'Neu'),
    'rekord': ('record', 'Rekord'),
    'stagniert': ('stall', 'Stagniert'),
    'steigend': ('up', 'Steigend'),
}


def _to_float(value, fallback=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_increment(value):
    """A weight increment as typed: None for a blank, else a number above 0
    and at most MAX_INCREMENT_KG. InvalidInput for anything else.

    Comma-tolerant: `type=number` normalises to a dot, but the field degrades
    to text without JS and a German keyboard produces `2,5`. A blank stores
    NULL, which stats.resolve_increment() reads as "use the default" -- so
    clearing the field is the way to put an exercise back on 2.5 kg. An
    unparseable or non-positive value used to do the same, silently; 'inf'
    got through to the database and came back as a 500.
    """
    raw, parsed = _typed_number(value, _to_float)
    if not raw:
        return None
    if parsed is None or not 0 < parsed <= MAX_INCREMENT_KG:
        raise InvalidInput(f'Gewichtsstufe: bitte mehr als 0 und höchstens {MAX_INCREMENT_KG} kg.')
    return parsed


def _to_bar_weight(value):
    """A bar's own weight: None for a blank (the list's value), else 0 to
    MAX_BAR_KG -- 0 is "nothing inside the number". InvalidInput otherwise."""
    raw, parsed = _typed_number(value, _to_float)
    if not raw:
        return None
    if parsed is None or not 0 <= parsed <= MAX_BAR_KG:
        raise InvalidInput(f'Stangengewicht: bitte 0 bis {MAX_BAR_KG} kg.')
    return parsed


def _to_int(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


class InvalidInput(Exception):
    """A typed value the server will not store, and the sentence that says why.

    These used to be dropped with a 200 -- the old number stayed and the screen
    snapped back without a word (G-070, G-071, G-092) -- or, for a name longer
    than its column, to reach the database and come back as a 500 that the
    island called a connection failure (G-083). The blueprint's handler
    (routes/__init__.py) answers an island with a 400 carrying the message,
    which api.ts shows as it is, and a form post with the message flashed on
    the page it came from.
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


# The largest numbers a set can carry. A bound on what someone can mean when
# they type it, not a judgement on anyone's lifting: the heaviest real sled
# loads fit well inside it, a fat-fingered 9999 does not -- and a stored 9999
# stays the record, the next workout's seed and most of the tonnage. Mirrored
# in static/gym/src/setInput.ts.
MAX_SET_WEIGHT_KG = 1000
MAX_SET_REPS = 1000
BODYWEIGHT_RANGE_KG = (20, 400)
# A bar or a weight step past these is a typo, not equipment.
MAX_BAR_KG = 100
MAX_INCREMENT_KG = 50
MAX_STACK_STOPS = 100
# Names are VARCHAR(150). Notes are TEXT: 65,535 *bytes*, fewer characters
# once umlauts and emoji take two to four bytes each.
MAX_NAME_CHARS = 150
MAX_NOTE_CHARS = 2000


def _typed_number(value, parse):
    """(raw text, number or None) for a typed field. The raw text is '' for a
    blank; the number is None when the text is not a finite number."""
    raw = str(value if value is not None else '').replace(',', '.').strip()
    if not raw:
        return raw, None
    parsed = parse(raw)
    if parsed is not None and not math.isfinite(parsed):
        parsed = None
    return raw, parsed


def _to_weight(value):
    """A set's weight as typed: None for a blank -- not an edit, like a field
    the form never sent -- else a number of 0 to MAX_SET_WEIGHT_KG.
    InvalidInput for anything else.

    Stricter than _to_float on purpose: float() also accepts 'nan' and 'inf',
    and exponent notation made 1e9 kg a stored set. Zero stays valid -- a
    bodyweight set is logged at 0 kg. Comma-tolerant for the same reason as
    _to_increment.
    """
    raw, parsed = _typed_number(value, _to_float)
    if not raw:
        return None
    if parsed is None or not 0 <= parsed <= MAX_SET_WEIGHT_KG:
        raise InvalidInput(f'Gewicht: bitte 0 bis {MAX_SET_WEIGHT_KG} kg.')
    return parsed


def _to_reps(value):
    """A set's rep count: None for a blank, else a whole number of 1 to
    MAX_SET_REPS. InvalidInput for anything else -- a set of zero reps is not
    a set, and 2.5 of them is not a count."""
    raw = str(value if value is not None else '').strip()
    if not raw:
        return None
    parsed = _to_int(raw)
    if parsed is None or not 1 <= parsed <= MAX_SET_REPS:
        raise InvalidInput(f'Wiederholungen: bitte eine ganze Zahl von 1 bis {MAX_SET_REPS}.')
    return parsed


def _to_bodyweight(value):
    """A workout's bodyweight: None for a blank (the field was cleared), else
    a number within BODYWEIGHT_RANGE_KG. InvalidInput for anything else, so a
    typo no longer erases the weight that was stored (G-071)."""
    raw, parsed = _typed_number(value, _to_float)
    if not raw:
        return None
    low, high = BODYWEIGHT_RANGE_KG
    if parsed is None or not low <= parsed <= high:
        raise InvalidInput(f'Körpergewicht: bitte {low} bis {high} kg.')
    return parsed


def _to_rest_seconds(value):
    """A rest as typed: None for a blank, else whole seconds within the
    stepper's ends. InvalidInput for anything else. One check for every rest
    a lifter can set -- two of the three routes stored any number, a negative
    one included, which scheduled the "rest over" push in the past (G-092)."""
    raw = str(value if value is not None else '').strip()
    if not raw:
        return None
    seconds = _to_int(raw)
    if seconds is None or not REST_MIN_SECONDS <= seconds <= REST_MAX_SECONDS:
        raise InvalidInput(
            f'Pause: bitte {_clock(REST_MIN_SECONDS)} bis {_clock(REST_MAX_SECONDS)} min.')
    return seconds


def _clock(seconds):
    return f'{seconds // 60}:{seconds % 60:02d}'


def _to_name(value):
    """A routine's or workout's name as typed, stripped; '' for a blank.
    InvalidInput past the column's length."""
    name = (value or '').strip()
    if len(name) > MAX_NAME_CHARS:
        raise InvalidInput(f'Name zu lang — höchstens {MAX_NAME_CHARS} Zeichen.')
    return name


def _to_note(value):
    """A note as typed, stripped; None for a blank. InvalidInput past
    MAX_NOTE_CHARS."""
    note = (value or '').strip()
    if len(note) > MAX_NOTE_CHARS:
        raise InvalidInput(f'Notiz zu lang — höchstens {MAX_NOTE_CHARS} Zeichen.')
    return note or None


# The phone's name for a set it adds (SessionSet.client_key): a uuid from
# the live screen's outbox, never text a lifter typed.
MAX_CLIENT_KEY_CHARS = 36
_CLIENT_KEY_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-')


def _to_client_key(value):
    """An added set's key, or None when the request has none (the debrief, a
    page from before the outbox). InvalidInput for anything else that is not
    one: no screen sends it, so it is a bug to hear about, not a key to
    store."""
    if not value:
        return None
    if len(value) > MAX_CLIENT_KEY_CHARS or not set(value) <= _CLIENT_KEY_CHARS:
        raise InvalidInput('Der Satz kam mit einem ungültigen Schlüssel.')
    return value


# The live screen's outbox (static/gym/src/session/outbox.ts) holds what the
# lifter logs while the phone is offline and sends it when it can -- minutes
# or a day later. Each write says how long ago the lifter made it, in
# milliseconds, and "now" would be the wrong time for all of them (B6, D6-A).
WRITE_AGE_HEADER = 'X-Gym-Write-Age'
# While the outbox holds writes for a workout, the page names it in this
# cookie with the time of the oldest: "<session id>:<epoch ms>".
OUTBOX_COOKIE = 'gym_outbox'
# The cookie's own Max-Age, held here too: the cookie is the phone's to set.
OUTBOX_HOLD_LIMIT = dt.timedelta(days=7)


def _from_millis(raw):
    """Naive UTC from epoch milliseconds as the phone sends them, or None
    for anything that is not a number of them."""
    try:
        return dt.datetime.fromtimestamp(int(raw) / 1000, dt.timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _write_time(session_):
    """When the lifter made this write, or None when the request does not
    say.

    The phone says how long ago, not when: its clock can be minutes off, and
    a set stamped by it read as lifted that much early -- a rest still
    running counted as over, and its push never came (B6 review). An age is
    the same on any clock. A set stamped with its arrival instead read as
    lifted hours late, its rest ran from then, and a push buzzed for a rest
    that had ended long before.

    Held to what is possible: never before the workout began, never after
    now."""
    try:
        age = dt.timedelta(milliseconds=max(int(request.headers.get(WRITE_AGE_HEADER)), 0))
    except (TypeError, ValueError, OverflowError):
        return None
    now = dt.datetime.utcnow()
    try:
        moment = now - age
    except OverflowError:
        moment = session_.started_at
    return min(max(moment, session_.started_at), now)


def _outbox_hold(session_):
    """The time of the oldest write the caller's phone still holds for this
    workout (OUTBOX_COOKIE), or None.

    Held to the workout and to now like a write's own time. It can only
    postpone the three-hour rule, and only for the caller's own workout --
    every caller has checked ownership first -- and for a week at most."""
    if not has_request_context():
        return None
    named, _, millis = request.cookies.get(OUTBOX_COOKIE, '').partition(':')
    if named != str(session_.id):
        return None
    moment = _from_millis(millis)
    now = dt.datetime.utcnow()
    if moment is None or now - moment > OUTBOX_HOLD_LIMIT:
        return None
    return min(max(moment, session_.started_at), now)


# LIVE_SURFACE_HEADER (scope.py) is sent by the live workout island on every
# write. The debrief writes to the same set routes on purpose -- a finished
# workout is corrected there -- so finished_at alone cannot tell the two
# apart; the surface that asked can.


def _refuse_live_write_if_finished(session_):
    """409 for a live-screen write to a workout that has already finished,
    else None.

    The live screen outlives the workout: the back button restores it, and a
    second phone never saw the finish. Its "Satz geschafft" used to land in
    the finished workout, queue a rest push for it, and hand the island a
    debrief payload it could not render. The island answers a 409 by
    reloading, which shows the debrief.
    """
    if request.headers.get(LIVE_SURFACE_HEADER) != 'live':
        return None
    # A screen left open overnight writes into a workout nobody came back
    # to: it ends at its last set first, and the screen reloads into that
    # (B4 review) -- instead of today's set landing in yesterday's workout.
    # Judged at the moment the lifter made the write: one the phone held
    # while offline was made while the workout ran (B6).
    session_id = session_.id
    if _settle_if_abandoned(session_, as_of=_write_time(session_)) == 'live':
        return None
    return _finished_refusal(session_id)


def _refuse_structure_edit_if_finished(session_):
    """409 for a change to a finished workout's shape, else None -- whoever
    asks.

    A finished workout is corrected from the debrief: set values, ticks,
    notes, bodyweight and the deload mark (_refuse_live_write_if_finished
    guards those). Adding, replacing, skipping, removing or reordering
    exercises, their rests and the rest skip have no place there, and used to
    go through for any caller that left out the live screen's header -- a
    "replace" hid two logged sets from the debrief while the stats still
    counted them (G-090). The header no longer decides whether; the live
    island still answers the 409 by reloading into the debrief.
    """
    session_id = session_.id
    if _settle_if_abandoned(session_, as_of=_write_time(session_)) == 'live':
        return None
    return _finished_refusal(session_id)


def _finished_refusal(session_id):
    """By id: the workout may have been discarded on the way here."""
    if _wants_json():
        return jsonify({'finished': True}), 409
    return redirect(url_for('gym.session_detail', session_id=session_id))


def _delete_session_and_links(session_, commit=True):
    """Delete a workout together with every partner link it took part in.

    Plain FKs with no ondelete point at the session from both halves of a
    link, with no ORM cascade either -- so the link rows have to go first.
    The resting-set pointer is cleared before the cascade deletes the set it
    names. Commits, unless `commit=False`: a caller holding lock_user, which
    a commit lets go of, commits once it is done (the join).
    """
    session_.resting_set_id = None
    # Flushed, not committed: a commit would let go of the lock a caller
    # holds (_settle_if_abandoned) with the workout still half there.
    db.session.flush()
    doomed_link_ids = [row.id for row in SharedSession.query.filter(
        db.or_(SharedSession.leader_session_id == session_.id,
               SharedSession.follower_session_id == session_.id)).all()]
    if doomed_link_ids:
        SharedSession.query.filter(SharedSession.id.in_(doomed_link_ids)).delete(
            synchronize_session=False)
    db.session.delete(session_)
    if commit:
        db.session.commit()
    else:
        db.session.flush()


def _discard_session(session_, commit=True):
    """Throw away a running workout of the caller's (_delete_session_and_links)
    and remember it (DISCARDED_SESSION_KEY): a screen of theirs still showing
    it goes home, not to a 404."""
    session_id = session_.id
    _delete_session_and_links(session_, commit=commit)
    flask_session[DISCARDED_SESSION_KEY] = session_id


def _to_stack_steps(raw):
    """The real stops of an uneven stack, typed as a list.

    Separators are comma or semicolon; a decimal point is a dot (e.g.
    "5, 13, 21, 29" or "5.5; 13.2"), not a German-locale comma decimal --
    stack pins are whole kilograms in practice, so that's a documented
    limitation rather than a case this needs to support. Sorted ascending,
    deduped, junk dropped. Empty means None rather than [] -- an empty list
    would read as "this machine has no positions", and the column's whole
    meaning is "NULL: steps evenly, ask weight_increment instead".
    """
    steps = []
    for chunk in (raw or '').replace(';', ',').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = float(chunk)
        except ValueError:
            continue
        # 'inf' parses, and reached the database as a stop.
        if math.isfinite(value) and 0 < value <= MAX_SET_WEIGHT_KG:
            steps.append(value)
    steps = sorted(set(steps))
    if len(steps) > MAX_STACK_STOPS:
        raise InvalidInput(f'Höchstens {MAX_STACK_STOPS} Stufen.')
    return steps or None


def _exercise_meta(exercise, setup):
    """An exercise as one lifter sees it (schemas.ExerciseMeta): the list's
    facts, that lifter's effective settings (`setup`), and the list's own
    values, which a blank field in the settings form falls back to. `own`
    names the settings that are the lifter's own value -- for the rest an
    exception to `rest_for_all`, where they set one."""
    return {
        'id': exercise.id,
        'name': exercise.name,
        'muscle_group': exercise.muscle_group,
        'is_unilateral': exercise.is_unilateral,
        'default_rest_seconds': setup.default_rest_seconds,
        'weight_increment': setup.weight_increment,
        'equipment': exercise.equipment,
        'bar_weight': setup.bar_weight,
        'stack_kg': setup.stack_kg,
        'secondary_muscle_groups': exercise.secondary_muscle_groups,
        'list_defaults': list_values(exercise),
        'own': sorted(setup.changed),
        'rest_for_all': setup.rest_for_all,
    }


def _counted(session_):
    """The workout's sets that count (Q1), on every row -- a set lifted
    before its exercise was skipped or replaced was lifted all the same."""
    return [s for se in session_.exercises for s in se.sets
            if stats.set_counts(s.completed, s.reps)]


def planned_set_count(session_):
    """How many sets the workout holds: every set that counts, plus the open
    ones still ahead -- the "von Y" of the finish sheet, by the same rule as
    the live tally (workout._live_data). Open sets of a skipped row are not
    ahead, and neither are a replaced original's: its slot is the
    substitute's now. A ticked set without reps is neither (G-038)."""
    replaced = {se.replaces_id for se in session_.exercises if se.replaces_id is not None}
    ahead = sum(1 for se in session_.exercises
                if not se.skipped and se.id not in replaced
                for s in se.sets if not s.completed)
    return len(_counted(session_)) + ahead


def _finish_session(session_, finished_at, auto=False):
    """End a running workout: the one way it happens, whether the lifter
    taps "Beenden" or the app gives up on it (_settle_if_abandoned). Does not
    commit.

    What was never lifted goes (D5, G-080): open sets used to stay behind,
    invisible everywhere but the export. Their number is kept first, as
    planned_sets -- the debrief's comparison leaves cut-short workouts out
    (D10) and could not tell one otherwise. Whoever finishes first ends the
    sharing; the other trains on alone.
    """
    session_.planned_sets = planned_set_count(session_)
    session_.finished_at = finished_at
    session_.auto_finished = auto
    session_.rest_ends_at = None
    # Before the sets go: the pointer is a foreign key to one of them.
    session_.resting_set_id = None
    settle_rests(session_)
    _cancel_pending_push(session_)
    for se in session_.exercises:
        for s in [s for s in se.sets if not stats.set_counts(s.completed, s.reps)]:
            se.sets.remove(s)
    sharing.end_links_for(session_)


def _last_set_at(session_):
    """When the last set that counts (Q1) was ticked, or None when none
    carries a stamp. One query: every gym page asks it (_is_abandoned), and
    walking the workout's rows cost one per exercise (B4 re-review)."""
    return (db.session.query(db.func.max(SessionSet.completed_at))
            .join(SessionExercise, SessionSet.session_exercise_id == SessionExercise.id)
            .filter(SessionExercise.session_id == session_.id,
                    SessionSet.completed == True,  # noqa: E712
                    SessionSet.reps >= 1)
            .scalar())


# The last running workout of the lifter's that was thrown away
# (_discard_session), kept in their own signed cookie.
DISCARDED_SESSION_KEY = 'gym_discarded_session'


def _is_abandoned(session_, as_of=None):
    """Left alone for STALE_SESSION_TIMEOUT by `as_of` (default now):
    counted from its last set, or from its start while it has none."""
    moment = as_of or dt.datetime.utcnow()
    return moment - (_last_set_at(session_) or session_.started_at) > STALE_SESSION_TIMEOUT


def _abandon_clock(session_, as_of=None):
    """The moment the three-hour rule is judged at: now, or earlier when the
    phone says the lifter acted earlier (B6, D6-A) -- a write by its own
    time (`as_of`, _write_time), and anything by the oldest write the phone
    still holds for this workout (_outbox_hold).

    Offline to the end of a workout, the app closed, opened again the next
    day: the page load ended the workout at its last set that had reached
    the server -- or threw it away when none had -- before the phone could
    send the rest, and each of them was refused. The hold postpones only
    that; once the phone has sent everything, the rule applies as ever."""
    moments = [dt.datetime.utcnow()]
    if as_of is not None:
        moments.append(as_of)
    hold = _outbox_hold(session_)
    if hold is not None:
        moments.append(hold)
    return min(moments)


def _settle_if_abandoned(session_, as_of=None):
    """End a running workout nobody came back to, and say what it is now:
    'live', 'finished' or 'discarded'. `as_of`: when the write asking was
    made (_abandon_clock).

    Abandoned (_is_abandoned), it is finished at its last set and marked
    auto_finished, or discarded when nothing in it counts (D5, G-086,
    G-124). It used to be finished at start + 3 h, a set logged a minute
    earlier notwithstanding, and filed as a 180-minute workout, empty ones
    included.

    Under the session lock and re-read, like a finish: two requests noticing
    the same workout at once -- a page and its prefetch, two phones -- both
    deleted it (a 500 for the second), and a tick racing the finish could
    lose its set to the finish's delete (B4 review). Like lock_sessions this
    ends the caller's transaction when there is something to settle: ask it
    before changing anything, and never while holding lock_user -- its
    commit releases that lock.
    """
    if session_.finished_at is not None:
        return 'finished'
    clock = _abandon_clock(session_, as_of)
    if not _is_abandoned(session_, clock):
        return 'live'
    session_id = session_.id
    lock_sessions([session_id])
    session_ = db.session.get(WorkoutSession, session_id)
    if session_ is None:
        # Another request settled it first -- this one goes home as well.
        flask_session[DISCARDED_SESSION_KEY] = session_id
        return 'discarded'
    if session_.finished_at is not None:
        return 'finished'
    if not _is_abandoned(session_, clock):
        return 'live'
    if not _counted(session_):
        _discard_session(session_)
        # Whichever request noticed it, the next page says why it is gone.
        flash('Das leere Workout wurde nach 3 Stunden ohne Satz verworfen.', 'error')
        return 'discarded'
    # Sets from before completed_at existed carry no stamp: the old cap is
    # the only end there is to give them.
    _finish_session(session_, _last_set_at(session_) or session_.started_at + STALE_SESSION_TIMEOUT,
                    auto=True)
    db.session.commit()
    return 'finished'


def _was_discarded(session_id):
    """Whether this is the lifter's running workout that was thrown away
    (_discard_session) -- which a screen of theirs may still be showing."""
    return (flask_session.get(DISCARDED_SESSION_KEY) == session_id
            and db.session.get(WorkoutSession, session_id) is None)


def _get_active_session():
    """The one in-progress workout, if any -- once an abandoned one has been
    ended (_settle_if_abandoned). That commits, so a caller about to take
    lock_user asks this first."""
    session_ = (
        my_sessions()
        .filter_by(finished_at=None)
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    if session_ is None or _settle_if_abandoned(session_) != 'live':
        return None
    return session_


@gym_bp.app_template_filter('local')
def _local_filter(moment):
    """Naive UTC -> naive local, for anything a person reads as a date or time.

    Timestamps are stored naive-UTC and stay that way. Two hours of every CEST
    day fall on the previous UTC date, so an unconverted `strftime` filed a
    00:30 workout under yesterday -- next to a "vor 0 Tagen" that had already
    been corrected to local. Every human-readable render goes through here.

    NOT for durations. The elapsed clock's `data-started` stays UTC on purpose:
    GymClock appends 'Z' and subtracts from Date.now(), which is a difference
    between two instants and is the same number in any zone. Localising it
    would shift the clock by the offset.
    """
    return stats.to_local(moment)


@gym_bp.context_processor
def inject_gym_nav_context():
    """Makes the active session available to `_nav.html` on every gym page,
    not just the dashboard -- so the nav can show a "session running" dot
    and link straight to it from anywhere. An abandoned workout was already
    ended before the page was built (routes/__init__.py), so this only
    reads."""
    return {'gym_active_session': _get_active_session()}


def _cancel_pending_push(session_):
    """Cancel this session's still-pending push, if any. Must be called
    whenever resting_set_id/rest_ends_at is cleared or superseded -- an
    orphaned PendingPush row has no way to tell the notifier daemon that the
    set/exercise/session it was scheduled for is no longer current, and the
    daemon fires it regardless the moment it's due."""
    PendingPush.query.filter_by(session_id=session_.id, sent=False).delete()


# These four were defined near their first *reader* in the pre-split routes.py,
# which worked only because module globals resolve at call time -- WEEKDAY_SHORT
# sat 1300 lines below the gym_heute that used it. Splitting the file turns that
# latent ordering dependency into an import, so they live here, where every
# domain module can reach them.

# Here for the same reason MONTH_NAMES is: strftime('%a') follows the server's
# locale, which is not the UI's.
WEEKDAY_SHORT = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')

# Buckets in MUSCLE_GROUPS that are not muscle groups, so a section built
# from the full vocabulary does not carry them at zero forever.
NON_MUSCLE_GROUPS = ('Cardio', 'Sonstiges')

# How many finished workouts the Start page lists.
RECENT_SESSIONS = 5

# Start's first-run checklist stops asking after this many finished workouts
# without a routine: by then freeform is how this person trains, not a step
# they have not found yet.
ONBOARDING_WORKOUTS = 3

def _username(user_id):
    row = db.session.get(AppUser, user_id)
    return row.username if row is not None else 'Jemand'


# Whether this request is an island's fetch rather than a form post. The
# test lives with the login check, which needs it too (auth.login_redirect);
# the routes here read it under its old name.
_wants_json = wants_json


def _debrief_args():
    """The query flag a redirect to the debrief carries on: ?just_finished,
    which the "Routine aktualisieren" offer is gated on.

    Only that one. The whole query string used to be passed on, so
    `?session_id=` collided with url_for's own keyword (a 500) and `?_scheme=`
    rewrote the redirect (G-135).
    """
    if 'just_finished' in request.args:
        return {'just_finished': request.args['just_finished']}
    return {}
