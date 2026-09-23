"""The exercise catalogue: the list page, and a lifter's settings -- for one
exercise, and their rest for all of them.

Since the one exercise list (2026-09-23) nobody creates, renames or deletes
an exercise here. The page lists the lifter's own exercises -- the ones they
logged, keep in a routine or set up (exercises.touched_exercises) -- and the
only writes are their step, rest, stack stops and bar, and "Deine Pause"."""

from features.gym import stats
from features.gym.schemas import CataloguePayload, ExerciseMeta, RestOverview
import datetime as dt

from flask import (
    abort, jsonify, redirect, render_template, request, url_for,
)
from extensions import (
    db,
)
from models import (
    MUSCLE_GROUPS,
)
from auth import (
    login_required,
)
from features.gym.exercises import (
    REST_MAX_SECONDS, REST_MIN_SECONDS, exercise_or_404, rest_overview, save_setup,
    set_rest_for_all, setup as exercise_setup, setups as exercise_setups,
    touched_exercises,
)
from features.gym.scope import (
    current_user_id,
)
from .helpers import (
    EXERCISE_STATE_CHIP, NON_MUSCLE_GROUPS, _exercise_meta,
    _to_increment, _to_int, _to_stack_steps, _to_weight, _wants_json,
)
from .history import (
    load_performed,
)
from ._blueprint import (
    gym_bp,
)


@gym_bp.route('/gym/uebungen')
@login_required
def gym_uebungen():
    return render_template(
        'gym/uebungen.html',
        payload_json=_catalogue_payload().model_dump(mode='json'),
    )


def _catalogue_payload():
    """The caller's catalogue as a validated payload: the exercises they have
    logged, kept in a routine or set up, each with their settings."""
    now = dt.datetime.utcnow()
    user_id = current_user_id()
    exercises = touched_exercises(user_id)
    setups = exercise_setups(user_id, exercises)

    # The one bulk load this whole page runs on -- every completed set ever
    # logged, across the whole catalogue. Every exercise's state/last-done/
    # best-weight/best-e1RM below is computed from this single result,
    # grouped by exercise_id in Python; must not be queried again per
    # exercise (see load_performed()'s own docstring, spec 5.4).
    performed = load_performed()
    rows_by_exercise = {}
    for row in performed:
        rows_by_exercise.setdefault(row.exercise_id, []).append(row)

    entries_by_id = {}
    for exercise in exercises:
        rows = rows_by_exercise.get(exercise.id, [])
        # Judged slot, record weight and record e1RM must agree with what
        # the exercise's own detail page shows and with what stall_report()
        # judges on the dashboard, so deload rows are dropped BEFORE they
        # reach dominant_position/best_e1rm/best_weight/sessions_since_pr --
        # the same filter-before-judge order stall_report() uses (see its
        # own docstring). `last_done` stays on the unfiltered `rows`: "when
        # did I last do this" is a fact a deload session legitimately
        # answers, it is not a judgement.
        progression = stats.progression_rows(rows)
        # dominant_position() requires at least one row -- a brand new
        # exercise, or one whose only history is deloads, has no position to
        # speak of, and exercise_state returns 'neu' from its own
        # empty-rows check before position is ever consulted, so None is a
        # safe stand-in here.
        position = stats.dominant_position(progression) if progression else None
        best_e1rm = max((stats.best_e1rm(row) for row in progression), default=None)
        state = stats.exercise_state(progression, position=position)
        chip_class, chip_label = EXERCISE_STATE_CHIP.get(state, (None, None))
        last_done = max((row.started_at for row in rows), default=None)
        entries_by_id[exercise.id] = {
            'exercise': exercise,
            'chip_class': chip_class,
            'chip_label': chip_label,
            'last_done': last_done,
            'best_weight': max((stats.best_weight(row) for row in progression), default=None),
            # What you would load TODAY, which is the question a catalogue is
            # opened with. The row led with the all-time best -- unlabelled, so
            # "Military Press · 15,0 kg" could not be told apart from a working
            # weight -- and that figure is already on the exercise's own page
            # with a label on it.
            'last_weight': stats.best_weight(progression[-1]) if progression else None,
            'days_ago': (stats.calendar_days_between(last_done, now)
                         if last_done is not None else None),
            'sessions_since_pr': stats.sessions_since_pr(progression, position=position) if progression else None,
        }

    # Default/grouped view (spec 6.2's "nach Muskelgruppe"). The two flat
    # sorts ("am längsten ohne PR", "zuletzt gemacht") are client-side
    # re-orderings of these SAME rows in uebungen.html's own script, not a
    # second server round trip -- every exercise's data attributes carry
    # what that script needs (see the template).
    # Seeded from MUSCLE_GROUPS, so a group with nothing in it still gets a
    # band. group_exercises_by_muscle emits only non-empty groups, which made
    # the catalogue structurally unable to say "you have no leg exercises" --
    # the single strongest signal for the planning question, rendered as
    # nothing at all. Same fix Start's muscle balance got in item 5, and
    # Cardio/Sonstiges stay out for the same reason.
    filled = dict(stats.group_exercises_by_muscle(exercises, MUSCLE_GROUPS))
    grouped = []
    for group_name in MUSCLE_GROUPS:
        if group_name in NON_MUSCLE_GROUPS and group_name not in filled:
            continue
        grouped.append((group_name,
                        [entries_by_id[e.id] for e in filled.get(group_name, [])]))
    for group_name, group_exercises in filled.items():
        if group_name not in MUSCLE_GROUPS:      # NO_GROUP_LABEL and legacy values
            grouped.append((group_name, [entries_by_id[e.id] for e in group_exercises]))

    payload = CataloguePayload.model_validate({
        'groups': [
            {'name': name,
             'entries': [{**entry, 'exercise': _exercise_meta(entry['exercise'],
                                                              setups[entry['exercise'].id])}
                         for entry in entries]}
            for name, entries in grouped
        ],
        'open_by_default': len(exercises) <= UEBUNGEN_FOLD_ABOVE,
        'rest': rest_overview(user_id),
    })
    return payload




