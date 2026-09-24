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

from flask import jsonify, redirect, request, url_for

from auth import wants_json
from extensions import db
from models import (
    AppUser, WorkoutSession, PendingPush, SharedSession, STALE_SESSION_TIMEOUT,
)
from features.gym import stats
from features.gym.exercises import (
    REST_MAX_SECONDS, REST_MIN_SECONDS, list_values, settle_rests,
)
from features.gym.scope import my_sessions
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


# Sent by the live workout island on every write. The debrief writes to the
# same set routes on purpose -- a finished workout is corrected there -- so
# finished_at alone cannot tell the two apart; the surface that asked can.
LIVE_SURFACE_HEADER = 'X-Gym-Surface'


def _refuse_live_write_if_finished(session_):
    """409 for a live-screen write to a workout that has already finished,
    else None.

    The live screen outlives the workout: the back button restores it, and a
    second phone never saw the finish. Its "Satz geschafft" used to land in
    the finished workout, queue a rest push for it, and hand the island a
    debrief payload it could not render. The island answers a 409 by
    reloading, which shows the debrief.
    """
    if session_.finished_at is None or request.headers.get(LIVE_SURFACE_HEADER) != 'live':
        return None
    if _wants_json():
        return jsonify({'finished': True}), 409
    return redirect(url_for('gym.session_detail', session_id=session_.id))


def _delete_session_and_links(session_):
    """Delete a workout together with every partner link it took part in.

    Plain FKs with no ondelete point at the session from both halves of a
    link, with no ORM cascade either -- so the link rows have to go first.
    The resting-set pointer is cleared before the cascade deletes the set it
    names. Commits.
    """
    session_.resting_set_id = None
    db.session.commit()
    doomed_link_ids = [row.id for row in SharedSession.query.filter(
        db.or_(SharedSession.leader_session_id == session_.id,
               SharedSession.follower_session_id == session_.id)).all()]
    if doomed_link_ids:
        SharedSession.query.filter(SharedSession.id.in_(doomed_link_ids)).delete(
            synchronize_session=False)
    db.session.delete(session_)
    db.session.commit()


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


def _get_active_session():
    """The one in-progress workout, if any. Sessions left open past
    STALE_SESSION_TIMEOUT are treated as abandoned and auto-finished here,
    capped at started_at + timeout rather than "now"."""
    session_ = (
        my_sessions()
        .filter_by(finished_at=None)
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    if session_ and dt.datetime.utcnow() - session_.started_at > STALE_SESSION_TIMEOUT:
        session_.finished_at = session_.started_at + STALE_SESSION_TIMEOUT
        session_.rest_ends_at = None
        session_.resting_set_id = None
        settle_rests(session_)
        _cancel_pending_push(session_)
        # This is a second, differently-spelled site that stamps finished_at
        # (started_at + timeout, not utcnow()) -- the brief's suggested grep
        # for the literal string "finished_at = dt.datetime.utcnow()" does not
        # match it, but going stale ends the workout exactly as explicitly
        # finishing it does, so the same rule applies: whoever finishes first
        # ends the sharing, the other trains on alone.
        sharing.end_links_for(session_)
        db.session.commit()
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
    and link straight to it from anywhere. Reuses `_get_active_session`,
    which is already idempotent (it only mutates state once, the first time
    it notices a session has gone stale past the timeout)."""
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
