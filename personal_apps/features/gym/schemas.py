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


class ListDefaults(_Model):
    """The list's own values for the four personal settings -- what a blank
    field in the settings form stands for."""
    default_rest_seconds: int | None
    weight_increment: float | None
    bar_weight: float | None
    stack_kg: list[float] | None


class ExerciseMeta(_Model):
    """The exercise as this lifter sees it -- backs both the header and the
    settings sheet. Name, groups, equipment and one side are the list's;
    rest, step, bar and stack are the lifter's effective values."""
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
    list_defaults: ListDefaults
    #: The settings that are the lifter's own value, by field name -- for the
    #: rest an exception to `rest_for_all`, where they set one.
    own: list[Literal['weight_increment', 'default_rest_seconds', 'stack_kg', 'bar_weight']]
    #: The lifter's rest for all their exercises ("Deine Pause"), or None: by
    #: kind of exercise, the list's rest.
    rest_for_all: int | None


class RestException(_Model):
    """An exercise with a rest of its own, under "Deine Pause"."""
    exercise_id: int
    name: str
    rest_seconds: int


class RestOverview(_Model):
    """"Deine Pause" (exercises.rest_overview): the lifter's rest for all
    their exercises and what it comes with."""
    #: None: by kind of exercise, the list's rest for each.
    rest_for_all: int | None
    exceptions: list[RestException]
    #: Where "Eine für alle" starts from "Je nach Übungsart".
    start_seconds: int
    #: The list's range, which "Je nach Übungsart" means.
    list_min_seconds: int
    list_max_seconds: int
    #: The stepper's ends.
    min_seconds: int
    max_seconds: int


class SessionRow(_Model):
    """One performed session, as rendered in the Workouts log."""
    session_id: int
    started_at: datetime
    position: int
    is_deload: bool
    #: This workout's best e1RM beat every workout before it (D3). History:
    #: a record later overtaken keeps the tag.
    is_record: bool
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
    carried alongside for the readout. is_record as on SessionRow."""
    x: float
    y: float
    e1rm: float
    started_at: datetime
    is_record: bool
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


class ChartProjection(_Model):
    """The "bei diesem Tempo" overlay: the fitted trend of the main series,
    extended to the next round e1RM. None whenever any of the silence gates in
    stats.e1rm_projection holds -- a wrong date on a chart outlives any
    caveat, so absence is the default."""
    x1: float
    y1: float
    x2: float
    y2: float
    milestone: float
    date: datetime
    per_week: float


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
    projection: ChartProjection | None


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
    # None = not decided yet: an exercise with no history is planned blank
    # (seeding._seeded_sets). Never None on a completed set.
    weight: float | None
    reps: int | None
    completed: bool
    # Non-NULL exactly when this set's weight is deload-scaled. It is what
    # `deload_applied` is derived from -- the session's is_deload flag is not,
    # because a session flagged after a set was logged keeps its full weights.
    base_weight: float | None
    # The live screen's own name for a set it added (SessionSet.client_key):
    # how its outbox finds the real set behind the one it drew (B6). None on
    # every other set.
    key: str | None


class LiveBest(_Model):
    """The heaviest weight and the most reps an exercise has seen in the
    lifter's other finished workouts, raised by this one's counted sets: past
    twice either, a typed number gets a "Sicher?" before it is kept (Q5,
    G-070). The debrief carries it too (workout._typed_bests)."""
    weight: float
    reps: int


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
    # True while this row is the leader's structure in a live shared workout:
    # the follower's screen offers skip and substitute for it, never remove.
    mirrored: bool
    is_unilateral: bool
    #: This workout's own rest ("Pause heute"), or None: `rest_setting`.
    rest_seconds: int | None
    #: The lifter's rest for the exercise, what always applies: its own,
    #: else their rest for all, else the list's.
    rest_setting: int | None
    #: Whether `rest_setting` is the lifter's (own or for all) rather than
    #: the list's -- the mark under it says "deine" or "Liste".
    rest_setting_mine: bool
    increment: float
    #: Where a blank kg stepper's "+" lands for this row (live_floor, when it
    #: is live): the screen that moves on by itself offline needs it (B6).
    floor: float
    notes: str | None
    # A boolean flag ("this hurt"), not free text -- NOT NULL with a False
    # default, so never None. Typed str here first and the endpoint rejected
    # its own payload the moment a real session was fed through it.
    pain: bool
    #: LiveBest, or None before the exercise's first set: nothing to measure
    #: a typo against.
    best: LiveBest | None
    #: Where the exercise's drawing loads from (art.picture_url), or None
    #: while it has none -- off the list, or not drawn yet: the placeholder.
    picture: str | None
    #: The done sets (count, volume) of the hidden originals this row
    #: replaced, so the client's retally counts them in place (Q1). Zero
    #: where nothing was replaced.
    replaced_sets_done: int
    replaced_volume: float
    #: Stands in for a hidden original (replaces_id): removed, it brings that
    #: original back rather than leaving a gap.
    is_substitute: bool
    sets: list[LiveSet]


class CatalogueExercise(_Model):
    """An entry in the add-exercise sheet's list."""
    id: int
    name: str
    muscle_group: str | None
    #: The folded name and aliases (exercises.search_text). The sheet finds
    #: an entry when every word of the folded query occurs in it -- the
    #: library.matches contract, so English and umlaut-free typing work.
    search: str
    #: The movement it is a variant of and what sets it apart from the other
    #: variants: `Bankdrücken` and `Kurzhantel` of `Bankdrücken (Kurzhantel)`.
    movement: str
    label: str
    #: The section the sheet lists the movement under (library.MOVEMENT_GROUP),
    #: the same for all of its variants.
    movement_group: str
    #: This lifter's finished workouts with a completed set of it; 0 = never.
    workouts: int
    #: Calendar days since the last of them; None = never.
    days_ago: int | None
    #: 1 = what this lifter does most, recent weeks weighing more (exercises.
    #: usage); None = never done.
    rank: int | None
    #: Listed under "Deine" at the top of the sheet.
    common: bool


