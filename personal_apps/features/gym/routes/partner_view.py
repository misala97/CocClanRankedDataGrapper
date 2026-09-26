"""A training partner's workout, as the other one sees it (D14, M5).

The one place a lifter's workout is READ by someone else: the mirror of
sharing.py, which holds the one cross-user write, and of scope.py, where
every read of one's own is gated. Structure travels between the two as
writes (sharing.propagate_structure). What each of them lifts is shown to
the other, read-only: the live screen's partner line, the partner's list
behind it, and "mit <Name>" on the debrief and in Verlauf.

Only a link's two parties read through it, and every read first checks that
the users on the link own the sessions it names (_partner_of) -- a follower
never sees another follower of the same leader. What travels is what the
line and the list show: names, pictures, the sets lifted (weight, reps) and
how many are still open. Never a planned weight, a note, pain, bodyweight or
a record.
"""
import datetime as dt
import math
import zlib

from flask import abort, jsonify

from auth import login_required
from extensions import db
from models import AppUser, SessionExercise, SessionSet, SharedSession, WorkoutSession
from features.gym import art
from features.gym.schemas import PartnerList
from features.gym.scope import current_user_id
from .. import sharing
from ._blueprint import gym_bp
from .helpers import _counted, _username, planned_set_count
from .history import counts
from .live import _live_context, _load_rows


def _partner_of(link, viewer_id):
    """(the partner's session, whether the viewer leads), or (None, None).

    The viewer must be one of the link's two users, and both users must own
    the sessions the link names -- the check reconcile_follower makes before
    a write, made here before a read."""
    if link.follower_session_id is None or viewer_id not in (
            link.leader_user_id, link.follower_user_id):
        return None, None
    leader = db.session.get(WorkoutSession, link.leader_session_id)
    follower = db.session.get(WorkoutSession, link.follower_session_id)
    if (leader is None or follower is None or leader.user_id != link.leader_user_id
            or follower.user_id != link.follower_user_id):
        return None, None
    if viewer_id == link.leader_user_id:
        return follower, True
    return leader, False


def _rest_left(session_):
    """Whole seconds of the rest still running, or None."""
    if session_.rest_ends_at is None:
        return None
    left = (session_.rest_ends_at - dt.datetime.utcnow()).total_seconds()
    return math.ceil(left) if left > 0 else None


def _totals(partner):
    """(sets done, sets held): the partner's own tick strip -- every set that
    counts, and those plus the open ones still ahead. After their finish the
    open ones are gone, so what the workout held is what the finish kept
    (planned_sets; NULL before B4, when the open sets stayed)."""
    done = len(_counted(partner))
    if partner.finished_at is not None and partner.planned_sets is not None:
        return done, partner.planned_sets
    return done, planned_set_count(partner)


def _list_key(rows):
    """A fingerprint of what the partner's list shows: each visible row in
    its place, its exercise, its skip, and each set's tick and lift -- never
    a planned weight. An open sheet asks again when it moves, not only when
    the live row does: a swap further down, a lift corrected (I5 fix check).
    crc32, not hash(): every worker has to give the same number."""
    shown = [(se.id, se.exercise_id, se.skipped,
              [(s.weight, s.reps) if s.completed else None for s in se.sets])
             for se in rows]
    return zlib.crc32(repr(shown).encode())


