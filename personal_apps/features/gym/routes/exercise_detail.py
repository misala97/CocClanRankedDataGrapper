"""The single-exercise page.

_chart_geometry turns history into SVG coordinates. Inline SVG rather than a
canvas, because a canvas can only read a resolved rgb() and a themed canvas
silently loses its colours -- this project has been bitten by that."""

from features.gym import stats

from flask import (
    jsonify, render_template, request,
)
from models import (
    EQUIPMENT_LABELS, MUSCLE_GROUPS,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    owned_exercise,
)
from features.gym.schemas import (
    ExerciseDetailPayload,
)
from .helpers import (
    EXERCISE_STATE_CHIP, _to_int,
)
from .history import (
    load_performed,
)
from ._blueprint import (
    gym_bp,
)


CHART_W = 320.0
CHART_H = 128.0
CHART_PAD = 10.0

# Smallest y range the chart will draw, in kg. See _chart_geometry.
CHART_MIN_SPAN = 5.0

# How far apart same-day sessions are nudged on the x axis, in viewBox units.
SAME_DAY_SPREAD = 16.0

# A slot needs this many sessions before its numbers count as a track record
# rather than one good day.
MIN_SESSIONS_FOR_DEFAULT_POSITION = 2


def _default_position(series):
    """Which slot the exercise page opens on.

    The best-performing one by best e1RM, restricted to slots with real history
    (see the constant above) so a single lucky session cannot become the default
    view. Falls back to the slot with the most sessions, then to None, which
    renders every slot at once.

    Returns (position, reason); the reason is what the page tells the reader,
    because a slot picked FOR them has to say on what grounds.
    """
    if not series:
        return None, None
    proven = [entry for entry in series
              if len(entry['points']) >= MIN_SESSIONS_FOR_DEFAULT_POSITION]
    if proven:
        # ties break toward the slot with more sessions, then the earlier slot
        best = max(proven, key=lambda entry: (
            max(point['e1rm'] for point in entry['points']),
            len(entry['points']),
            -entry['position'],
        ))
        return best['position'], 'strongest'
    fallback = max(series, key=lambda entry: (len(entry['points']), -entry['position']))
    return fallback['position'], 'most'