class Suggestion(_Model):
    """What the steppers pre-fill with. None for an exercise with no history
    to seed from, so the containing dict's value is optional."""
    weight: float
    reps: int


class SeedSource(_Model):
    """Which past workout a plan's numbers were taken from, and by which of
    seeding's rules -- so the screen can say so instead of leaving the lifter
    to guess why moving an exercise did or did not change its weights.

    `basis`: 'slot' -- the best fresh result at this slot or a later one;
    'earlier_slot' -- nothing fresh this late in a workout, so the best fresh
    result from an earlier, fresher slot (may run heavy); 'layoff' -- nothing
    fresh at all, so the most recent workout rather than the best."""
    date: datetime
    # The slot the exercise sat in during THAT workout.
    position: int
    basis: Literal['slot', 'earlier_slot', 'layoff']
    # That workout is also the newest one that counts (deloads left out):
    # the card may say "Letztes Mal" only then.
    is_latest: bool
    # What was lifted that day, in order -- the one line the card leads with.
    sets: list[Suggestion]


class LiveRecord(_Model):
    """What one just-logged set beat, for the record takeover to say.

    Only ever present for a set id that is also in record_set_ids -- the two
    are built from the same judgement in the same loop, so a detail without a
    gold chip (or the reverse) is a bug, not a state.

    `value` and `previous` are estimated one-rep-max kilograms: a record is
    e1RM only (D3), the same pair session_report's records print, so the live
    screen and the debrief never name one set's record two different ways."""
    kind: Literal['e1rm']
    value: float
    previous: float
    # The start of the session that held the old best.
    previous_at: datetime


class TargetSet(_Model):
    """One set of "what to lift" (stats.next_target): display only, never
    seeded."""
    weight: float
    reps: int