def _line(link, username, leads, state, since, partner=None):
    line = {
        'id': link.id, 'username': username, 'viewer_leads': leads,
        'state': state, 'since': since, 'finished_at': None,
        'exercise': None, 'set_no': None, 'done_in_exercise': 0, 'sets_in_exercise': 0,
        'last_set': None, 'rest_left': None, 'sets_done': 0, 'sets_total': 0, 'list_key': 0,
    }
    if partner is None:
        return line
    held = _load_rows(partner)  # noqa: F841 -- held, not read: see _load_rows
    line['sets_done'], line['sets_total'] = _totals(partner)
    if state == 'finished':
        line['finished_at'] = partner.finished_at
        return line
    # The partner's live row by the partner's OWN rule: a follower's started
    # exercise stays live (_live_context), a leader's is the first open one.
    ctx = _live_context(partner, keep_started=sharing.is_live_follower(partner.id))
    live = next((se for se in ctx['visible_exercises'] if se.id == ctx['live_id']), None)
    if live is not None:
        counted = [s for s in live.sets if counts(s)]
        first_open = next((i for i, s in enumerate(live.sets) if not s.completed), None)
        newest = max(counted, key=lambda s: (s.completed_at or dt.datetime.min, s.id),
                     default=None)
        line.update(
            exercise=live.exercise.name,
            set_no=first_open + 1 if first_open is not None else None,
            done_in_exercise=len(counted),
            sets_in_exercise=len(live.sets),
            last_set=({'weight': newest.weight, 'reps': newest.reps}
                      if newest is not None else None),
        )
    line['rest_left'] = _rest_left(partner)
    line['list_key'] = _list_key(ctx['visible_exercises'])
    return line


def partner_links(session_):
    """The live screen's partner lines for this workout: one per link it
    leads (invited, declined, joined, ended, finished), or the one to the
    leader it follows (joined, ended, finished). An invite that ended nobody
    joined has none."""
    viewer = session_.user_id
    lines = []
    led = (SharedSession.query
           .filter(SharedSession.leader_session_id == session_.id)
           .order_by(SharedSession.id).all())
    for link in led:
        if link.leader_user_id != viewer:
            continue
        if link.accepted_at is None:
            if link.ended_at is not None:
                continue
            name = _username(link.follower_user_id)
            if link.declined_at is not None:
                lines.append(_line(link, name, True, 'declined', link.declined_at))
            else:
                lines.append(_line(link, name, True, 'invited', link.created_at))
            continue
        lines.extend(_accepted_line(link, viewer))
    followed = (SharedSession.query
                .filter(SharedSession.follower_session_id == session_.id,
                        SharedSession.accepted_at.isnot(None))
                .order_by(SharedSession.id).all())
    for link in followed:
        lines.extend(_accepted_line(link, viewer))
    return lines


def _accepted_line(link, viewer):
    partner, leads = _partner_of(link, viewer)
    if partner is None:
        return []
    name = _username(partner.user_id)
    if partner.finished_at is not None:
        return [_line(link, name, leads, 'finished', link.accepted_at, partner)]
    if link.ended_at is not None:
        # Left or ended, the partner still training (B11): said, not dropped.
        # Nothing about it moves any more, so it carries none of the partner's
        # rows and nothing polls it.
        return [_line(link, name, leads, 'ended', link.ended_at)]
    return [_line(link, name, leads, 'joined', link.accepted_at, partner)]


def partner_list(link, partner, leads):
    """The partner's workout for the sheet: their visible rows in their own
    order (which, while the link is live, is the leader's), each with what
    was lifted and the count their own queue gives it. Runs to the partner's
    own finish, past the link's end (Michi). After that finish the open sets
    are gone, so a row nothing was lifted on reads as not done."""
    held = _load_rows(partner)  # noqa: F841 -- held, not read: see _load_rows
    finished = partner.finished_at is not None
    ctx = _live_context(partner, keep_started=sharing.is_live_follower(partner.id))
    rows = []
    for se in ctx['visible_exercises']:
        lifted = [s for s in se.sets if counts(s)]
        # A skipped row's open sets are not ahead (the tally's rule).
        open_ = 0 if finished or se.skipped else sum(1 for s in se.sets if not s.completed)
        first_open = next((i for i, s in enumerate(se.sets) if not s.completed), None)
        if se.skipped or (finished and not lifted):
            state = 'skipped'
        elif not finished and se.id == ctx['live_id'] and (open_ or not se.sets):
            state = 'now'
        elif se.sets and not open_:
            state = 'done'
        else:
            state = 'open'
        rows.append({
            'id': se.id, 'name': se.exercise.name,
            'picture': art.picture_url(se.exercise.library_key),
            'state': state,
            'sets': [{'weight': s.weight, 'reps': s.reps} for s in lifted],
            # The count their own queue gives the row (Queue.tsx loadSummary):
            # every ticked set, one without reps too, of every set it holds.
            'done': sum(1 for s in se.sets if s.completed),
            'open': open_,
            # The set they are on, counted as the line counts it (_line).
            'set_no': (first_open + 1 if state == 'now' and first_open is not None
                       else None),
        })
    done, total = _totals(partner)
    # Live as sharing._live_links says it: not ended, and both workouts still
    # run -- a finish that left no stamp ended the sharing all the same (B11).
    own = db.session.get(WorkoutSession,
                         link.leader_session_id if leads else link.follower_session_id)
    return {
        'id': link.id, 'username': _username(partner.user_id), 'viewer_leads': leads,
        'link_live': (link.ended_at is None and not finished
                      and own is not None and own.finished_at is None),
        'since': link.accepted_at, 'started_at': partner.started_at,
        'finished_at': partner.finished_at,
        'sets_done': done, 'sets_total': total,
        'rest_left': None if finished else _rest_left(partner),
        'rows': rows,
    }


