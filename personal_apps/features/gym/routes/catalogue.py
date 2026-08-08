"""The exercise catalogue: the list page and exercise create / update /
delete."""

from features.gym import stats
import datetime as dt

from flask import (
    flash, redirect, render_template, request, url_for,
)
from extensions import (
    db,
)
from models import (
    EQUIPMENT_LABELS, Exercise, MUSCLE_GROUPS,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    current_user_id, my_exercises, owned_exercise,
)
from .helpers import (
    DEFAULT_REST_SECONDS, EXERCISE_STATE_CHIP, NON_MUSCLE_GROUPS, _clean_equipment, _clean_muscle_group, _clean_secondary_groups, _to_increment, _to_int, _to_stack_steps,
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
    now = dt.datetime.utcnow()
    exercises = my_exercises().order_by(Exercise.name).all()

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

    return render_template(
        'gym/uebungen.html',
        grouped=grouped,
        muscle_groups=MUSCLE_GROUPS,
        equipment_labels=EQUIPMENT_LABELS,
        open_by_default=len(exercises) <= UEBUNGEN_FOLD_ABOVE,
        # The sheet's rest placeholder said 90 while this is what a blank field
        # actually stores.
        default_rest_seconds=DEFAULT_REST_SECONDS,
        added_id=_to_int(request.args.get('added')),
        name_taken=bool(request.args.get('name_taken')),
    )




# Above this many exercises the catalogue opens folded; at or below it every
# group starts open. Hardcoded shut, the page's default state contained no
# exercises at all -- 0 of 17 visible on a phone AND on a 1280 desktop, with
# the fastest route to your own list being to press a SORT button, because the
# two flat sorts ignore the fold. Folding is right for a long catalogue and
# wrong for a short one, so it follows the length.
UEBUNGEN_FOLD_ABOVE = 30


@gym_bp.route('/gym/exercises/add', methods=['POST'])
@login_required
def gym_add_exercise():
    # The write reports itself. A duplicate name was a silent no-op and a
    # success landed the new exercise inside a collapsed band, so the only
    # difference between "saved" and "discarded" was a digit beside the h1.
    # gym_update_exercise already had the ?name_taken= convention; this is the
    # same one.
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('gym.gym_uebungen'))
    # No flash on either branch: the input is `required`, so an empty name does
    # not reach here through the UI, and ?name_taken already renders a banner on
    # the page that says this in context. A flash would say it twice.
    if my_exercises().filter_by(name=name).first():
        return redirect(url_for('gym.gym_uebungen', name_taken=1))

    muscle_group = _clean_muscle_group(request.form.get('muscle_group', ''))
    equipment = _clean_equipment(request.form.get('equipment', ''))
    exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
        equipment=equipment,
        bar_weight=_to_increment(request.form.get('bar_weight', '')),
        # Stack steps only mean something for a stack machine -- the hidden
        # Stack-Stufen input still submits its old value even when Art has
        # been switched away from stack, and increment_kg/stack_kg are meant
        # to be mutually exclusive (the export derives one from the other).
        stack_kg=_to_stack_steps(request.form.get('stack_kg', '')) if equipment == 'stack' else None,
        secondary_muscle_groups=_clean_secondary_groups(
            request.form.getlist('secondary_muscle_groups'), muscle_group),
        user_id=current_user_id(),
    )
    db.session.add(exercise)
    db.session.commit()
    return redirect(url_for('gym.gym_uebungen', added=exercise.id))


@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
def gym_update_exercise(exercise_id):
    exercise = owned_exercise(exercise_id)
    new_name = request.form.get('name', '').strip()
    name_taken = False
    if new_name and new_name != exercise.name:
        if my_exercises().filter_by(name=new_name).first():
            name_taken = True  # surfaced to the user below instead of silently skipping the rename
        else:
            # Remember the old name so anything still referencing it (e.g.
            # historical data, or a rename made by mistake) can still
            # resolve to this exercise instead of creating a duplicate.
            exercise.previous_name = exercise.name
            exercise.name = new_name
    exercise.muscle_group = _clean_muscle_group(request.form.get('muscle_group', ''), current=exercise.muscle_group)
    exercise.default_rest_seconds = _to_int(request.form.get('default_rest_seconds', ''))
    exercise.weight_increment = _to_increment(request.form.get('weight_increment', ''))
    exercise.is_unilateral = request.form.get('is_unilateral') == 'on'
    exercise.equipment = _clean_equipment(request.form.get('equipment', ''),
                                          current=exercise.equipment)
    exercise.bar_weight = _to_increment(request.form.get('bar_weight', ''))
    # Stack steps only mean something for a stack machine -- the hidden
    # Stack-Stufen input still submits its old value even when Art has been
    # switched away from stack, and increment_kg/stack_kg are meant to be
    # mutually exclusive (the export derives one from the other).
    exercise.stack_kg = (
        _to_stack_steps(request.form.get('stack_kg', '')) if exercise.equipment == 'stack' else None
    )
    exercise.secondary_muscle_groups = _clean_secondary_groups(
        request.form.getlist('secondary_muscle_groups'), exercise.muscle_group)
    db.session.commit()
    return redirect(url_for(
        'gym.exercise_detail', exercise_id=exercise.id, name_taken=1 if name_taken else None,
    ))


@gym_bp.route('/gym/exercises/<int:exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_exercise(exercise_id):
    exercise = owned_exercise(exercise_id)
    if exercise.session_exercises or exercise.template_exercises:
        # Silently refusing looked identical to deleting, so the row just
        # stayed there with no reason given.
        flash(f'„{exercise.name}“ steckt noch in einem Workout oder einer Routine '
              f'und wurde nicht gelöscht.', 'error')
        return redirect(url_for('gym.gym_uebungen'))
    name = exercise.name
    db.session.delete(exercise)
    db.session.commit()
    flash(f'Übung „{name}“ gelöscht.', 'success')
    return redirect(url_for('gym.gym_uebungen'))