class RoutinePlan(_Model):
    """What the workout's routine keeps for one exercise (D2 P1): how many
    sets it plans and the rep range the target aims at."""
    sets: int
    rep_min: int
    rep_max: int


class VariantRef(_Model):
    """Another variant of a movement, as the lifter last did it: the top set
    of the latest workout (not a deload) that had it. `label` is the variant
    part of the name (library.Entry.label), `per_side` says the weight is one
    side's."""
    label: str
    weight: float
    reps: int
    per_side: bool


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
    # Where the live exercise's kg stepper lands when "+" is tapped on a blank
    # weight: the empty bar, the lightest stop of a known stack, else one
    # step. None when nothing is live.
    live_floor: float | None

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
    # Keyed the same way. None for an exercise with no history at all.
    seed_sources: dict[str, SeedSource | None]
    stagnation_counts: dict[str, int]
    #: Keyed like stagnation_counts: what to lift, set by set, for every
    #: exercise with a workout to build on (D2 P1). Empty in a deload.
    next_targets: dict[str, list[TargetSet]]
    #: Keyed the same way (D4): during a deload marked after the first set,
    #: the weight the deload would have planned for each exercise not started
    #: yet -- nothing rescales mid-workout. Empty otherwise.
    deload_hints: dict[str, float]
    #: Keyed the same way: the routine's plan for each exercise it holds,
    #: where the sheet's steppers start. Empty without a routine of your own.
    routine_plans: dict[str, RoutinePlan]
    #: Kept, saying nothing, for a page loaded before B5's deploy: its bundle
    #: reads both unguarded (the stall line's step-up, the "Bereit" line), and
    #: the first answer without them blanked the live screen mid-workout (B5
    #: review). Drop them in a batch after that deploy.
    stall_next_weight: dict[str, float] = {}
    ready_for_more: None = None
    # A set in the route; a list here. json.dumps cannot serialize a set, so
    # the builder converts and this type is what makes that non-optional.
    record_set_ids: list[int]
    # Keyed by Set.id, string-keyed on the wire like suggestions above. One
    # entry per id in record_set_ids and no others.
    record_details: dict[str, LiveRecord]
    # Keyed by SessionExercise.id like suggestions: the exercises the lifter
    # meets for the first time -- no history, nothing logged in this workout
    # yet. Each lists up to two of the lifter's other variants of the same
    # movement with their last numbers, most-done first; information only,
    # another variant's numbers are not this one's. Empty list when there are
    # none; absent key when the exercise is not a first time.
    first_time: dict[str, list[VariantRef]]

    # The add sheet's list, and its sections in the list's own order
    # (library.LIST_GROUPS): sent with the page and by detail.json, never in
    # a write's answer -- it was 47 of that answer's 52 KB, on every set tick,
    # and it cannot change under a running workout: its counts are of
    # finished workouts (walkthrough G-140). The island keeps the last one it
    # was given (session/api.ts). None only while being left out.
    exercises: list[CatalogueExercise] | None
    list_groups: list[str] | None
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
    #: The folded name and aliases the add sheet searches too (library.fold,
    #: exercises.search_text); the page adds the group's name.
    search: str
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
    # Above UEBUNGEN_FOLD_ABOVE the catalogue opens folded; at or below it
    # every group starts open. Hardcoded shut, the page's default state
    # contained no information about the catalogue's size.
    open_by_default: bool
    rest: RestOverview


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
    # Ended by the app three hours after its last set (D5): the row says so,
    # since its end is that set's time rather than a "Beenden".
    auto_finished: bool
    volume: float
    record_count: int
    # The same exercises the volume beside it was computed from. The row listed
    # every SessionExercise including ones swapped out mid-workout, so a
    # session showed 10 names next to a total built from 7.
    exercises: list[str]
    # The name and the date words ("push\n31.07.2026 juli 2026"), folded
    # apart (library.fold_apart): session names stopped carrying the date, so
    # date search was degrading to nothing as history accumulated. The
    # exercises' texts are HistoryPayload.exercise_search.
    search: str
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
    # Each listed exercise's search text by name -- the add sheet's, aliases
    # and all (exercises.search_text): once per exercise, not per row.
    exercise_search: dict[str, str]


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


