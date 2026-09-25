"""The single-exercise page (D9, M2): what to lift next, how far each weight
went, the estimated max as the Rekordtreppe, every workout, the exercise
itself.

The numbers are decided here and in stats/plan; the island only draws them.
The stair's pixels are the island's, because only it knows how wide the page
is -- a fixed viewBox scaled its 13px labels to 26px on a tablet."""

import datetime as dt

from flask import (
    jsonify, render_template, request,
)
from models import (
    EQUIPMENT_LABELS, Exercise,
)
from auth import (
    login_required,
)
from features.gym import art, plan, stats
from features.gym.exercises import (
    exercise_or_404, setup as exercise_setup,
)
from features.gym.library import (
    BY_KEY, LIBRARY,
)
from features.gym.scope import (
    current_user_id,
)
from features.gym.schemas import (
    ExerciseDetailPayload,
)
from .helpers import (
    EXERCISE_STATE_CHIP, _exercise_meta, _to_int,
)
from .history import (
    load_performed,
)
from ._blueprint import (
    gym_bp,
)


#: A slot earns an "Als N. Übung" pill with this many workouts in it: fewer
#: drew one-dot charts that read as a trend (D9, G-036).
MIN_WORKOUTS_FOR_PILL = 3


def _about(exercise):
    """The exercise itself: its drawing and the other variants of its
    movement, by label. Empty for an exercise off the list."""
    entry = BY_KEY.get(exercise.library_key) if exercise.library_key else None
    if entry is None:
        return {'picture': None, 'movement': None, 'variants': []}
    keys = [other.key for other in LIBRARY
            if other.movement == entry.movement and other.key != entry.key]
    variants = [{'id': other.id, 'label': BY_KEY[other.library_key].label}
                for other in Exercise.query.filter(Exercise.library_key.in_(keys)).all()]
    variants.sort(key=lambda variant: variant['label'].casefold())
    return {'picture': art.picture_url(exercise.library_key), 'movement': entry.movement,
            'variants': variants}


def _stairs(rows, state, since):
    """The Rekordtreppe for "Alle", then one per pill: [stair], and the pill
    slots. A slot needs MIN_WORKOUTS_FOR_PILL workouts and a stair of its
    own, and pills only exist for a lift done in more than one slot -- one
    pill would lens nothing."""
    whole = stats.record_stair(rows)
    if whole is None:
        return [], []
    stairs = [dict(whole, position=None, since=since, stalled=(state == 'stagniert'))]
    workouts = {}
    for row in rows:
        workouts.setdefault(row.position, set()).add(row.session_id)
    pills = []
    if len(workouts) > 1:
        for position in sorted(workouts):
            if len(workouts[position]) < MIN_WORKOUTS_FOR_PILL:
                continue
            stair = stats.record_stair(rows, position=position)
            if stair is None:
                continue
            # The drought is the lift's: under a pill the stair says no count.
            stairs.append(dict(stair, position=position, since=None, stalled=False))
            pills.append(position)
    return stairs, pills


def _exercise_detail_payload(exercise, raw_position):
    """Everything the exercise page shows, for one exercise and the pill in
    `?position=`. Shared by the HTML route and the JSON route.

    "Alle" is the default (D9): the page used to open on the slot it judged
    strongest and filter everything by it, which drew one-dot charts and a
    lit pill nobody pressed. Now every part is the whole exercise, and a pill
    lenses the Rekordtreppe only -- which is why each pill's stair comes with
    the page. `?position=N` opens on pill N; anything else opens on "Alle".
    """
    user_id = current_user_id()
    rows = load_performed(exercise_ids=[exercise.id])
    setup = exercise_setup(user_id, exercise)
    data = stats.exercise_progress(rows)
    stairs, pills = _stairs(rows, data['state'], data['sessions_since_pr'])
    position = _to_int(raw_position)
    chip_class, chip_label = EXERCISE_STATE_CHIP.get(data['state'], (None, None))
    return ExerciseDetailPayload.model_validate({
        'exercise': _exercise_meta(exercise, setup),
        'goal': plan.exercise_target(
            rows, user_id,
            stats.resolve_increment(setup.weight_increment, exercise.is_unilateral),
            setup.stack_kg),
        'weights': stats.weight_ladder(rows),
        'trend': stats.e1rm_trend(rows, dt.datetime.utcnow()),
        'stairs': stairs,
        'position_pills': pills,
        'selected_position': position if position in pills else None,
        'chip_class': chip_class,
        'chip_label': chip_label,
        'about': _about(exercise),
        # The settings sheet names the equipment; it no longer picks one.
        'equipment_labels': dict(EQUIPMENT_LABELS),
        **data,
    })


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = exercise_or_404(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    # mode='json' so datetimes are ISO strings the island can parse. `exercise`
    # is still passed separately because the shell's <title> block reads its
    # name before any JavaScript runs.
    return render_template(
        'gym/exercise_detail.html',
        exercise=exercise,
        payload_json=payload.model_dump(mode='json'),
    )


@gym_bp.route('/gym/exercises/<int:exercise_id>/detail.json')
@login_required
def gym_exercise_detail_json(exercise_id):
    """The exercise page as JSON: the same object the page embeds."""
    exercise = exercise_or_404(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return jsonify(payload.model_dump(mode='json'))