@gym_bp.route('/gym/shared/<int:shared_id>/list.json')
@login_required
def gym_shared_list(shared_id):
    """The list behind a partner line or a "mit <Name>". 404 for anyone but
    the link's two parties, and for a link nobody joined: 404 rather than
    403, like every ownership failure in the gym."""
    link = db.session.get(SharedSession, shared_id)
    if link is None or link.accepted_at is None:
        abort(404)
    partner, leads = _partner_of(link, current_user_id())
    if partner is None:
        abort(404)
    return jsonify(PartnerList.model_validate(partner_list(link, partner, leads))
                   .model_dump(mode='json'))


def partner_refs(session_ids):
    """{session id: [{'id', 'username'}]}: whom each of these workouts was
    done with, for "mit <Name>" on the debrief and in Verlauf. In four
    queries however many workouts are asked about.

    A partner counts once they joined and lifted a set (Michi): an invite
    nobody answered, or a partner who never logged anything, is nobody to
    have trained with."""
    ids = set(session_ids)
    if not ids:
        return {}
    links = (SharedSession.query
             .filter(SharedSession.accepted_at.isnot(None),
                     SharedSession.follower_session_id.isnot(None),
                     db.or_(SharedSession.leader_session_id.in_(ids),
                            SharedSession.follower_session_id.in_(ids)))
             .order_by(SharedSession.id).all())
    if not links:
        return {}
    named = {l.leader_session_id for l in links} | {l.follower_session_id for l in links}
    owner = dict(db.session.query(WorkoutSession.id, WorkoutSession.user_id)
                 .filter(WorkoutSession.id.in_(named)).all())
    lifted = dict(db.session.query(SessionExercise.session_id, db.func.count(SessionSet.id))
                  .join(SessionSet, SessionSet.session_exercise_id == SessionExercise.id)
                  .filter(SessionExercise.session_id.in_(named),
                          SessionSet.completed == True,  # noqa: E712
                          SessionSet.reps >= 1)
                  .group_by(SessionExercise.session_id).all())
    users = {l.leader_user_id for l in links} | {l.follower_user_id for l in links}
    names = dict(db.session.query(AppUser.id, AppUser.username)
                 .filter(AppUser.id.in_(users)).all())
    refs = {}
    for link in links:
        if (owner.get(link.leader_session_id) != link.leader_user_id
                or owner.get(link.follower_session_id) != link.follower_user_id):
            continue
        if link.leader_session_id in ids:
            mine, theirs, who = link.leader_session_id, link.follower_session_id, link.follower_user_id
        else:
            mine, theirs, who = link.follower_session_id, link.leader_session_id, link.leader_user_id
        if lifted.get(theirs, 0) < 1:
            continue
        refs.setdefault(mine, []).append({'id': link.id, 'username': names.get(who, 'Jemand')})
    return refs


def followed_a_leader(session_):
    """Whether this workout followed someone's order: the follower half of a
    link that was accepted, live or since ended. Its debrief offers no
    routine update (Michi): the order it would write was the leader's."""
    return SharedSession.query.filter(
        SharedSession.follower_session_id == session_.id,
        SharedSession.accepted_at.isnot(None)).first() is not None
