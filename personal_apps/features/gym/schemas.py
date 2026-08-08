"""The exercise-detail JSON contract.

Mirrors what stats.exercise_progress() and routes._chart_geometry() already
return -- this types an existing shape rather than designing a new one. The
React page in static/gym/src/ reads exactly these field names.

Every model forbids extra fields on purpose. The schema is a mirror, not a
subset: a field added to stats.py and not to here should fail loudly at the
boundary rather than silently disappear from the payload and leave a blank
where a number belongs. tests/test_gym_schemas.py validates real output from
the dev database against these models for that reason.

Datetimes serialize as ISO 8601 through model_dump(mode='json'); the client
formats them for display, because German date formatting is a presentation
concern and the server should not decide it twice.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ExerciseMeta(_Model):
    """The editable identity of the exercise -- backs both the header and the
    edit sheet."""
    id: int
    name: str
    muscle_group: str | None
    is_unilateral: bool
    default_rest_seconds: int | None
    weight_increment: float | None
    equipment: str | None
    bar_weight: float | None
    stack_kg: list[float] | None
    secondary_muscle_groups: list[str] | None


class SessionRow(_Model):
    """One performed session, as rendered in the Einheiten log."""
    session_id: int
    started_at: datetime
    position: int
    is_deload: bool
    sets_display: str
    best_weight: float
    volume: float
    e1rm: float


class LastOverall(_Model):
    """Newest session of the WHOLE exercise, never scoped to the position
    filter -- identity metadata is not filtered."""
    started_at: datetime
    position: int


class WeightPR(_Model):
    """The heaviest single set ever logged. session_id is required:
    exercise_detail matches the record row on it, never on the date -- two
    sessions on one day both matched a date test and both went gold."""
    weight: float
    reps: int
    session_id: int
    started_at: datetime
    position: int


class E1rmPR(_Model):
    """The set with the highest estimated 1RM. Not always the heaviest one:
    more reps at less weight can estimate higher."""
    e1rm: float
    weight: float
    reps: int
    session_id: int
    started_at: datetime
    position: int


class ChartPoint(_Model):
    """One plotted session. x/y are SVG coordinates; e1rm and started_at are
    carried alongside because _chart_geometry computes is_best from them."""
    x: float
    y: float
    e1rm: float
    started_at: datetime
    is_best: bool
    is_deload: bool


class ChartTick(_Model):
    y_pct: float
    text: str


class ChartSeries(_Model):
    """One position slot. Series separate by weight rather than hue: the
    palette is fixed at three semantic hues and a slot number is not a state,
    so the slot with the most sessions draws solid and occasional ones
    recede."""
    position: int
    points: list[ChartPoint]
    opacity: float
    width: float
    is_main: bool
    label_x: float
    label_y: float
    # Only ever 'end' (label flipped left of a point near the right edge) or
    # 'start'. Narrowed so a third value added to _chart_geometry fails here
    # rather than reaching an SVG attribute that will not accept it.
    label_anchor: Literal['start', 'end']


class ChartGeometry(_Model):
    """SVG coordinates from routes._chart_geometry(). None when there is
    nothing to draw.

    lo/hi are the DATA range, which is what the accessible description quotes.
    axis_lo/axis_hi are the padded drawing range -- widened to a floor so a
    lift that drifted 0,7 kg over a year does not render as a cliff.
    """
    series: list[ChartSeries]
    lo: float
    hi: float
    axis_lo: float
    axis_hi: float
    ticks: list[ChartTick]
    # One or three entries: deduped, so an exercise whose whole history is one
    # day renders a single mark instead of the same date three times.
    dates: list[str]
    width: float
    height: float
    has_deload: bool
    has_record: bool


class ExerciseDetailPayload(_Model):
    exercise: ExerciseMeta
    table: list[SessionRow]
    # The pre-geometry series. Unread by the page, which draws from `chart`,
    # but carried so the payload stays a faithful dump of exercise_progress().
    series: list[dict]
    available_positions: list[int]
    selected_position: int | None
    selected_position_is_default: bool
    selected_position_reason: str | None
    last_overall: LastOverall | None
    pr_weight: WeightPR | None
    pr_e1rm: E1rmPR | None
    last_progression: SessionRow | None
    # 'neu' | 'rekord' | 'stagniert' | 'steigend', or None for stable --
    # exercise_state() documents None as a real answer, not an absence.
    state: str | None
    # None when there is too little history to say anything.
    sessions_since_pr: int | None
    chart: ChartGeometry | None
    chip_class: str | None
    chip_label: str | None
    can_delete: bool
    muscle_groups: list[str]
    equipment_labels: dict[str, str]
