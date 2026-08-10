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


# ---------------------------------------------------------------------------
# The history page.
#
# Mirrors what routes/reports.py:gym_verlauf computes. Search and the export
# selection are client-side over these same rows -- the page is the one surface
# that sees the whole history, and re-querying per keystroke would be absurd.
# ---------------------------------------------------------------------------


class HistoryEntry(_Model):
    """One finished session."""
    session_id: int
    name: str | None
    started_at: datetime
    finished_at: datetime | None
    is_deload: bool
    volume: float
    record_count: int
    # The same exercises the volume beside it was computed from. The row listed
    # every SessionExercise including ones swapped out mid-workout, so a
    # session showed 10 names next to a total built from 7.
    exercises: list[str]
    # Searchable date text, so a query like "31.07" or "juli" works. The
    # searchable string carried only the name and the exercises, and session
    # names stopped carrying the date -- so date search was degrading to
    # nothing as history accumulated.
    search_date: str
    # Days since the session AFTER this one in time. history is newest-first,
    # so the gap belongs to the row below the break. None on the newest row.
    gap_days: int | None


class HistoryMonth(_Model):
    """A month band. Grouped server-side because Jinja can detect a change of
    month while looping but cannot count a group it has not reached yet."""
    label: str
    slug: str
    entries: list[HistoryEntry]
    volume: float
    records: int


class HistoryPayload(_Model):
    months: list[HistoryMonth]
    total: int
    # A break this long or longer gets called out. Below it the date column
    # already tells the story; above it, a layoff was represented by nothing.
    gap_threshold: int
    # Stated rather than taken from strftime('%a'), which follows the server's
    # locale and not the UI's.
    weekday_short: list[str]


# ---------------------------------------------------------------------------
# The Start page.
#
# Mirrors what routes/workout.py:gym_heute computes. Every figure here comes
# from that route's single load_performed() call -- this page must never issue
# one query per session, however long the history gets.
# ---------------------------------------------------------------------------


class Consistency(_Model):
    sessions: int
    per_week: float
    days_since_last: int | None
    window_days: int


class RoutineMemory(_Model):
    """A routine and when it was last trained."""
    template_id: int
    name: str
    exercises: list[str]
    #: Parallel to `exercises`. The briefing intersects the lead routine with
    #: the stall roster, and it does so by id -- two exercises can carry the
    #: same name, and a name collision would report a stall the routine does
    #: not actually contain.
    exercise_ids: list[int]
    last_done: datetime | None
    days_ago: int | None


class RecentSession(_Model):
    session_id: int
    name: str | None
    started_at: datetime
    finished_at: datetime
    is_deload: bool
    volume: float
    records: int


class Stall(_Model):
    """A lift that has stopped moving. The roster this feeds is the whole
    catalogue's stalls; the deload signal below is a narrower read of the same
    data, limited to the active rotation."""
    exercise_id: int
    name: str
    position: int
    stuck_at: float
    since: datetime
    sessions_since_pr: int


class DeloadSuggestion(_Model):
    count: int
    stalls: list[Stall]


class MuscleBalance(_Model):
    """Seeded from the app's own vocabulary, not from whichever groups happen
    to own an exercise -- a group you have never built an exercise for could
    otherwise not appear, so the section that exists to say "you have quietly
    stopped training X" was structurally unable to name legs at all."""
    group: str
    sets: int
    volume: float
    share: float
    under_trained: bool


class TonnageWeek(_Model):
    week_start: datetime
    volume: float
    is_current: bool
    has_deload: bool


class PendingInvite(_Model):
    """Addressed to one person: an invite is only ever visible to its
    recipient."""
    shared_id: int
    leader_name: str
    session_name: str


class HeutePayload(_Model):
    now: datetime
    active_session_id: int | None
    active_session_name: str | None
    vapid_public_key: str | None
    consistency: Consistency
    routines: list[RoutineMemory]
    recent_sessions: list[RecentSession]
    stalls: list[Stall]
    deload_suggestion: DeloadSuggestion | None
    balance: list[MuscleBalance]
    tonnage: list[TonnageWeek]
    # The scale the bars are drawn against, named on the page so their heights
    # mean something. Also the empty-state gate: 0 means there is nothing to
    # chart, and the section says so instead of drawing eight stubs.
    tonnage_peak: float
    templates: list[RoutineMemory]
    pending_invites: list[PendingInvite]