class OnboardingLast(_Model):
    """The newest finished workout that logged something: step 1's receipt,
    and what step 2 saves as a routine."""
    session_id: int
    name: str | None
    started_at: datetime
    finished_at: datetime
    exercises: int


class Onboarding(_Model):
    # Finished workouts with at least one logged set -- the count every other
    # section of the page is built on, so the steps never disagree with them.
    workouts: int
    last: OnboardingLast | None


class HeutePayload(_Model):
    now: datetime
    active_session_id: int | None
    active_session_name: str | None
    # The card's clock must measure from the session's start, not from the
    # page render -- `now` measures the latter, and a card that says
    # "00:00:01 läuft" twenty minutes into a workout is worse than no clock.
    active_session_started_at: datetime | None
    # The resume-strip heuristic's answer to "what was I on", so the card can
    # say it without a navigation.
    active_session_exercise: str | None
    # Display target for the rest countdown; a stale value past the cap is the
    # client's problem to ignore, same as the Jinja strip.
    active_session_rest_ends_at: datetime | None
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
    # The first-run checklist. None once the account has a routine, or has
    # finished enough workouts without one that it is a way of training rather
    # than a step not yet taken.
    onboarding: Onboarding | None


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
    # Ended by the app, at its last set, three hours on (D5).
    auto_finished: bool
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


class UnloggedExercise(_Model):
    """An exercise the workout held but nothing was logged on -- the
    correction sheet can still add a set to it."""
    session_exercise_id: int
    name: str
    #: What a typed set is judged against, or None: no history (Q5).
    best: LiveBest | None


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
    #: This exercise's best e1RM here beat every earlier workout's (D3).
    is_record: bool
    sessions_since_pr: int | None
    # 'rekord' | 'stagniert' | 'steigend' | 'neu', or None -- a deload keeps
    # only 'rekord' (a record is a record, D3) and has no progress verdict
    # otherwise, which is why the tag strip can be empty.
    verdict: str | None
    set_rows: list[CorrectableSet]
    # The per-exercise note and pain flag, which belong to the workout rather
    # than to the set values. None for an exercise with no SessionExercise
    # behind it, which the sheet renders as no form.
    session_exercise_id: int | None
    notes: str | None
    pain: bool
    #: What a correction or "Nachtragen" is judged against, or None: no
    #: history (Q5).
    best: LiveBest | None


class SessionRecord(_Model):
    """One record this session set, one per exercise, e1RM only (D3). Ranked
    by relative gain, so records[0] is the strongest claim rather than the
    biggest number."""
    kind: Literal['e1rm']
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
    # One entry per logged set, in order: 'record' for every set whose e1RM
    # beat each earlier workout's (D3), 'done' for the rest.
    tick_states: list[Literal['record', 'done']]
    # Measured pace -- the average gap between consecutive sets, which holds
    # the rest AND the next set. None for any session logged before
    # completed_at existed, which the page renders as silence rather than zero.
    set_pace_seconds: int | None
    # Exercises of this workout with nothing logged, for the correction
    # sheet's add rows.
    unlogged: list[UnloggedExercise]
    weekday_short: list[str]
    # Celebrate on arrival, not on every later visit from Verlauf.
    just_finished: bool
    # The update prompt's diff, both halves: the template's current list, and
    # what updating it would write -- computed by the same function the route
    # writes with, so the preview cannot drift. Both None for freeform.
    template_exercises: list[str] | None
    template_next_exercises: list[str] | None


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
    #: The part of `volume` lifted in deload workouts.
    deload_volume: float
    #: Records set in the month (exercise-workouts, as the timeline counts).
    records: int


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
    #: change in its own window rather than against a fixed 100 %.
    bar_pct: float
    is_up: bool