def _chart_geometry(series, pr_e1rm=None):
    """Turn exercise_progress()'s series into SVG coordinates.

    Computed here rather than in the template because Jinja doing coordinate
    arithmetic is unreadable, and because this replaces Chart.js: an inline SVG
    inherits the palette directly, which a canvas cannot -- it can only read
    resolved rgb(), so a themed canvas silently loses its colours (this project
    has hit that before).

    One polyline PER POSITION, not one for the whole exercise. The old chart
    drew a line per slot, and collapsing them would quietly drop a dimension:
    the same lift in slot 1 and slot 3 is two different stories.

    Deload points stay in the data -- dropping them would leave holes -- but are
    marked so the template can draw their legs dotted. A solid line through a
    deliberately light week reads as a collapse that never happened.
    """
    values = [point['e1rm'] for entry in series for point in entry['points']]
    if not values:
        return None
    data_lo, data_hi = min(values), max(values)

    # The axis is padded to a floor, and that is not cosmetic. Auto-fitting to
    # the data alone means the y range is whatever the data happens to span, so
    # 0,7 kg of drift over a year gets stretched across the full plot height and
    # draws as a cliff. Every chart looked equally dramatic and none of them
    # said how much. Below the floor the range is widened symmetrically around
    # its own midpoint, so a flat lift renders flat -- and the tick labels below
    # state the range either way, which is what actually makes the shape legible.
    lo, hi = data_lo, data_hi
    if hi - lo < CHART_MIN_SPAN:
        mid = (hi + lo) / 2.0
        lo, hi = mid - CHART_MIN_SPAN / 2.0, mid + CHART_MIN_SPAN / 2.0
    span = hi - lo

    # x comes from the DATE, not from the point's index within its own series.
    # Indexing looked right with one line and was wrong the moment a second
    # appeared: a slot with two sessions got spread across the same width as a
    # slot with seven, so the two lines were drawn on different time axes and
    # crossed each other for no reason. One shared date axis is the only way
    # two slots can be compared at all, which is the whole point of drawing
    # them together.
    stamps = [point['started_at'] for entry in series for point in entry['points']]
    first, last = min(stamps), max(stamps)
    days = (last - first).total_seconds() / 86400.0 or 1.0

    # Sessions on the SAME DAY land on the same x and stack into a vertical
    # line you cannot read. They are nudged apart by a few units each, keeping
    # chronological order -- the date still places the group, the offset only
    # separates its members. Small enough that it cannot be mistaken for elapsed
    # time: a whole day of sessions occupies less width than two days do.
    same_day = {}
    for entry in series:
        for point in entry['points']:
            key = point['started_at'].date()
            same_day.setdefault(key, []).append(point['started_at'])
    def _base_x(stamp):
        return CHART_PAD + ((stamp - first).total_seconds() / 86400.0) / days * (CHART_W - 2 * CHART_PAD)

    nudge = {}
    for stamps in same_day.values():
        ordered = sorted(set(stamps))
        if len(ordered) < 2:
            continue
        spread = min(SAME_DAY_SPREAD, (CHART_W - 2 * CHART_PAD) / 8)
        step = spread / (len(ordered) - 1)
        offsets = [-spread / 2 + index * step for index in range(len(ordered))]
        # A day sitting on either edge -- and the newest one always does -- gets
        # the whole group shifted inward rather than each member clamped, which
        # would silently re-stack the very points this is separating. The shift
        # is measured from the members' OWN positions: within one day each still
        # has its own base x, so testing only the first one left the last one
        # hanging past the edge.
        placed = [_base_x(stamp) + offset for stamp, offset in zip(ordered, offsets)]
        shift = 0.0
        if max(placed) > CHART_W - CHART_PAD:
            shift = (CHART_W - CHART_PAD) - max(placed)
        elif min(placed) < CHART_PAD:
            shift = CHART_PAD - min(placed)
        for stamp, offset in zip(ordered, offsets):
            nudge[stamp] = offset + shift

    out = []
    for entry in series:
        points = []
        for point in entry['points']:
            offset = (point['started_at'] - first).total_seconds() / 86400.0
            points.append({
                'x': round(min(max(
                    CHART_PAD + offset / days * (CHART_W - 2 * CHART_PAD)
                    + nudge.get(point['started_at'], 0.0),
                    0.0), CHART_W), 2),
                'y': round(CHART_H - CHART_PAD - (point['e1rm'] - lo) / span * (CHART_H - 2 * CHART_PAD), 2),
                'is_deload': point['is_deload'],
                'e1rm': point['e1rm'],
                'started_at': point['started_at'],
            })
        out.append({'position': entry['position'], 'points': points})

    # Every series is the same rose, because 4.3 fixes the palette at three
    # semantic hues and a slot number is not a semantic state. With three slots
    # overlapping that was unreadable, so they separate by WEIGHT instead: the
    # slot the exercise actually lives in (most sessions) draws solid, the
    # occasional ones recede. Each line also carries its slot number at its last
    # point, so the ordering is stated and not merely implied by opacity.
    out.sort(key=lambda entry: -len(entry['points']))
    for rank, entry in enumerate(out):
        # Floored at 0.65: a line is non-text UI and owes 3:1 against its panel.
        # Measured on the light scheme, which is the binding one -- --done over
        # the light chassis is 7.29:1 at full, 3.27:1 at 0.65 and 2.94:1 at 0.6.
        # The old ramp bottomed out at 0.3 (1.63:1), so the third slot was
        # decoration rather than data. Stroke width carries the separation that
        # opacity can no longer afford to.
        entry['opacity'] = 1.0 if rank == 0 else (0.8 if rank == 1 else 0.65)
        entry['width'] = 2.5 if rank == 0 else (1.9 if rank == 1 else 1.4)
        entry['is_main'] = (rank == 0)
        # `tip`, not `last`: the date-axis bounds above are named first/last and
        # rebinding one of them here silently fed a point dict to the date
        # arithmetic further down.
        tip = entry['points'][-1] if entry['points'] else None
        # The last point is usually AT the right edge, so a label placed to its
        # right lands outside the viewBox and is clipped. Flip to the left there
        # and lift it clear of the line either way.
        near_edge = tip is not None and tip['x'] > CHART_W - 34
        entry['label_x'] = round((tip['x'] - 8) if near_edge else (tip['x'] + 8), 2) if tip else 0
        entry['label_y'] = round(max(tip['y'] - 8, 12), 2) if tip else 0
        entry['label_anchor'] = 'end' if near_edge else 'start'

    # Slots that ran in the same weeks end at the same date, so their labels are
    # placed at nearly the same point and land on top of each other -- P5 was
    # drawn through P2. Push apart any pair that shares a horizontal
    # neighbourhood, working down the chart and folding upward at the floor.
    LABEL_GAP, LABEL_NEAR = 13.0, 40.0
    placed = []
    for entry in sorted((e for e in out if e['points']), key=lambda e: e['label_y']):
        for other in placed:
            if abs(entry['label_x'] - other['label_x']) >= LABEL_NEAR:
                continue
            if abs(entry['label_y'] - other['label_y']) < LABEL_GAP:
                entry['label_y'] = round(other['label_y'] + LABEL_GAP, 2)
        if entry['label_y'] > CHART_H - 4:
            entry['label_y'] = round(min(e['label_y'] for e in placed) - LABEL_GAP, 2) if placed else 12.0
        placed.append(entry)

    # The gold dot is the EXERCISE's best -- the same number the PR band above
    # the chart prints -- not the best of whatever happens to be plotted.
    #
    # Marking per series was the first bug: a position with a single session was
    # trivially its own best and got a record dot, so one chart carried two
    # golds and one of them meant nothing. Taking the max of the plotted points
    # fixed that and introduced the next one: under `?position=N` the plotted
    # set is one slot, so the slot's ceiling was promoted to "Rekord" and the
    # chart gold-dotted 85,8 while the band directly above it read 87,4.
    #
    # pr_e1rm comes from the UNFILTERED history (stats.exercise_progress), so a
    # filtered view that contains no record now correctly shows no gold at all.
    # A deload can never hold it, matching every other record rule here.
    candidates = [p for entry in out for p in entry['points'] if not p['is_deload']]
    if pr_e1rm is not None:
        best = pr_e1rm.get('e1rm') if isinstance(pr_e1rm, dict) else pr_e1rm
    else:
        best = max((p['e1rm'] for p in candidates), default=None)
    claimed = False
    for entry in out:
        for point in entry['points']:
            point['is_best'] = (
                best is not None and not claimed
                and not point['is_deload'] and point['e1rm'] == best
            )
            claimed = claimed or point['is_best']

    # One label per gridline, as a percentage of the viewBox so the HTML gutter
    # can sit beside the SVG and stay at text size instead of being scaled up
    # with the drawing.
    #
    # The decimal is kept whenever there is one. Rounding the top tick to whole
    # kg printed 87 directly under a record band reading 87,4 -- two numbers for
    # the same point, which reads as a discrepancy rather than as rounding.
    def fmt(value):
        text = '%.1f' % value
        return (text[:-2] if text.endswith('.0') else text).replace('.', ',')

    ticks = [{'y_pct': round(y / CHART_H * 100, 3), 'text': fmt(lo + span * frac)}
             for frac, y in ((1.0, CHART_PAD), (0.5, CHART_H / 2), (0.0, CHART_H - CHART_PAD))]

    # The middle date, not the middle ROW. The template took the median session
    # out of the table and printed it under the centre of the axis -- which was
    # right only while x came from the point's index. On a real date axis the
    # median session sits wherever its date puts it, so a run of three sessions
    # in one week followed by a month off printed a date under the midpoint that
    # was nowhere near it.
    #
    # Deduped, because an exercise whose whole history is one day -- or one slot
    # filtered down to a single date -- printed "31.07. 31.07. 31.07." across
    # the axis. Order is preserved, so three marks stay left/centre/right and a
    # collapsed range falls back to one.
    middle = first + (last - first) / 2
    dates = []
    for stamp in (first, middle, last):
        text = stats.to_local(stamp).strftime('%d.%m.')
        if text not in dates:
            dates.append(text)

    # What the legend is allowed to claim. A key for a mark that is not on the
    # chart is noise, and the deload key was on every chart in a database that
    # contains no deload at all.
    plotted = [p for entry in out for p in entry['points']]

    return {'series': out, 'lo': data_lo, 'hi': data_hi, 'axis_lo': lo, 'axis_hi': hi,
            'ticks': ticks, 'dates': dates, 'width': CHART_W, 'height': CHART_H,
            'has_deload': any(p['is_deload'] for p in plotted),
            'has_record': any(p['is_best'] for p in plotted)}


