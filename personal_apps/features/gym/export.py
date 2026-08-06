"""The JSON an external coaching tool reads.

Schema v2. The break from v1 is small but real: `is_deload` became
`deload`, and every exercise now carries what the logged weight physically
means (`weight_convention`) plus what the machine can actually be loaded
to (`increment_kg` or `stack_kg`). A reader that guesses at either of
those recommends weights that cannot be selected.

This module takes ORM rows and returns plain dicts. It holds no queries
and no request handling, so the contract can be tested without a database
or an HTTP client -- which is the point, because the contract is the part
that must not drift.
"""

SCHEMA_VERSION = 2


def _stamp(value):
    """ISO 8601 UTC, matching v1's format exactly."""
    return value.isoformat() + 'Z' if value is not None else None


def weight_convention(equipment, is_unilateral):
    """What the logged number means, derived rather than stored.

    Two orthogonal facts already answer this: how the exercise is loaded,
    and whether the number is one side's share. Storing a third field that
    restates their combination would let it disagree with them -- and
    volume is computed from is_unilateral alone (stats.set_volume), so the
    stored value would be the one that is wrong.

    The contract's fourth value, `per_arm`, is never emitted: nothing in
    this app distinguishes "one side at a time" from "both at once", and
    both double the volume identically.
    """
    if not is_unilateral:
        return 'total'
    return 'per_dumbbell' if equipment == 'dumbbell' else 'per_side'


def set_payload(session_set):
    return {
        'position': session_set.position,
        'weight': session_set.weight,
        'reps': session_set.reps,
        'completed': session_set.completed,
        # completed_at is cleared whenever a set stops being completed, so
        # this is null exactly for sets that never happened.
        'finished_at': _stamp(session_set.completed_at),
    }


def exercise_payload(session_exercise):
    exercise = session_exercise.exercise
    stack_kg = exercise.stack_kg or None
    return {
        'exercise_id': exercise.id,
        'exercise_name': exercise.name,
        'muscle_group': exercise.muscle_group,
        'secondary_muscle_groups': exercise.secondary_muscle_groups or [],
        'equipment': exercise.equipment,
        'weight_convention': weight_convention(exercise.equipment, exercise.is_unilateral),
        'bar_weight': exercise.bar_weight,
        # Mutually exclusive by contract: real stops are a complete answer,
        # and a step size beside them would be a second, coarser one.
        'increment_kg': None if stack_kg else exercise.weight_increment,
        'stack_kg': stack_kg,
        'position': session_exercise.position,
        'replaces': (session_exercise.replaces.exercise.name
                     if session_exercise.replaces else None),
        'replaced_by': (session_exercise.replaced_by.exercise.name
                        if session_exercise.replaced_by else None),
        'rest_seconds': session_exercise.rest_seconds,
        'notes': session_exercise.notes or '',
        'pain': bool(session_exercise.pain),
        'skipped': session_exercise.skipped,
        'sets': [set_payload(s) for s in session_exercise.sets],
    }


def session_payload(session):
    return {
        'id': session.id,
        'name': session.name,
        'template_name': session.template.name if session.template else None,
        'started_at': _stamp(session.started_at),
        'finished_at': _stamp(session.finished_at),
        'deload': session.is_deload,
        # Kept beside the boolean: how deep a deload went is not recoverable
        # from "it was one".
        'deload_pct': session.deload_pct,
        'bodyweight_kg': session.bodyweight_kg,
        'notes': session.notes or '',
        'exercises': [exercise_payload(se) for se in session.exercises],
    }


def build_payload(sessions, requested_session_ids, exported_at):
    """`range` is derived from what actually came back, not from what was
    asked for. The route is id-picked -- Verlauf's 30/90-day presets are a
    client-side bulk-check and no date range ever reaches the server -- so
    a range echoing the request would be inventing one. requested_session_ids
    stays beside it as the only record of the gap between asked and
    delivered.
    """
    dates = sorted(s.started_at.date() for s in sessions)
    return {
        'schema_version': SCHEMA_VERSION,
        'exported_at': _stamp(exported_at),
        'range': {
            'from': dates[0].isoformat() if dates else None,
            'to': dates[-1].isoformat() if dates else None,
        },
        'requested_session_ids': requested_session_ids,
        'sessions': [session_payload(s) for s in sessions],
    }