class ProgressionWindow(_Model):
    """One window's ranking. `key` is one of 'all', '6m', '3m', '30d' -- an
    identifier, not a label: the component owns the German, exactly as it does
    for month and weekday names."""
    key: str
    entries: list[ProgressionRow]


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
    #: Per session, so the most-trained day does not win by arithmetic.
    avg_volume: float


class Weekday(_Model):
    days: list[WeekdayBucket]
    sample: int
    statable: bool


class RestGapBucket(_Model):
    label: str
    sessions: int
    avg_volume: float
    shown: bool


class RestGap(_Model):
    buckets: list[RestGapBucket]
    thin: list[RestGapBucket]
    statable: bool


class SessionLength(_Model):
    #: Timed sessions only. `untimed` counts the rest -- missing finish stamps
    #: and workouts left running -- so the page can say what the median is
    #: built from instead of implying it covers everything.
    sample: int
    untimed: int
    statable: bool
    median_minutes: int | None
    volume_per_minute: float | None


class Consistency(_Model):
    weeks_trained: int
    weeks_total: int
    share: float
    current_streak: int
    longest_streak: int
    statable: bool


class DriftGroup(_Model):
    label: str | None
    recent_share: float
    earlier_share: float
    delta: float


class BalanceDrift(_Model):
    window_days: int
    groups: list[DriftGroup]
    recent_sessions: int
    earlier_sessions: int
    statable: bool


class LadderRung(_Model):
    exercise_id: int
    name: str
    notches: int
    from_weight: float
    to_weight: float
    sessions: int


class IncrementLadder(_Model):
    exercises: list[LadderRung]
    total_notches: int
    statable: bool


class DroughtRow(_Model):
    exercise_id: int
    name: str
    sessions: int
    sessions_since: int
    #: None when the lift has never beaten its own debut.
    last_record_at: datetime | None


class RecordDrought(_Model):
    exercises: list[DroughtRow]
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
    #: A record is e1RM only (D3): the best the workout reached, and the
    #: best of every workout before it.
    e1rm: RecordMove


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
    #: All four windows, precomputed. The client swaps between them without a
    #: round trip, so they travel together.
    progression: list[ProgressionWindow]
    rep_range: RepRange
    min_sets_for_rep_range: int
    fatigue: Fatigue
    daypart: Daypart
    weekday: Weekday
    rest_gap: RestGap
    session_length: SessionLength
    consistency: Consistency
    balance_drift: BalanceDrift
    increment_ladder: IncrementLadder
    record_drought: RecordDrought
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


# ---------------------------------------------------------------------------
# The shared-workout confirm screen.
# ---------------------------------------------------------------------------


class SharedExercise(_Model):
    """One of the leader's exercises -- which, since the one list, the
    follower logs as it is."""
    id: int
    name: str


class ConfirmTemplate(_Model):
    """One of the FOLLOWER's own routines, offered as what this shared
    workout counts as on their side. The island ranks them by how many of
    the workout's exercises they hold."""
    id: int
    name: str
    exercise_ids: list[int]


class SharedConfirmPayload(_Model):
    shared_id: int
    leader_name: str
    #: The workout being joined, as the invite card on Start names it -- its
    #: name (None for a freeform one) and when the leader started it.
    session_name: str | None
    started_at: datetime | None
    #: Why this invite cannot be accepted, or None. Present means the form is
    #: replaced by the reason -- there is nothing to confirm.
    refusal: str | None
    #: Whether accepting throws away the lifter's own running workout. Only
    #: ever an empty one -- a logged set refuses the invite instead.
    discards_active: bool
    #: The leader's exercises in workout order, each once. Empty when the
    #: invite carries a refusal, or the leader has not added one yet.
    exercises: list[SharedExercise]
    #: The follower's routines, for booking this workout under one of them.
    #: Empty when the invite carries a refusal -- there is nothing to book.
    templates: list[ConfirmTemplate]
