"""Shared constants, request-value coercion, and the gym nav context.

Every coercion here answers the same question: what does this value mean when
the input is missing, blank, or not a number. They arrive from form posts and
query strings, so none of them may raise.

This is a leaf module -- it imports no other routes module, which is what lets
every other one import it. _cancel_pending_push lives here rather than with the
workout routes for exactly that reason: _get_active_session calls it, and
leaving it in workout.py would make helpers and workout import each other.

Moved verbatim from the pre-split routes.py.
"""
import datetime as dt

from flask import request

from extensions import db
from models import (
    AppUser, WorkoutSession, PendingPush, STALE_SESSION_TIMEOUT,
    MUSCLE_GROUPS, EQUIPMENT_TYPES,
)
from features.gym import stats
from features.gym.scope import my_sessions
from .. import sharing
from ._blueprint import gym_bp


DEFAULT_REST_SECONDS = 180  # fallback for newly created exercises when no rest time is given

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
    """A weight increment as typed, or None.

    Comma-tolerant: `type=number` normalises to a dot, but the field degrades
    to text without JS and a German keyboard produces `2,5`. Blank,
    unparseable and non-positive all store NULL, which
    stats.resolve_increment() reads as "use the default" -- so clearing the
    field is the way to put an exercise back on 2.5 kg.
    """
    parsed = _to_float(str(value).replace(',', '.').strip())
    return parsed if parsed and parsed > 0 else None


def _to_int(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clean_muscle_group(value, current=None):
    """Restricts new values to MUSCLE_GROUPS, but if the submitted value is
    just the exercise's existing value coming back unchanged (e.g. a legacy
    free-text category from before this enum existed), preserve it instead
    of silently nulling it out -- only an actual attempt to change it is
    held to the fixed list."""
    value = (value or '').strip()
    if value in MUSCLE_GROUPS:
        return value
    if current and value == current:
        return current
    return None


def _clean_equipment(raw, current='stack'):
    """An unknown value keeps whatever the exercise already had. The form
    only ever submits the three real values; anything else is a hand-rolled
    request, and silently widening the column's vocabulary from one of those
    would break the export's derivation table."""
    value = (raw or '').strip()
    return value if value in EQUIPMENT_TYPES else current


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
        if value > 0:
            steps.append(value)
    return sorted(set(steps)) or None


def _clean_secondary_groups(values, primary):
    """Known groups only, in the order given, primary removed. None when
    nothing is left -- the column treats NULL and [] the same and NULL is
    the cheaper of the two to store."""
    seen = []
    for value in values or []:
        value = (value or '').strip()
        if value in MUSCLE_GROUPS and value != primary and value not in seen:
            seen.append(value)
    return seen or None


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

def _username(user_id):
    row = db.session.get(AppUser, user_id)
    return row.username if row is not None else 'Jemand'


def _wants_json():
    """Whether this request is an island's fetch rather than a form post.

    Both halves are load-bearing. A browser form post sends
    `Accept: text/html,...,*/*;q=0.8`, so accept_json is TRUE via the wildcard
    -- testing it alone would flip every form post to JSON and take the page
    down. A bare fetch() sends */* and lands on the html side too, which is
    why every island sends `Accept: application/json` explicitly (src/api.ts).
    """
    return (request.accept_mimetypes.accept_json
            and not request.accept_mimetypes.accept_html)