# ---------------------------------------------------------------------------
# The finished workout (the debrief).
#
# session_detail() branches on finished_at and builds this from
# stats.session_report(), then bolts on what session_report structurally
# cannot know: the real SessionSet rows the correction sheet posts to, the
# session's own deload percentage, and the measured rest.
# ---------------------------------------------------------------------------


class FinishedSession(_Model):
    """The session row. finished_at is never None here -- that is the branch
    this page IS."""
    id: int
    name: str | None
    started_at: datetime
    finished_at: datetime
    is_deload: bool
    deload_pct: int | None
    bodyweight_kg: float | None
    notes: str | None
    template_id: int | None
    template_name: str | None


class CorrectableSet(_Model):
    """One completed set, as the correction sheet edits it. `id` is the real
    SessionSet, because that is what gym_update_set writes to -- session_report
    hands back bare (weight, reps) tuples and the sheet cannot post to those."""
    id: int
    weight: float
    reps: int


class FinishedExercise(_Model):
    """One row of the Nach-Übung list, and one group of the correction sheet.

    `sets` is session_report's own list of (weight, reps) pairs; `set_rows`
    are the same sets with their database ids, attached by the route. Both are
    carried: the display line is built from the former by stats.py, the sheet
    edits the latter.
    """
    exercise_id: int
    name: str
    position: int
    sets: list[tuple[float, int]]
    sets_display: str
    volume: float
    best_weight: float
    e1rm: float
    has_history: bool
    avg_volume: float | None
    volume_delta_pct: int | None
    is_weight_pr: bool
    is_volume_pr: bool
    is_e1rm_pr: bool
    sessions_since_pr: int | None
    # 'rekord' | 'stagniert' | 'steigend' | 'neu', or None -- a deload sets
    # every verdict to None, which is why the tag strip can be empty.
    verdict: str | None
    set_rows: list[CorrectableSet]
    # The per-exercise note and pain flag, which belong to the workout rather
    # than to the set values. None for an exercise with no SessionExercise
    # behind it, which the sheet renders as no form.
    session_exercise_id: int | None
    notes: str | None
    pain: bool


class SessionRecord(_Model):
    """One record this session set. Ranked by kind then by relative gain, so
    records[0] is the strongest claim rather than the biggest number."""
    kind: Literal['weight', 'e1rm', 'volume']
    name: str
    exercise_id: int
    position: int
    value: float
    previous: float
    previous_at: datetime


class SessionAdvice(_Model):
    """A plateau worth acting on next time. Only ever produced for a verdict of
    'stagniert', so a deload can never generate any."""
    exercise_id: int
    name: str
    stuck_at: float
    sessions: int
    suggested_weight: float


class PreviousSession(_Model):
    """The session before this one, of the same routine. A fact, next to the
    mean, which is a judgement."""
    id: int
    started_at: datetime
    volume: float


class FinishedPayload(_Model):
    session: FinishedSession
    exercises: list[FinishedExercise]
    total_volume: float
    total_sets: int
    avg_total_volume: float | None
    total_volume_delta_pct: int | None
    records: list[SessionRecord]
    record_count: int
    advice: list[SessionAdvice]
    is_deload: bool
    # No top-level deload_pct: session_report reports one as None for shape
    # stability, and the real value lives on the session row. Carrying it
    # under two names is how the header and the verdict came to read
    # different fields for the same number.
    deload_default_pct: int
    # Whether the percentage was actually applied to these weights. Flagging a
    # session retroactively never rewrites them, and without this the page
    # would quote a percentage of a working weight over the real numbers.
    deload_applied: bool
    previous_session: PreviousSession | None
    # One entry per logged set, in order: 'record' only for the single set that
    # lifted a WEIGHT record, 'done' for the rest.
    tick_states: list[Literal['record', 'done']]
    # Measured rest, not planned -- the gap between consecutive sets. None for
    # any session logged before completed_at existed, which the page renders as
    # silence rather than as zero.
    rest_taken_seconds: int | None
    weekday_short: list[str]
    # Celebrate on arrival, not on every later visit from Verlauf.
    just_finished: bool


# ---------------------------------------------------------------------------
# Statistik: the whole history, aggregated.
#
# Every model here mirrors one analytics.py return value. The `statable` flags
# are analytics' own: a section with too little evidence says so rather than
# stating a confident figure over three data points, and the page reads that
# flag rather than re-deciding the threshold for itself.
# ---------------------------------------------------------------------------