def _exercise_detail_payload(exercise, raw_position):
    """Everything the exercise page shows, for one exercise and one requested
    position.

    Shared by the HTML route and the JSON route so the default-slot rule below
    cannot drift between them -- two copies of it would disagree the first time
    either was touched, and the page and a refetch would then show different
    slots.

    The default view is one slot, not all of them. "Alle" draws every position
    at once, which is the comparison view -- useful when you want it, and a
    poor thing to land on: the answer to "how is this lift going" is a single
    line, and overlapping slots bury it.

    Which slot: the best-performing one, meaning highest best-e1RM -- but only
    among slots with at least two sessions. A slot used once is a data point,
    not a track record, and defaulting to it would show a flattering line
    built from a single lucky day. With nothing qualifying, fall back to the
    slot the exercise actually lives in (the most sessions).

    `?position=all` is how the page asks for the comparison view, so the
    default stays reachable in one click and the URL stays honest about what
    it is showing.
    """
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)

    default_reason = None
    if raw_position == 'all':
        position = None
    else:
        position = _to_int(raw_position)
        if position is None:
            position, default_reason = _default_position(
                stats.exercise_progress(rows, position=None)['series'])

    # Whether the page CHOSE this slot or was told to. Without it the chart and
    # the session list were silently filtered on arrival: a pill was lit that
    # the reader never pressed, and everything below it counted one slot while
    # reading like the whole exercise.
    position_is_default = (raw_position is None and position is not None)
    if not position_is_default:
        default_reason = None

    data = stats.exercise_progress(rows, position=position)
    chip_class, chip_label = EXERCISE_STATE_CHIP.get(data['state'], (None, None))
    return ExerciseDetailPayload.model_validate({
        'exercise': {
            'id': exercise.id,
            'name': exercise.name,
            'muscle_group': exercise.muscle_group,
            'is_unilateral': exercise.is_unilateral,
            'default_rest_seconds': exercise.default_rest_seconds,
            'weight_increment': exercise.weight_increment,
            'equipment': exercise.equipment,
            'bar_weight': exercise.bar_weight,
            'stack_kg': exercise.stack_kg,
            'secondary_muscle_groups': exercise.secondary_muscle_groups,
        },
        'selected_position_is_default': position_is_default,
        'selected_position_reason': default_reason,
        'chart': _chart_geometry(data['series'], data.get('pr_e1rm')),
        'chip_class': chip_class,
        'chip_label': chip_label,
        # Only offer deletion when nothing depends on it -- same test the
        # catalogue used before this moved off the list.
        'can_delete': not exercise.session_exercises and not exercise.template_exercises,
        'muscle_groups': list(MUSCLE_GROUPS),
        'equipment_labels': dict(EQUIPMENT_LABELS),
        **data,
    })


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = owned_exercise(exercise_id)
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
    """The full exercise page as JSON.

    Distinct from gym_exercise_progress_json below, which backs the in-workout
    quick-glance modal and deliberately falls back to all-time data when the
    requested slot is empty. This one honours the filter exactly, because the
    page's pills have to mean what they say.
    """
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return jsonify(payload.model_dump(mode='json'))


