"""The exercise catalogue: the list page, and a lifter's settings -- for one
exercise, and their rest for all of them.

Since the one exercise list (2026-09-23) nobody creates, renames or deletes
an exercise here. The page lists the lifter's own exercises -- the ones they
logged, keep in a routine or set up (exercises.touched_exercises) -- and then
the rest of the list, "Noch nie gemacht" (M6). The only writes are their
step, rest, stack stops and bar, and "Deine Pause"."""

from features.gym import art, stats
from features.gym.library import BY_KEY, LIST_GROUPS, MOVEMENT_GROUP
from features.gym.schemas import CataloguePayload, ExerciseMeta, RestOverview
import datetime as dt

from flask import (
    jsonify, redirect, render_template, request, url_for,
)
from extensions import (
    db,
)
from models import (
    MUSCLE_GROUPS, SessionExercise, SessionSet,
)
from auth import (
    login_required,
)
from features.gym.exercises import (
    exercise_or_404, library_exercises, rest_overview, save_setup,
    search_text, set_rest_for_all, setup as exercise_setup, setups as exercise_setups,
    touched_exercises,
)
from features.gym.scope import (
    current_user_id,
)
from ..locking import lock_user
from .helpers import (
    EXERCISE_STATE_CHIP, _exercise_meta, _page_active_session,
    _to_bar_weight, _to_increment, _to_rest_seconds, _to_stack_steps, _wants_json,
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
    logged, kept in a routine or set up, each with their settings -- and the
    rest of the list."""
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
    lifted = _lifted_running()

    entries_by_id = {}
    for exercise in exercises:
        rows = rows_by_exercise.get(exercise.id, [])
        # The judged slot and "what you would load today" must agree with the
        # exercise's own page and with stall_report(), so deload rows are
        # dropped before they reach dominant_position and last_weight -- a
        # deliberately light workout is no working weight. Records, the
        # heaviest set, the "ohne PR" count and `last_done` read every row:
        # those are facts, and a deload workout legitimately answers them.
        progression = stats.progression_rows(rows)
        # dominant_position() requires at least one row -- a brand new
        # exercise, or one whose only history is deloads, has no position to
        # speak of, and exercise_state returns 'neu' from its own
        # empty-rows check before position is ever consulted, so None is a
        # safe stand-in here.
        position = stats.dominant_position(progression) if progression else None
        # Every row, deloads included: 'Rekord' is a record whatever the
        # workout was (D3), and exercise_state drops deloads itself for the
        # progress verdicts -- as on the exercise's own page.
        state = stats.exercise_state(rows, position=position)
        chip_class, chip_label = EXERCISE_STATE_CHIP.get(state, (None, None))
        last_done = max((row.started_at for row in rows), default=None)
        entries_by_id[exercise.id] = {
            'exercise': exercise,
            # What the page's search looks in: the add sheet's text, so a
            # word that finds an exercise there finds it here (G-020).
            'search': search_text(exercise),
            'chip_class': chip_class,
            'chip_label': chip_label,
            'last_done': last_done,
            # Every row, deloads included: the heaviest set is a fact, and the
            # exercise's own page says "Schwerster Satz" from all of them.
            'best_weight': max((stats.best_weight(row) for row in rows), default=None),
            # What you would load TODAY, which is the question a catalogue is
            # opened with. The row led with the all-time best -- unlabelled, so
            # "Military Press · 15,0 kg" could not be told apart from a working
            # weight -- and that figure is already on the exercise's own page
            # with a label on it.
            'last_weight': stats.best_weight(progression[-1]) if progression else None,
            'days_ago': (stats.calendar_days_between(last_done, now)
                         if last_done is not None else None),
            # From the last record, whatever slot or workout set it: the same
            # count as the chip beside it and every other "ohne PR" (drought).
            'sessions_since_pr': stats.sessions_since_pr(rows),
            'in_running': exercise.id in lifted,
        }

    # Default/grouped view ("Nach Muskelgruppe"); the two flat sorts are the
    # page's own re-orderings of these same rows, not a second round trip.
    # Each band is a muscle group -- it says what the exercise trains -- and
    # the bands come in the list's order, the add sheet's (G-013: Übungen ran
    # Bizeps, Trizeps, Brust ... beside the sheet's Brust, Rücken ...). Every
    # group of the list is here, an empty one too: group_exercises_by_muscle
    # emits only filled ones, and "you have no leg exercises" is the
    # strongest signal for the planning question. The page says it in one
    # line ("Noch nichts für Beine") that links to that band of the rest of
    # the list, not in a band apiece. Cardio and Sonstiges come only when
    # filled, then anything else (NO_GROUP_LABEL and legacy values).
    filled = dict(stats.group_exercises_by_muscle(exercises, MUSCLE_GROUPS))
    names = list(LIST_GROUPS)
    names += [name for name in MUSCLE_GROUPS if name not in names and name in filled]
    names += [name for name in filled if name not in names]
    grouped = [(name, [entries_by_id[e.id] for e in filled.get(name, [])]) for name in names]

    # The rest of the list (M6, D13-A): a new lifter could not browse it
    # outside a workout (G-004), and an exercise never done was a dead end
    # to reach (G-041). One query more, the add sheet's rows.
    mine = set(entries_by_id)
    library = [_library_entry(exercise) for exercise in library_exercises()
               if exercise.id not in mine]

    payload = CataloguePayload.model_validate({
        'groups': [
            {'name': name,
             'entries': [{**entry, 'exercise': _exercise_meta(entry['exercise'],
                                                              setups[entry['exercise'].id]),
                          'picture': art.picture_url(entry['exercise'].library_key)}
                         for entry in entries]}
            for name, entries in grouped
        ],
        'open_by_default': len(exercises) <= UEBUNGEN_FOLD_ABOVE,
        'rest': rest_overview(user_id),
        'library': library,
        'list_groups': list(LIST_GROUPS),
    })
    return payload


def _lifted_running():
    """The exercises the running workout holds sets of that count (Q1), a
    replaced-away original's too; none without a running workout. The rows
    read finished workouts only (load_performed), so a first go at an
    exercise, three sets in, said "Noch kein Satz". One query."""
    session_ = _page_active_session()
    if session_ is None:
        return set()
    return {exercise_id for (exercise_id,) in (
        db.session.query(SessionExercise.exercise_id)
        .join(SessionSet, SessionSet.session_exercise_id == SessionExercise.id)
        .filter(SessionExercise.session_id == session_.id,
                SessionSet.completed == True,  # noqa: E712
                SessionSet.reps >= 1)
        .distinct())}


def _library_entry(exercise):
    """One row of "Noch nie gemacht": the entry, the movement it is a
    variant of, and the band it goes in -- its movement's, as in the add
    sheet, so a movement's variants stay together."""
    entry = BY_KEY[exercise.library_key]
    return {
        'id': exercise.id, 'name': exercise.name,
        'movement': entry.movement, 'label': entry.label,
        'movement_group': MOVEMENT_GROUP[entry.movement],
        'search': search_text(exercise),
        'picture': art.picture_url(exercise.library_key),
    }




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
        'default_rest_seconds': _to_rest_seconds,
        'stack_kg': _to_stack_steps,
        'bar_weight': _to_bar_weight,
    }
    submitted = {field: parse(request.form.get(field, ''))
                 for field, parse in parsers.items() if field in request.form}
    # The first save of an exercise's settings inserts their row; two at
    # once -- the keepalive save on leaving the page skips the client's queue
    # -- both found none and the second insert hit the unique key (G-136).
    lock_user(current_user_id())
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
    seconds = _to_rest_seconds(request.form.get('rest_seconds', ''))
    user_id = current_user_id()
    lock_user(user_id)   # its first write inserts the lifter's row: see gym_update_exercise
    set_rest_for_all(user_id, seconds)
    db.session.commit()
    if _wants_json():
        return jsonify(RestOverview.model_validate(rest_overview(user_id)).model_dump(mode='json'))
    return redirect(url_for('gym.gym_uebungen'))