class BestSession(_Model):
    session_id: int
    started_at: datetime
    volume: float


class Totals(_Model):
    tonnage: float
    sets: int
    reps: int
    sessions: int
    # All three are None before the first logged set -- the page's own empty
    # state, not a zero.
    first_session: datetime | None
    days_training: int | None
    best_session: BestSession | None


class TonnageMonth(_Model):
    year: int
    month: int
    volume: float
    #: A month with no training at all, drawn as a break rather than as a zero.
    is_gap: bool
    has_deload: bool
    has_record: bool


class ProgressionRow(_Model):
    """One exercise's whole arc, with its sparkline already drawn.

    Geometry in Python for the same reason the exercise chart's is: an inline
    SVG inherits the palette where a canvas cannot, and the coordinate
    arithmetic has one home.
    """
    exercise_id: int
    name: str
    sessions: int
    first_e1rm: float
    current_e1rm: float
    change_pct: float
    best_weight: float
    points: list[float]
    #: SVG polyline points, from routes._progression_view.
    spark: str
    #: Half-width of the diverging bar, scaled against the largest absolute
    #: change on the page rather than against a fixed 100 %.
    bar_pct: float
    is_up: bool


class RepBucket(_Model):
    label: str
    sets: int
    share: float


class RepRange(_Model):
    buckets: list[RepBucket]
    sample: int
    dominant: RepBucket | None
    statable: bool
    #: Sets excluded from the distribution, counted so the page can say so.
    skipped: int


class Fatigue(_Model):
    """How much a lift drops off across a session."""
    sample: int
    statable: bool
    weight_change_pct: float | None
    first_reps: float | None
    last_reps: float | None


class DaypartBucket(_Model):
    #: 'morning' | 'evening' | 'other' -- keyed into DAYPART_NAMES for display.
    label: str
    sessions: int
    volume: float
    avg_volume: float


class Daypart(_Model):
    parts: list[DaypartBucket]
    statable: bool


class WeekdayBucket(_Model):
    #: Monday-first, matching WEEKDAY_NAMES.
    weekday: int
    sessions: int
    share: float


class Weekday(_Model):
    days: list[WeekdayBucket]
    sample: int
    statable: bool


class RestGapBucket(_Model):
    label: str
    sessions: int
    avg_volume: float


class RestGap(_Model):
    buckets: list[RestGapBucket]
    statable: bool


class EffortSlice(_Model):
    label: str
    volume: float
    sets: int
    share: float


class Effort(_Model):
    groups: list[EffortSlice]
    exercises: list[EffortSlice]
    total_volume: float


class RecordMove(_Model):
    value: float
    previous: float


class TimelineRecord(_Model):
    started_at: datetime
    session_id: int
    exercise_id: int
    name: str
    #: A session can set either kind, both, or -- for a row that is here at
    #: all -- at least one.
    weight: RecordMove | None
    e1rm: RecordMove | None


class RecordYear(_Model):
    year: int
    records: list[TimelineRecord]


class StatistikPayload(_Model):
    totals: Totals
    #: The only figure here not from analytics: cheap from the session dates
    #: the page has loaded anyway, and the fact that makes the lede worth
    #: reading.
    longest_gap: int
    months: list[TonnageMonth]
    progression: list[ProgressionRow]
    rep_range: RepRange
    min_sets_for_rep_range: int
    fatigue: Fatigue
    daypart: Daypart
    weekday: Weekday
    rest_gap: RestGap
    effort: Effort
    #: (planned, actual) medians in seconds, or None when there is nothing to
    #: report -- so the page says "noch keine Daten" instead of a confident 0.
    rest_habit: tuple[int, int] | None
    #: The newest RECENT_RECORDS shown flat; everything older folded into year
    #: bands. Bounded by COUNT, not by calendar: grouping by year assumes a
    #: history that spans years, and on 2 January the largest section on the
    #: page would have collapsed to one row.
    records_total: int
    recent_records: list[TimelineRecord]
    record_years: list[RecordYear]
    month_names: list[str]
    weekday_names: list[str]
    #: {'morning': 'Vormittags', ...} -- keyed by DaypartBucket.label.
    daypart_names: dict[str, str]