@gym_bp.route('/gym/exercises/<int:exercise_id>/progress.json')
@login_required
def gym_exercise_progress_json(exercise_id):
    """Backs the in-workout quick-glance modal. Scoped to a position when
    one is given (same slot in the workout order = comparable fatigue
    state), but unlike the full exercise page's explicit filter, this falls
    back to all-time data if that exact slot has no history yet -- the
    modal should always show *something* useful rather than an empty state
    just because you haven't done this exercise in this position before."""
    exercise = owned_exercise(exercise_id)
    position = request.args.get('position', type=int)
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)
    progress = stats.exercise_progress(rows, position=position)
    if position is not None and not progress['table']:
        progress = stats.exercise_progress(rows, position=None)

    def fmt_weight_pr(pr):
        if not pr:
            return None
        return {'weight': pr['weight'], 'reps': pr['reps'], 'position': pr['position'],
                'date': stats.to_local(pr['started_at']).strftime('%d.%m.%Y')}

    def fmt_e1rm_pr(pr):
        if not pr:
            return None
        return {'e1rm': pr['e1rm'], 'weight': pr['weight'], 'reps': pr['reps'], 'position': pr['position'],
                'date': stats.to_local(pr['started_at']).strftime('%d.%m.%Y')}

    return jsonify({
        'exercise_id': exercise.id,
        'name': exercise.name,
        'is_unilateral': exercise.is_unilateral,
        'selected_position': progress['selected_position'],
        'series': progress['series'],
        # The same geometry the exercise page draws from. The modal used to ship
        # raw series and let Chart.js lay them out on a category axis, which drew
        # a six-week gap and four same-day sessions at the same width -- so the
        # two charts in this app disagreed about what the x axis meant.
        'chart': _chart_geometry(progress['series'], progress.get('pr_e1rm')),
        'pr_weight': fmt_weight_pr(progress['pr_weight']),
        'pr_e1rm': fmt_e1rm_pr(progress['pr_e1rm']),
    })
