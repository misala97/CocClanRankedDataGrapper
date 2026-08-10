"""The gym JSON contracts: the exercise-detail page, and the live workout.

Each mirrors what its route already computes -- these type existing shapes
rather than designing new ones. The React pages in static/gym/src/ read
exactly these field names.

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


# ---------------------------------------------------------------------------
# The live workout screen.
#
# Mirrors what routes/workout.py:session_detail already computes for
# session_detail.html. Every type here was read off that function rather than
# inferred from the template -- the exercise-detail schema above was written
# the other way round and was wrong in five places.
# ---------------------------------------------------------------------------


class SessionMeta(_Model):
    """The session row itself. finished_at is always None here: a finished
    session renders session_finished.html, a different page with a different
    payload."""
    id: int
    name: str | None
    started_at: datetime
    finished_at: datetime | None
    is_deload: bool
    deload_pct: int | None
    rest_ends_at: datetime | None
    resting_set_id: int | None
    template_id: int | None
    template_name: str | None
    bodyweight_kg: float | None
    notes: str | None
    # What the follower's poll compares. reconcile_follower bumps it on the
    # FOLLOWER's session only, which is why a leader polling sync.json would
    # burn a request every 5s for a version that can never change.
    structure_version: int


class LiveSet(_Model):
    id: int
    weight: float
    reps: int
    completed: bool
    # Non-NULL exactly when this set's weight is deload-scaled. It is what
    # `deload_applied` is derived from -- the session's is_deload flag is not,
    # because a session flagged after a set was logged keeps its full weights.
    base_weight: float | None


class LiveExercise(_Model):
    """One row of the queue. `id` is the SessionExercise, `exercise_id` the
    catalogue entry -- suggestions and stagnation_counts are keyed by the
    former, records and history by the latter."""
    id: int
    exercise_id: int
    name: str
    muscle_group: str | None
    position: int
    skipped: bool
    is_unilateral: bool
    rest_seconds: int | None
    increment: float
    notes: str | None
    # A boolean flag ("this hurt"), not free text -- NOT NULL with a False
    # default, so never None. Typed str here first and the endpoint rejected
    # its own payload the moment a real session was fed through it.
    pain: bool
    sets: list[LiveSet]


class CatalogueExercise(_Model):
    """An entry in the add-exercise sheet's list."""
    id: int
    name: str
    muscle_group: str | None


class Suggestion(_Model):
    """What the steppers pre-fill with. None for an exercise with no history
    to seed from, so the containing dict's value is optional."""
    weight: float
    reps: int


class ReadyForMore(_Model):
    """`that weight went easy` -- only ever computed for the live exercise,
    and never during a deload."""
    sets: int
    weight: float
    is_latest: bool


class PartnerStatus(_Model):
    username: str
    accepted: bool


class Partner(_Model):
    id: int
    username: str


class SessionDetailPayload(_Model):
    session: SessionMeta
    visible_exercises: list[LiveExercise]
    # The SessionExercise that is live, or None when the session has no
    # visible exercises at all.
    live_id: int | None
    # 1-based position of the live exercise in visible_exercises; 0 when none.
    live_index: int
    live_increment: float

    # One entry per set in the whole workout, in order: 'done', 'now' or
    # 'open'. Sets belonging to a skipped exercise are omitted entirely.
    tick_states: list[str]
    sets_done: int
    sets_total: int
    sets_open: int
    session_volume: float

    resting: bool
    # 0 when nothing is resting, never None -- the progress bar divides by it.
    # Comes from the exercise that OWNS the resting set, not the live one.
    rest_total_seconds: int

    # Both keyed by SessionExercise.id. JSON object keys are always strings,
    # so model_dump(mode='json') emits '10', not 10 -- the client reads
    # string keys. Pinned by test_int_keyed_dicts_serialize_as_string_keys.
    suggestions: dict[str, Suggestion | None]
    stagnation_counts: dict[str, int]
    # A set in the route; a list here. json.dumps cannot serialize a set, so
    # the builder converts and this type is what makes that non-optional.
    record_set_ids: list[int]
    ready_for_more: ReadyForMore | None

    min_full_reps: int
    default_plan_weight: float
    default_plan_reps: int

    exercises: list[CatalogueExercise]
    muscle_groups: list[str]
    # None whenever VAPID_PUBLIC_KEY is unset in .env, which is the normal
    # state on a fresh checkout.
    vapid_public_key: str | None
    has_completed_set: bool

    deload_applied: bool
    deload_pcts: list[int]
    deload_default_pct: int

    partners: list[Partner]
    partner_status: list[PartnerStatus]
    session_is_shared: bool


# ---------------------------------------------------------------------------
# The exercise catalogue.
#
# Mirrors what routes/catalogue.py:gym_uebungen computes. The page's three
# sorts and its search are client-side re-orderings of these same rows, never a
# second round trip -- a lifter's catalogue is tens of rows.
# ---------------------------------------------------------------------------


class CatalogueEntry(_Model):
    """One row. `last_weight` is what you would load TODAY, which is the
    question a catalogue is opened with -- the row used to lead with the
    all-time best, unlabelled, so a personal record could not be told apart
    from a working weight."""
    exercise: ExerciseMeta
    chip_class: str | None
    chip_label: str | None
    last_done: datetime | None
    best_weight: float | None
    last_weight: float | None
    days_ago: int | None
    sessions_since_pr: int | None


class CatalogueGroup(_Model):
    """A muscle group and its exercises. Seeded from MUSCLE_GROUPS rather than
    from the catalogue, so a group with nothing in it still gets a band -- the
    strongest signal for the planning question was otherwise rendered as
    nothing at all."""
    name: str
    entries: list[CatalogueEntry]


class CataloguePayload(_Model):
    groups: list[CatalogueGroup]
    muscle_groups: list[str]
    equipment_labels: dict[str, str]
    # Above UEBUNGEN_FOLD_ABOVE the catalogue opens folded; at or below it
    # every group starts open. Hardcoded shut, the page's default state
    # contained no information about the catalogue's size.
    open_by_default: bool
    # What a blank rest field actually stores. The sheet's placeholder said 90.
    default_rest_seconds: int
    added_id: int | None
    name_taken: bool