# Above this many exercises the catalogue opens folded; at or below it every
# group starts open. Hardcoded shut, the page's default state contained no
# exercises at all -- 0 of 17 visible on a phone AND on a 1280 desktop, with
# the fastest route to your own list being to press a SORT button, because the
# two flat sorts ignore the fold. Folding is right for a long catalogue and
# wrong for a short one, so it follows the length.
UEBUNGEN_FOLD_ABOVE = 30

@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
def gym_update_exercise(exercise_id):
    """Save the caller's settings for an exercise.

    Only the four personal fields are read, and only those the form sent: a
    field left out keeps its stored value, a blank one goes back to the
    list's. Name, groups, equipment and one side belong to the list and are
    ignored if posted.
    """
    exercise = exercise_or_404(exercise_id)
    # Each field parsed; a blank parses to None, the list's value. The bar
    # parses as a weight so that 0 -- "nothing inside the number" -- survives.
    # Kept in the body: the form/route pairing test reads field names here.
    parsers = {
        'weight_increment': _to_increment,
        'default_rest_seconds': _to_int,
        'stack_kg': _to_stack_steps,
        'bar_weight': _to_weight,
    }
    submitted = {field: parse(request.form.get(field, ''))
                 for field, parse in parsers.items() if field in request.form}
    saved = save_setup(current_user_id(), exercise, submitted)
    db.session.commit()
    if _wants_json():
        # "Deine Einstellungen" saves every tap and redraws from the answer.
        return jsonify(_settings_json(exercise, saved))
    return redirect(url_for('gym.exercise_detail', exercise_id=exercise.id))


def _settings_json(exercise, setup):
    return ExerciseMeta.model_validate(_exercise_meta(exercise, setup)).model_dump(mode='json')


@gym_bp.route('/gym/exercises/<int:exercise_id>/settings.json')
@login_required
def gym_exercise_settings(exercise_id):
    """The caller's settings for an exercise, for the sheet the workout
    opens: its rows carry the rest in force, not the list's values."""
    exercise = exercise_or_404(exercise_id)
    return jsonify(_settings_json(exercise, exercise_setup(current_user_id(), exercise)))


@gym_bp.route('/gym/rest', methods=['POST'])
@login_required
def gym_rest_for_all():
    """Set the caller's rest for all their exercises ("Deine Pause"): whole
    seconds within the stepper's ends, or blank for "Je nach Übungsart".
    Anything else is refused -- a garbled number must not quietly switch
    the rest for all off. Answers with the fresh overview."""
    raw = request.form.get('rest_seconds', '').strip()
    seconds = None
    if raw:
        seconds = _to_int(raw)
        if seconds is None or not REST_MIN_SECONDS <= seconds <= REST_MAX_SECONDS:
            abort(400)
    user_id = current_user_id()
    set_rest_for_all(user_id, seconds)
    db.session.commit()
    if _wants_json():
        return jsonify(RestOverview.model_validate(rest_overview(user_id)).model_dump(mode='json'))
    return redirect(url_for('gym.gym_uebungen'))
