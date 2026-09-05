import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import (
    BIGINT as MYSQL_BIGINT, DATETIME as MYSQL_DATETIME, MEDIUMTEXT)
from extensions import db


class QuizRound(db.Model):
    __tablename__ = 'quiz_rounds'
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    datum       = db.Column(db.DateTime)
    bilderrunde = db.Column(db.String(100))
    quizmaster  = db.Column(db.String(100))

    teams = db.relationship('QuizTeam', back_populates='round', lazy=True, cascade="all, delete-orphan")


class QuizTeam(db.Model):
    __tablename__ = 'quiz_teams'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name          = db.Column(db.String(100))
    round_id      = db.Column(db.Integer, db.ForeignKey('quiz_rounds.id'))
    round1_points = db.Column(db.Float)
    round2_points = db.Column(db.Float)
    round3_points = db.Column(db.Float)
    round4_points = db.Column(db.Float)
    round1_size   = db.Column(db.Integer)
    round2_size   = db.Column(db.Integer)
    round3_size   = db.Column(db.Integer)
    round4_size   = db.Column(db.Integer)

    round = db.relationship('QuizRound', back_populates='teams')


class ArchivedQuiz(db.Model):
    __tablename__ = 'archived_quizzes'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_date   = db.Column(db.Date, nullable=True)
    venue        = db.Column(db.String(150), nullable=True)
    quizmaster   = db.Column(db.String(150), nullable=True)
    notes        = db.Column(db.Text, nullable=True)

    rounds = db.relationship(
        'ArchivedQuizRound', back_populates='quiz', lazy=True,
        cascade="all, delete-orphan", order_by='ArchivedQuizRound.position',
    )


# Default template when creating a new quiz: 2x trivia, 1x picture, 1x music,
# 10 items each. Quizzes can deviate from this (rounds can be added, removed,
# or retyped, and round sizes aren't enforced) since the real format varies
# occasionally.
ROUND_TYPES = ('trivia', 'picture', 'music')
DEFAULT_ROUND_TEMPLATE = ('trivia', 'trivia', 'picture', 'music')

TRIVIA_CATEGORIES = (
    'Bücher & Wörter',
    'Comics',
    'Computerspiele',
    'Die 2000er',
    'Draußen im Grünen',
    'Essen & Trinken',
    'Glaube & Religion',
    'Im Labor',
    'Kinofilme',
    'Kunst & Kultur',
    'Körper & Geist',
    'Macht & Geld',
    'Medien & Unterhaltung',
    'Musik & Hits',
    'Rund um die Welt',
    'Sport & Freizeit',
    'TV-Serien',
    'Wunder der Technik',
    'Zeugen der Zeit',
)


class ArchivedQuizRound(db.Model):
    __tablename__ = 'archived_quiz_rounds'
    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    quiz_id        = db.Column(db.Integer, db.ForeignKey('archived_quizzes.id'), nullable=False)
    position       = db.Column(db.Integer, nullable=False, default=0)
    round_type     = db.Column(db.String(20), nullable=False)   # 'trivia' | 'picture' | 'music'
    topic          = db.Column(db.String(150), nullable=True)   # picture round topic
    image_filename = db.Column(db.String(255), nullable=True)   # picture round image

    quiz = db.relationship('ArchivedQuiz', back_populates='rounds')
    questions = db.relationship(
        'ArchivedQuizQuestion', back_populates='round', lazy=True,
        cascade="all, delete-orphan", order_by='ArchivedQuizQuestion.position',
    )
    songs = db.relationship(
        'ArchivedQuizSong', back_populates='round', lazy=True,
        cascade="all, delete-orphan", order_by='ArchivedQuizSong.position',
    )


class ArchivedQuizQuestion(db.Model):
    __tablename__ = 'archived_quiz_questions'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    round_id      = db.Column(db.Integer, db.ForeignKey('archived_quiz_rounds.id'), nullable=False)
    position      = db.Column(db.Integer, nullable=False, default=0)
    category      = db.Column(db.String(100), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    is_ai_reconstructed = db.Column(db.Boolean, nullable=False, default=False)  # question_text was AI-generated, not yet human-checked
    reconstructed_confidence = db.Column(db.String(20), nullable=True)  # 'high' | 'medium' | 'low' | 'unknown' — only meaningful while is_ai_reconstructed
    answer        = db.Column(db.Text, nullable=True)
    points        = db.Column(db.Float, nullable=True)

    round = db.relationship('ArchivedQuizRound', back_populates='questions')


class ArchivedQuizSong(db.Model):
    __tablename__ = 'archived_quiz_songs'
    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    round_id = db.Column(db.Integer, db.ForeignKey('archived_quiz_rounds.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    artist   = db.Column(db.String(200), nullable=True)
    title    = db.Column(db.String(200), nullable=True)

    round = db.relationship('ArchivedQuizRound', back_populates='songs')


class DeliveryShift(db.Model):
    __tablename__ = 'delivery_shifts'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shift_date   = db.Column(db.Date, nullable=False)
    shift_start  = db.Column(db.Time, nullable=True)
    shift_end    = db.Column(db.Time, nullable=True)
    hours_worked = db.Column(db.Float, nullable=False)
    tips_cash    = db.Column(db.Float, default=0)
    tips_online  = db.Column(db.Float, default=0)
    deliveries   = db.Column(db.Integer, default=0)
    trips        = db.Column(db.Integer, default=0)
    bike_size    = db.Column(db.String(10))   # 'small' | 'big'
    weather      = db.Column(db.String(20))   # 'clear' | 'rain' | 'heavy_rain' | 'snow' | 'thunderstorm' | 'hail' | 'heat'
    notes        = db.Column(db.Text, nullable=True)


# An active (unfinished) workout older than this is treated as abandoned and
# auto-finished the next time it's looked up, capped at started_at + this.
STALE_SESSION_TIMEOUT = dt.timedelta(hours=3)


MUSCLE_GROUPS = (
    'Bizeps', 'Trizeps', 'Brust', 'Rücken', 'Schultern',
    'Beine', 'Bauch', 'Gesäß', 'Waden', 'Unterarme', 'Cardio', 'Sonstiges',
)


# How an exercise is loaded. Two orthogonal facts describe a logged weight:
# this one, and is_unilateral below. Their combination is what the export's
# `weight_convention` is derived from -- storing that enum instead would put
# laterality in two places at once, and volume already depends on
# is_unilateral alone (stats.set_volume).
#
# A loaded barbell is `plate_loaded` with a bar_weight; it is not a value of
# its own, because "the bar is dead weight inside the number you logged" is
# exactly what bar_weight already says.
EQUIPMENT_TYPES = ('dumbbell', 'plate_loaded', 'stack')

EQUIPMENT_LABELS = {
    'dumbbell': 'Kurzhantel',
    'plate_loaded': 'Scheiben',
    'stack': 'Steckgewicht',
}


class Exercise(db.Model):
    __tablename__ = 'gym_exercises'
    # Owned per user since 2026-08-02: a third lifter joined who trains at the
    # same gym but shares none of the same exercises, so one global list meant
    # everyone's picker held everyone else's lifts. The cost is that the same
    # machine can now carry a different weight_increment per user, and nothing
    # reports the disagreement -- see the per-user-exercises design spec.
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_gym_exercises_user_id_name'),)
    id                   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    name                 = db.Column(db.String(150), nullable=False)
    previous_name        = db.Column(db.String(150), nullable=True)  # set to the prior name on rename, so anything still referencing the old name (e.g. historical data, or a rename made by mistake) can still resolve to this exercise instead of creating a duplicate
    muscle_group         = db.Column(db.String(100), nullable=True)
    default_rest_seconds = db.Column(db.Integer, nullable=True)
    weight_increment     = db.Column(db.Float, nullable=True)  # smallest loadable jump on this equipment (dumbbells 2, a stack often 9); NULL means use stats.DEFAULT_INCREMENT
    is_unilateral        = db.Column(db.Boolean, nullable=False, default=False)  # logged weight/reps are per side (e.g. one-arm curls); volume must be doubled
    equipment            = db.Column(db.String(20), nullable=False, default='stack',
                                     server_default='stack')  # one of EQUIPMENT_TYPES
    bar_weight           = db.Column(db.Float, nullable=True)   # dead weight (bar, carriage) already contained in the logged number
    # The real stops of an uneven stack, ascending. NULL on everything that
    # steps evenly -- weight_increment already answers those, and a list
    # spelling out 5,10,15,... would be the same fact typed twice. Mutually
    # exclusive with weight_increment in the export.
    stack_kg             = db.Column(db.JSON, nullable=True)
    # Values from MUSCLE_GROUPS. NULL and [] mean the same thing; readers
    # normalise to [].
    secondary_muscle_groups = db.Column(db.JSON, nullable=True)

    session_exercises  = db.relationship('SessionExercise', back_populates='exercise', lazy=True)
    template_exercises = db.relationship('TemplateExercise', back_populates='exercise', lazy=True)


class WorkoutTemplate(db.Model):
    __tablename__ = 'gym_workout_templates'
    id      = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name    = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)

    exercises = db.relationship(
        'TemplateExercise', back_populates='template', lazy=True,
        cascade="all, delete-orphan", order_by='TemplateExercise.position',
    )
    # Not cascading -- deleting a template must not delete past workout history.
    # The delete route nulls template_id on these instead of relying on the ORM.
    sessions_started_from = db.relationship('WorkoutSession', back_populates='template', lazy=True)


class TemplateExercise(db.Model):
    __tablename__ = 'gym_template_exercises'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_id  = db.Column(db.Integer, db.ForeignKey('gym_workout_templates.id'), nullable=False)
    exercise_id  = db.Column(db.Integer, db.ForeignKey('gym_exercises.id'), nullable=False)
    position     = db.Column(db.Integer, nullable=False, default=0)
    rest_seconds = db.Column(db.Integer, nullable=True)  # captured from the session's SessionExercise.rest_seconds when saved/updated

    template = db.relationship('WorkoutTemplate', back_populates='exercises')
    exercise = db.relationship('Exercise', back_populates='template_exercises')


class WorkoutSession(db.Model):
    __tablename__ = 'gym_workout_sessions'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name         = db.Column(db.String(150), nullable=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    template_id  = db.Column(db.Integer, db.ForeignKey('gym_workout_templates.id'), nullable=True)
    started_at   = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    finished_at  = db.Column(db.DateTime, nullable=True)
    rest_ends_at = db.Column(db.DateTime, nullable=True)  # display-only target for the in-page countdown
    resting_set_id = db.Column(db.Integer, db.ForeignKey('gym_session_sets.id'), nullable=True)  # which set's completion started the current rest timer, for the per-set progress bar
    # A deliberately light session. Excluded from every judgement that assumes
    # an attempt at progress (records, stagnation, volume averages, next
    # session's pre-fill) and kept in every figure where it is simply true
    # (tonnage, balance, consistency). See features/gym/stats.py.
    is_deload    = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    # The percentage of normal working weight actually used, stored per session
    # rather than read from a constant: changing the default later must not
    # retroactively rewrite what past sessions claim to have been, and it makes
    # deload depth a measurable variable. NULL on every non-deload session.
    deload_pct   = db.Column(db.SmallInteger, nullable=True)
    # Bumped whenever a shared workout's reconciliation actually changes this
    # session's structure. The follower's page polls it; an unchanged version
    # means the poll costs a few bytes and no re-render.
    structure_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # What the lifter weighed on the day of this workout. Deliberately per
    # session rather than a daily weigh-in log: every question worth asking
    # of it ("what did I weigh when I lifted this") is a question about a
    # session, and a second table would need its own screen, its own history
    # and its own gaps. NULL whenever it was skipped, which is most of them.
    bodyweight_kg = db.Column(db.Float, nullable=True)
    notes         = db.Column(db.Text, nullable=True)

    template = db.relationship('WorkoutTemplate', back_populates='sessions_started_from')
    exercises = db.relationship(
        'SessionExercise', back_populates='session', lazy=True,
        cascade="all, delete-orphan", order_by='SessionExercise.position',
    )
    pending_pushes = db.relationship('PendingPush', lazy=True, cascade="all, delete-orphan")


class SessionExercise(db.Model):
    __tablename__ = 'gym_session_exercises'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id   = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=False)
    exercise_id  = db.Column(db.Integer, db.ForeignKey('gym_exercises.id'), nullable=False)
    position     = db.Column(db.Integer, nullable=False, default=0)
    rest_seconds = db.Column(db.Integer, nullable=True)  # rest time for this exercise in this workout; seeded from Exercise.default_rest_seconds, editable per session
    replaces_id  = db.Column(db.Integer, db.ForeignKey('gym_session_exercises.id', ondelete='SET NULL'), nullable=True, unique=True)  # set when this row is a mid-workout substitute for another exercise in the same slot; unique so at most one substitute can ever point at a given original
    skipped      = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())  # True when this exercise is intentionally not being done this session; the row (and any already-completed sets) is kept as-is so a later "save/update as template" still includes it
    # The leader's SessionExercise this row mirrors, when this session is the
    # follower half of a shared workout. Reconciliation keys on this rather
    # than exercise_id: the two catalogues use different ids for the same
    # lift, and one exercise can legitimately appear twice in a session (an
    # original plus the substitute that replaced it). NULL on every ordinary
    # session, which is almost all of them.
    mirrors_id   = db.Column(db.Integer, db.ForeignKey('gym_session_exercises.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # A twinge, flagged with one tap. Deliberately a boolean and not a
    # description: mid-set is the worst possible moment to ask for prose, and
    # "something hurt here" is already the whole signal a later reader needs
    # to go looking.
    pain  = db.Column(db.Boolean, nullable=False, default=False,
                      server_default=sa.false())

    session  = db.relationship('WorkoutSession', back_populates='exercises')
    exercise = db.relationship('Exercise', back_populates='session_exercises')
    # self-referential: `replaces` points at the original exercise this substitutes for;
    # `replaced_by` (backref) points the other way, so the original can tell it's been superseded.
    # foreign_keys pinned to replaces_id: mirrors_id is a second self-referential FK on this
    # table, so the join condition is no longer unambiguous without it.
    replaces = db.relationship('SessionExercise', remote_side=[id], foreign_keys=[replaces_id],
                               backref=db.backref('replaced_by', uselist=False))
    sets = db.relationship(
        'SessionSet', back_populates='session_exercise', lazy=True,
        cascade="all, delete-orphan", order_by='SessionSet.position',
    )


class SessionSet(db.Model):
    __tablename__ = 'gym_session_sets'
    id                  = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_exercise_id = db.Column(db.Integer, db.ForeignKey('gym_session_exercises.id'), nullable=False)
    position            = db.Column(db.Integer, nullable=False, default=0)
    weight              = db.Column(db.Float, nullable=False)
    reps                = db.Column(db.Integer, nullable=False)
    completed           = db.Column(db.Boolean, nullable=False, default=False)  # False for sets pre-filled from a template/history and not yet actually performed this session
    # When this set actually landed. The rest between two sets is the gap
    # between their stamps, which is the only way the app can compare the rest
    # you planned against the rest you took -- rest_ends_at is a display target
    # for the countdown, not a record that anything happened.
    #
    # Cleared whenever the set stops being completed: a stale stamp would make
    # a re-tick measure however long you spent deciding.
    completed_at        = db.Column(db.DateTime, nullable=True)
    # The working weight this set held before a deload rewrote it. The
    # invariant this column actually maintains: it is non-NULL exactly when
    # `weight` currently holds a deload-scaled value, and NULL whenever
    # `weight` is the real working weight. Persisted rather than re-derived
    # so the deload toggle is idempotent (re-applying it, or changing the
    # percentage, always scales from the baseline instead of compounding)
    # and exactly reversible even for an exercise with no history to re-seed
    # from.
    #
    # Do NOT read `base_weight IS NOT NULL` as "this set belongs to a deload
    # session" -- the completed-set gate in gym_toggle_deload can leave it
    # set after the session's `is_deload` flag has been toggled back off
    # (nothing actually lifted is ever overwritten), and a session marked
    # deload retroactively, after every set was already logged, never
    # touches `base_weight` at all. The session's own `is_deload` flag is
    # the only thing that answers "is this a deload session".
    #
    # A hand-typed weight also clears it: gym_toggle_set_complete and
    # gym_update_set drop the baseline when the submitted weight differs from
    # the stored one, because the typed number becomes ground truth and a
    # later toggle-off must not overwrite it. An unchanged submitted value is
    # the form echoing itself (the weight input and the check button share one
    # form) and deliberately does not count -- otherwise ticking a set done
    # and undoing it would lose its working weight for good. The corollary:
    # deliberately retyping the same number reads as "no change", so the
    # baseline survives it. Distinguishing the two would need a dirty flag
    # from the client and is not worth it.
    base_weight         = db.Column(db.Float, nullable=True)
    # The rep count this set held before a deload rewrote it to
    # stats.DELOAD_REPS. Every rule above for base_weight applies here
    # unchanged -- same invariant, same idempotence, same clearing on a
    # hand-typed value -- because the two are written and read as a pair:
    # a deload prescribes a weight AND a rep count, and toggling it back off
    # has to return both.
    base_reps           = db.Column(db.Integer, nullable=True)
    # True for exactly the sets _seeded_sets invents when an exercise has no
    # history at all (stats.DEFAULT_PLAN_WEIGHT/REPS) -- never for a set
    # seeded from real history, and never for one a lifter actually logged.
    #
    # gym_toggle_deload reads this to refuse to scale these sets: a deload is
    # a percentage of a real working weight, and there isn't one here, so
    # scaling the placeholder would dress it up as a prescription (that
    # invariant used to depend on `weight` never happening to already equal
    # the default, and on the toggle always running before the exercise was
    # added -- both false in general, so it needed its own column rather than
    # being inferred).
    #
    # Cleared the same moment base_weight/base_reps are, and for the same
    # reason: a hand-typed weight is ground truth from now on, so the number
    # stops being invented and a later deload is free to treat it like any
    # other real set.
    is_default_seeded  = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())

    session_exercise = db.relationship('SessionExercise', back_populates='sets')


class SharedSession(db.Model):
    """One live workout carried across to a training partner.

    Two people training together share structure -- which exercises, in what
    order -- and nothing else. Weight and reps are the one thing that cannot
    transfer between two bodies, so each side owns an ordinary WorkoutSession
    and this row only links them.

    State is derived from the timestamps rather than a status column:
    pending (accepted_at IS NULL), active (accepted, ended_at IS NULL), ended.
    """
    __tablename__ = 'gym_shared_sessions'
    id                  = db.Column(db.Integer, primary_key=True, autoincrement=True)
    leader_session_id   = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=False, index=True)
    # NULL until the invite is accepted: the follower's session does not exist
    # before then, because it is seeded from the leader's structure at accept
    # time rather than at invite time.
    follower_session_id = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=True)
    leader_user_id      = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    follower_user_id    = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    created_at          = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    accepted_at         = db.Column(db.DateTime, nullable=True)
    # Stamped when EITHER session finishes, whichever comes first. Propagation
    # stops from that moment; the follower trains on alone.
    ended_at            = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        # Inviting the same person twice to the same workout re-surfaces the
        # existing invite instead of creating a second one.
        db.UniqueConstraint('leader_session_id', 'follower_user_id',
                            name='uq_gym_shared_sessions_leader_session_follower'),
    )

    exercise_map = db.relationship('SharedSessionExercise', lazy=True,
                                   cascade="all, delete-orphan")


class SharedSessionExercise(db.Model):
    """One exercise, named twice.

    Exercises became per-user on 2026-08-02, so "Bankdruecken" in two
    catalogues is two rows with two ids. A structural change expressed in the
    leader's ids means nothing against the follower's data without this.
    """
    __tablename__ = 'gym_shared_session_exercises'
    id                   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shared_session_id    = db.Column(db.Integer, db.ForeignKey('gym_shared_sessions.id'), nullable=False, index=True)
    # CASCADE on both: a spent link's map row is not a reason to keep a
    # catalogue entry alive. An exercise can end up referenced ONLY by this
    # map -- e.g. the follower confirms "new" for an exercise the leader
    # removed in the meantime, so a catalogue entry and a mapping row are
    # created but no SessionExercise ever is -- and gym_delete_exercise only
    # checks session_exercises/template_exercises, so without CASCADE that
    # exercise could never be deleted without an unhandled IntegrityError.
    leader_exercise_id   = db.Column(db.Integer, db.ForeignKey('gym_exercises.id', ondelete='CASCADE'), nullable=False)
    follower_exercise_id = db.Column(db.Integer, db.ForeignKey('gym_exercises.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('shared_session_id', 'leader_exercise_id',
                            name='uq_gym_shared_session_exercises_link_leader'),
    )


class PushSubscription(db.Model):
    __tablename__ = 'gym_push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # A root with no parent to inherit from -- and the reason this column
    # exists at all: push delivery used to fan out to every row, which
    # without it would buzz the wrong person's phone.
    user_id    = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    endpoint   = db.Column(db.String(500), nullable=False, unique=True)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key   = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    # The last time the device holding this endpoint said it still holds it --
    # refreshed by the subscribe route, which both pages post to on load with
    # whatever subscription the browser already has.
    #
    # This exists because a browser can replace its own endpoint (a reinstall,
    # cleared site data, a rotation) and the row for the old one stays behind
    # with nothing to invalidate it: the endpoint is still valid as far as the
    # push service is concerned, so it never 404s into the pruning in push.py.
    # Every notification fans out to every row, so a lifter with one phone was
    # getting two buzzes -- measured in production at four rows for one
    # account, two per device. Silence is the only signal an orphan gives off,
    # so silence is what it is judged on.
    last_seen_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)


class PendingPush(db.Model):
    # Queue table polled by the standalone run_gym_notifier.py daemon. This
    # decouples push delivery from the web app's gunicorn worker count --
    # an in-process scheduler would risk duplicate/lost jobs across workers.
    __tablename__ = 'gym_pending_pushes'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=False)
    fire_at    = db.Column(db.DateTime, nullable=False)
    sent       = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)


class AppUser(db.Model):
    # personal_apps had exactly one user until 2026-08-02: authentication was a
    # single credential pair compared against the environment. This table is
    # what "belongs to someone" now means -- see gym_workout_sessions.user_id.
    __tablename__ = 'app_user'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    # The whole permission model: an admin sees every app, a non-admin sees
    # Gym only. A per-app permission table is the thing to add if a third
    # person ever needs a different slice -- not before.
    is_admin      = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())


class TickerUniverse(db.Model):
    """Every symbol extraction is allowed to match.

    symbol is utf8mb4_bin so lookups are case-sensitive -- 'it' must not match
    ticker IT. Extraction uppercases candidates before it gets here.

    first_seen / delisted_at exist for symbol reassignment: a delisted symbol
    later given to a different company would otherwise inherit the old
    company's baseline, silently.
    """
    __tablename__ = 'radar_ticker_universe'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol      = db.Column(db.String(12, collation='utf8mb4_bin'),
                            nullable=False, unique=True, index=True)
    name        = db.Column(db.String(255), nullable=True)
    exchange    = db.Column(db.String(32), nullable=True)
    # Y/N from the Nasdaq Trader directory files, which is the only
    # authoritative answer available: a fund has no market cap to look
    # up, so nothing downstream can infer it, and the names do not carry
    # it reliably -- `Invesco QQQ Trust` and `SPDR Dow Jones Industrial`
    # contain no fund word at all.
    #
    # NULL means the directory has not been read for this row yet, which
    # is not the same as False. segment_for falls back to the name
    # pattern there rather than asserting it is a stock.
    is_etf      = db.Column(db.Boolean, nullable=True)
    first_seen  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    delisted_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)

    # From the provider's profile call, refreshed weekly. Market cap drives the
    # segment tabs; the earnings date drives the proximity slice, since a large
    # share of mention spikes are simply scheduled.
    #
    # Numeric(20, 2) because mega caps run into the trillions -- Apple reports
    # 4543167.94 million, which is 4.5e12 and overflows an INTEGER.
    market_cap           = db.Column(db.Numeric(20, 2), nullable=True)

    # Standard deviation of daily returns, from the daily-close provider.
    # Stored rather than computed on demand: divergence needs it for every row
    # of every page load, and it moves on the scale of weeks.
    daily_sigma          = db.Column(db.Float, nullable=True)
    sigma_refreshed_at   = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    ipo_date             = db.Column(db.Date, nullable=True)
    next_earnings_date   = db.Column(db.Date, nullable=True)
    profile_refreshed_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)


class RadarInstrument(db.Model):
    """One venue-specific price instrument beneath a Radar ticker.

    `TickerUniverse.symbol` remains the social identity. This table answers a
    different question: which actual instrument supplies a price in one market
    and currency. The mapping may be unverified during the compatibility
    window, but venue and currency are never inferred by a reader from a price.
    """
    __tablename__ = 'radar_instruments'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'market', 'mic',
                            name='uq_radar_instrument'),
        db.CheckConstraint("market IN ('us', 'de')",
                           name='ck_radar_instrument_market'),
        db.Index('ix_radar_instrument_primary',
                 'ticker', 'market', 'is_primary'),
        db.Index('ix_radar_instruments_history_due',
                 'market', 'history_due_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    id              = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    ticker          = db.Column(db.String(12, collation='utf8mb4_bin'),
                                nullable=False)
    market          = db.Column(db.String(2), nullable=False)
    venue           = db.Column(db.String(48), nullable=False)
    mic             = db.Column(db.String(4), nullable=False)
    provider_symbol = db.Column(db.String(32), nullable=False)
    currency        = db.Column(db.String(3), nullable=False)
    isin            = db.Column(db.String(12), nullable=True)
    is_primary      = db.Column(db.Boolean, nullable=False, default=False)
    mapping_status  = db.Column(db.String(12), nullable=False)
    mapping_source  = db.Column(db.String(24), nullable=True)
    mapped_at       = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    # Which atomic mapping generation last wrote this German row; NULL for
    # legacy rows and for US rows, which the generation machinery never owns.
    mapping_generation_id = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        db.ForeignKey('radar_mapping_generations.id',
                      name='fk_radar_instrument_generation'),
        nullable=True)
    # When this instrument's daily history is next worth fetching. NULL means
    # never fetched, which sorts first: a ticker the panel cannot draw at all
    # outranks one whose last close is a day stale.
    #
    # A durable schedule rather than a per-cycle ranking. The history job used
    # to select from the loudest hundred tickers by chatter, so a ticker that
    # had never been loud was unreachable however long it sat on the board --
    # 10,676 of 12,599 active tickers had no stored close on 2026-09-04.
    history_due_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)


class RadarPost(db.Model):
    """One ingested post or comment. 30-day rolling retention.

    body is MEDIUMTEXT: Reddit self-posts reach 40k characters, which is over
    the 64KB TEXT limit once utf8mb4 puts up to 4 bytes behind each one.
    """
    __tablename__ = 'radar_posts'
    __table_args__ = (
        db.UniqueConstraint('source', 'external_id', name='uq_radar_post_source_ext'),
        db.Index('ix_radar_posts_created_utc', 'created_utc'),
        {'mysql_charset': 'utf8mb4'},
    )

    id           = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    # Reddit carries the subreddit in the durable source name.
    source       = db.Column(db.String(48), nullable=False)
    # 128, not 32: a Bluesky id is 'bluesky:<did>:<rkey>' and a DID alone is
    # 32 characters. The original width was sized for Reddit fullnames.
    external_id  = db.Column(db.String(128), nullable=False)
    channel      = db.Column(db.String(64), nullable=False)
    author       = db.Column(db.String(64), nullable=True)
    created_utc  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    title        = db.Column(db.String(512), nullable=True)
    body         = db.Column(MEDIUMTEXT, nullable=True)
    score        = db.Column(db.Integer, nullable=False, default=0)
    num_comments = db.Column(db.Integer, nullable=False, default=0)
    url          = db.Column(db.String(512), nullable=True)
    # UNSIGNED, because simhash64() fills all 64 bits and a signed
    # BIGINT tops out at 2**63-1. Signed, roughly half of real posts
    # would be rejected outright -- decided entirely by their text,
    # which makes it look intermittent rather than systematic.
    simhash      = db.Column(MYSQL_BIGINT(unsigned=True),
                             nullable=False, default=0)
    first_seen   = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    last_seen    = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)

    mentions = db.relationship('RadarMention', back_populates='post',
                               cascade='all, delete-orphan', lazy=True)


class RadarMention(db.Model):
    """One (post x ticker). Follows its post's retention."""
    __tablename__ = 'radar_mentions'
    __table_args__ = (
        db.Index('ix_radar_mentions_ticker_post', 'ticker', 'post_id'),
        db.Index('ix_radar_mentions_post', 'post_id'),
        db.Index('ix_radar_mentions_judged', 'confidence', 'sentiment_judged_at'),
        db.CheckConstraint(
            "sentiment_relevance IS NULL OR sentiment_relevance IN "
            "('relevant','irrelevant','uncertain')",
            name='ck_radar_mentions_relevance'),
        db.CheckConstraint(
            "sentiment_content_origin IS NULL OR sentiment_content_origin IN "
            "('human_chatter','broadcast_or_automated','uncertain')",
            name='ck_radar_mentions_origin'),
        db.CheckConstraint(
            "sentiment_attitude IS NULL OR sentiment_attitude IN "
            "('positive','negative','mixed','none')",
            name='ck_radar_mentions_attitude'),
        db.CheckConstraint(
            "sentiment_expected_move IS NULL OR sentiment_expected_move IN "
            "('up','down','flat','unknown')",
            name='ck_radar_mentions_move'),
        db.CheckConstraint(
            "sentiment_confidence IS NULL OR sentiment_confidence IN "
            "('high','medium','low')",
            name='ck_radar_mentions_conf'),
        {'mysql_charset': 'utf8mb4'},
    )

    id               = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    post_id          = db.Column(db.BigInteger,
                                 db.ForeignKey('radar_posts.id', ondelete='CASCADE'),
                                 nullable=False)
    ticker           = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    # `low` is a bare token nothing has corroborated. Stored but never scored
    # (spec 4.2) -- keeping it is what lets the extractor's own false-positive
    # rate be measured against real data instead of argued about. `medium` is
    # awarded at rollup, when another author cashtags the same ticker in the
    # same window.
    confidence       = db.Column(
        db.Enum('high', 'medium', 'low', name='radar_confidence'),
        nullable=False)
    lexicon_sentiment = db.Column(db.Float, nullable=True)
    llm_sentiment     = db.Column(db.String(16), nullable=True)

    # ---- sentiment v2 (spec 2026-08-31 §6). Materialized FINAL result the
    # board reads; the append-only history lives in RadarSentimentJudgment.
    # Nullable strings + CHECK, not ENUM: additive, and MariaDB ENUM
    # widening is a rewrite. llm_sentiment above stays as the written
    # compatibility projection until the cleanup release.
    sentiment_relevance      = db.Column(db.String(12), nullable=True)
    sentiment_content_origin = db.Column(db.String(24), nullable=True)
    sentiment_attitude       = db.Column(db.String(8), nullable=True)
    sentiment_expected_move  = db.Column(db.String(8), nullable=True)
    sentiment_confidence     = db.Column(db.String(8), nullable=True)
    sentiment_model          = db.Column(db.String(40), nullable=True)
    # 64, not 16: spec §5.2.1 version strings are long, e.g.
    # 'radar-sentiment-v2-attitude-origin-candidate-1' (46 chars).
    sentiment_prompt_version = db.Column(db.String(64), nullable=True)
    sentiment_judged_at      = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    local_sentiment_model_version = db.Column(db.String(24), nullable=True)
    # First time the review triggers selected this mention. The dedupe
    # anchor for the review meter: demanded/capped increment only when
    # this is first stamped, so a candidate waiting across scheduler
    # passes is never recounted.
    review_requested_at      = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)

    post = db.relationship('RadarPost', back_populates='mentions')


class RadarBucket(db.Model):
    """(ticker x 15 minutes). Retained forever; this is what scoring reads.

    Status is per source, not per bucket. With one column and two sources,
    Bluesky dropping while Reddit keeps working forces a choice between
    discarding good Reddit data and silently halving the count -- the second
    being exactly the baseline poisoning the status column exists to prevent
    (spec 4.5).

    The mention_z_* and baseline_days_* columns are written by Plan 2 and are
    NULL until then.
    """
    __tablename__ = 'radar_buckets'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'bucket_start', name='uq_radar_bucket'),
        db.Index('ix_radar_buckets_start_ticker', 'bucket_start', 'ticker'),
        {'mysql_charset': 'utf8mb4'},
    )

    # The primary key is composite because this table is partitioned by
    # bucket_start, and MariaDB requires every unique key -- the primary key
    # included -- to contain every partitioning column. A bare `id` primary key
    # makes the partition ALTER fail with errno 1503. `id` stays leftmost so it
    # can still carry AUTO_INCREMENT.
    id                        = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    bucket_start              = db.Column(MYSQL_DATETIME(fsp=6), primary_key=True, nullable=False)

    mention_count             = db.Column(db.Integer, nullable=False, default=0)
    high_confidence_count     = db.Column(db.Integer, nullable=False, default=0)
    distinct_authors          = db.Column(db.Integer, nullable=False, default=0)
    distinct_text_ratio       = db.Column(db.Float, nullable=False, default=1.0)
    engagement_weighted_count = db.Column(db.Float, nullable=False, default=0.0)
    sentiment_mean            = db.Column(db.Float, nullable=True)
    sentiment_stdev           = db.Column(db.Float, nullable=True)

    # Bare mentions nothing corroborated. Stored, never scored (spec 4.2).
    low_count                 = db.Column(db.Integer, nullable=False, default=0)

    sources_ok                = db.Column(db.SmallInteger, nullable=False, default=0)
    source_config_version     = db.Column(db.String(16), nullable=False)


class RadarBucketSource(db.Model):
    """(ticker x bucket x source). What makes the source set open.

    Per-source data lived in columns named after specific sources until three
    sources and a UI selector made that untenable: a user-chosen subset has to
    be pooled at query time, and `count_stocktwits` cannot participate in that.

    expected and variance sit here beside mention_z because pooling a subset
    means summing components -- a weighted mean of z-scores is not a z-score
    (spec 6.2). Both are written by Plan 2 and are NULL until then.

    No foreign key to radar_buckets: InnoDB does not support foreign keys on
    partitioned tables and radar_buckets is partitioned monthly. This table is
    partitioned identically and joined on (ticker, bucket_start), which means
    retention and partition maintenance must treat the pair as one unit --
    nothing enforces that for us.
    """
    __tablename__ = 'radar_bucket_sources'
    __table_args__ = (
        db.Index('ix_radar_bucket_sources_start', 'bucket_start', 'source'),
        # How the board's coverage probe reads it: DISTINCT bucket_start by
        # source and status. Covering -- without it MySQL walked every live
        # index entry and heap-read each for status (10.8s at 864k rows).
        db.Index('ix_radar_bucket_sources_coverage',
                 'source', 'status', 'bucket_start'),
        {'mysql_charset': 'utf8mb4'},
    )

    ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'),
                                          primary_key=True)
    bucket_start              = db.Column(MYSQL_DATETIME(fsp=6), primary_key=True)
    # 48, not 24: a Reddit source name carries its subreddit
    # (`reddit:smallstreetbets` is 22 characters and the margin at 24 was two).
    source                    = db.Column(db.String(48), primary_key=True)

    mention_count             = db.Column(db.Integer, nullable=False, default=0)
    high_confidence_count     = db.Column(db.Integer, nullable=False, default=0)
    low_count                 = db.Column(db.Integer, nullable=False, default=0)
    distinct_authors          = db.Column(db.Integer, nullable=False, default=0)
    distinct_text_ratio       = db.Column(db.Float, nullable=False, default=1.0)
    engagement_weighted_count = db.Column(db.Float, nullable=False, default=0.0)
    sentiment_mean            = db.Column(db.Float, nullable=True)
    sentiment_stdev           = db.Column(db.Float, nullable=True)

    status                    = db.Column(
        db.Enum('ok', 'missing', 'truncated', name='radar_source_status'),
        nullable=False, default='missing')

    # Per source, not inherited from the parent bucket: baselines exclude
    # history from before a configuration change (spec 6.6), and that decision
    # is made per (ticker, source).
    #
    # Nullable because rows already written have no value, and back-filling a
    # version they were not collected under would be a lie. baselines.usable
    # treats a mismatch as unusable, so those rows simply age out of the window.
    source_config_version     = db.Column(db.String(16), nullable=True)

    # Written by the scoring pass.
    expected                  = db.Column(db.Float, nullable=True)
    variance                  = db.Column(db.Float, nullable=True)
    mention_z                 = db.Column(db.Float, nullable=True)
    # Float since 2026-08-26. SmallInteger meant span.days, and .days truncated
    # twenty-three hours of history to zero -- which put every row on the board
    # under PROVISIONAL_BASELINE_DAYS permanently.
    baseline_days             = db.Column(db.Float, nullable=True)


class RadarPollState(db.Model):
    """When each symbol was last polled, and when it is next due.

    Per source, because the same symbol has a different message rate on each.
    """
    __tablename__ = 'radar_poll_state'
    __table_args__ = (
        db.Index('ix_radar_poll_state_due', 'source', 'next_due_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    source          = db.Column(db.String(48), primary_key=True)
    # 64, not 12. This holds whatever the source polls by, and that stopped
    # being a ticker when Reddit reused the scheduler with the SUBREDDIT as
    # the unit -- `RobinHoodPennyStocks` is 20 characters, and at 12 the whole
    # insert failed on the daemon's first cycle.
    symbol          = db.Column(db.String(64, collation='utf8mb4_bin'),
                                primary_key=True)
    last_polled_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    next_due_at     = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    observed_rate   = db.Column(db.Float, nullable=True)   # messages per hour


class RadarSourceCursor(db.Model):
    """How far each source has been read.

    Explicit state rather than max(radar_posts.created_utc), because posts that
    mention no ticker are not stored at all. Bluesky's firehose is 144k
    posts/hour and roughly none of them are about stocks -- keeping them would
    be 100 million rows a month of text nothing ever reads.

    Inferring the cursor from stored posts would then rewind it to the last
    post that happened to mention something, and the next cycle would refetch
    everything since. The cursor has to be what we SAW, not what we KEPT.
    """
    __tablename__ = 'radar_source_cursors'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    source     = db.Column(db.String(24), primary_key=True)
    cursor_utc = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarQuote(db.Model):
    """One price snapshot for one ticker.

    Snapshots rather than a single current price, because no-print detection
    compares consecutive polls: a frozen tape is one whose quote_ts has not
    advanced since last time, and that comparison needs last time to still be
    here.

    DECIMAL rather than float throughout (spec 5.5.5). Forward returns compound
    these, and drift in a history log is the one place it cannot be tolerated.

    Volume is nullable and, on the current provider, always null: Finnhub's
    free quote carries no `v` field. No-print detection degrades to comparing
    quote_ts alone, which still catches a frozen tape.
    """
    __tablename__ = 'radar_quotes'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'market', 'mic', 'fetched_at',
                            name='uq_radar_quote_market'),
        db.CheckConstraint("market IS NULL OR market IN ('us', 'de')",
                           name='ck_radar_quotes_market'),
        # massive_grouped is deliberately NOT a quote source: Massive is a
        # daily-close feed and must never masquerade as an intraday print
        # (spec 2026-08-31 §7).
        db.CheckConstraint(
            "source IS NULL OR source IN ('legacy', 'finnhub', 'twelvedata',"
            " 'deutsche_boerse_delayed', 'yahoo_chart')",
            name='ck_radar_quote_source'),
        db.CheckConstraint(
            "price_basis IS NULL OR price_basis IN"
            " ('trade', 'midpoint', 'close')",
            name='ck_radar_quote_price_basis'),
        db.Index('ix_radar_quotes_ticker_market_mic_fetched',
                 'ticker', 'market', 'mic', 'fetched_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    id          = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker      = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    # Expand-stage columns. Nullable until every daemon writer is market-aware;
    # old rows and mixed-version writes mean US during that compatibility
    # window. The contraction migration belongs after the writer rollout.
    market      = db.Column(db.String(2), nullable=True)
    mic         = db.Column(db.String(4), nullable=True)
    currency    = db.Column(db.String(3), nullable=True)
    provider_symbol = db.Column(db.String(32), nullable=True)
    fetched_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)

    # The exchange's timestamp for the print, not ours. A tape that has not
    # moved reuses the same one, which is what makes it detectable.
    quote_ts    = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    price       = db.Column(db.Numeric(18, 6), nullable=False)
    prev_close  = db.Column(db.Numeric(18, 6), nullable=True)
    # The current regular-session close is distinct from the previous close:
    # after-hours movement is measured from this same-day baseline.
    regular_close = db.Column(db.Numeric(18, 6), nullable=True)
    # Provider-declared provenance, distinct from age-derived ``stale``.
    # Nullable for snapshots written before this field was deployed.
    provider_delay = db.Column(db.String(8), nullable=True)
    volume      = db.Column(db.BigInteger, nullable=True)
    # Market-data v2 provenance (expand stage: nullable, legacy writers keep
    # working). ``source`` names the feed, ``price_basis`` separates an
    # executed trade from an indicative midpoint, and the book columns hold
    # the original bid/ask a midpoint was derived from.
    source      = db.Column(db.String(32), nullable=True)
    price_basis = db.Column(db.String(8), nullable=True)
    bid         = db.Column(db.Numeric(18, 6), nullable=True)
    ask         = db.Column(db.Numeric(18, 6), nullable=True)
    # Shadow rows are the measurement lane of the staged rollout: persisted
    # for the activation gates, invisible to every live read.
    is_shadow   = db.Column(db.Boolean, nullable=False, default=False,
                            server_default=sa.false())


class RadarDailyClose(db.Model):
    """One daily close per ticker. What the board's price history draws.

    Separate from RadarQuote, which is an intraday snapshot taken every five
    minutes and pruned at thirty days. This is one row per trading day, kept
    for a year, and it answers a different question: not "did the price move
    while people were talking" but "what state is this stock in".

    Not partitioned, unlike radar_buckets. A year of closes for a few thousand
    tickers is small, and rows are replaced by date rather than accumulated.
    """
    __tablename__ = 'radar_daily_closes'
    __table_args__ = (
        # is_shadow joins the identity so a shadow measurement row and the
        # incumbent live row can coexist for the same date during an
        # activation gate (spec 2026-08-31 §7 [A1]).
        db.UniqueConstraint('ticker', 'market', 'mic', 'close_date',
                            'is_shadow', name='uq_radar_daily_close_market'),
        db.CheckConstraint("market IS NULL OR market IN ('us', 'de')",
                           name='ck_radar_daily_closes_market'),
        db.CheckConstraint(
            "source IS NULL OR source IN ('legacy', 'finnhub', 'twelvedata',"
            " 'deutsche_boerse_delayed', 'yahoo_chart', 'massive_grouped')",
            name='ck_radar_daily_closes_source'),
        db.CheckConstraint(
            "price_basis IS NULL OR price_basis = 'close'",
            name='ck_radar_daily_closes_price_basis'),
        # Every selected v2 history source is split-only; NULL is the
        # migration-era value the contraction later classifies.
        db.CheckConstraint(
            "adjustment_basis IS NULL OR adjustment_basis = 'split'",
            name='ck_radar_daily_closes_adjustment'),
        {'mysql_charset': 'utf8mb4'},
    )

    id         = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    ticker     = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    # Same expand-only overlap as RadarQuote. The legacy primary key remains
    # until the history writer can supply market and MIC on every row.
    market     = db.Column(db.String(2), nullable=True)
    mic        = db.Column(db.String(4), nullable=True)
    currency   = db.Column(db.String(3), nullable=True)
    close_date = db.Column(db.Date, nullable=False)
    close      = db.Column(db.Numeric(18, 4), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    # Market-data v2 provenance (expand stage, nullable for legacy rows).
    source           = db.Column(db.String(32), nullable=True)
    price_basis      = db.Column(db.String(8), nullable=True)
    adjustment_basis = db.Column(db.String(8), nullable=True)
    is_shadow        = db.Column(db.Boolean, nullable=False, default=False,
                                 server_default=sa.false())


class RadarFxRate(db.Model):
    """One published FX reference rate per day, per currency pair.

    Here so a US listing's closes can be drawn on a EUR axis without the
    close store ever holding a derived number. Conversion happens at read
    time against these rows; what is stored is only ever what a venue
    printed and what a central bank published.

    The ECB publishes on TARGET business days, so this table has holes by
    construction. A reader carries the last published rate forward across
    them (features/radar/fx.py) rather than interpolating -- a weekend has
    no rate because no rate was set, not because one was missed.
    """
    __tablename__ = 'radar_fx_rates'
    __table_args__ = (
        db.UniqueConstraint('rate_date', 'base', 'quote',
                            name='uq_radar_fx_rate_day'),
        db.Index('ix_radar_fx_rates_pair_day', 'base', 'quote', 'rate_date'),
        {'mysql_charset': 'utf8mb4'},
    )

    id         = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    rate_date  = db.Column(db.Date, nullable=False)
    base       = db.Column(db.String(3), nullable=False)
    quote      = db.Column(db.String(3), nullable=False)
    # Units of `quote` per one `base`. EUR/USD 1.1615 means one euro buys
    # 1.1615 dollars, which is the direction the ECB publishes in.
    rate       = db.Column(db.Numeric(18, 8), nullable=False)
    source     = db.Column(db.String(16), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarMappingGeneration(db.Model):
    """One complete, hashed German-mapping decision set (spec §5.4).

    Mappings change only by activating a whole generation atomically, so a
    partial refresh can never leave the venue table half-updated. The exact
    canonical payload is retained: rollback is re-applying a prior
    generation, not reconstructing it from memory.
    """
    __tablename__ = 'radar_mapping_generations'
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('shadow', 'active', 'retired', 'failed')",
            name='ck_radar_mapping_generation_status'),
        {'mysql_charset': 'utf8mb4'},
    )

    id             = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    market         = db.Column(db.String(2), nullable=False)
    status         = db.Column(db.String(12), nullable=False)
    source         = db.Column(db.String(32), nullable=False)
    payload_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    payload_json   = db.Column(db.Text().with_variant(MEDIUMTEXT, 'mysql'),
                               nullable=False)
    summary_json   = db.Column(db.Text, nullable=False)
    created_at     = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    activated_at   = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)


class RadarMarketDataCursor(db.Model):
    """Durable per-(source, MIC, channel) file cursor for the German feed.

    The delayed service retains roughly a day of minute files; the cursor is
    what lets a restarted daemon consume the still-retained backlog in order
    instead of re-reading or skipping. Never pruned.
    """
    __tablename__ = 'radar_market_data_cursors'
    __table_args__ = (
        db.CheckConstraint("channel IN ('pretrade', 'posttrade')",
                           name='ck_radar_market_cursor_channel'),
        {'mysql_charset': 'utf8mb4'},
    )

    source     = db.Column(db.String(32), primary_key=True)
    mic        = db.Column(db.String(4), primary_key=True)
    channel    = db.Column(db.String(12), primary_key=True)
    remote_id  = db.Column(db.String(160), nullable=False)
    source_ts  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    checksum   = db.Column(db.String(64), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarMarketDataCycle(db.Model):
    """One scheduled German collection attempt and what became of it.

    The ops summary and the activation gates read these instead of scraping
    logs; transport success is a durable fact, not a grep.
    """
    __tablename__ = 'radar_market_data_cycles'
    __table_args__ = (
        db.UniqueConstraint('source', 'mic', 'channel', 'scheduled_at',
                            name='uq_radar_market_cycle'),
        db.CheckConstraint("mode IN ('shadow', 'active')",
                           name='ck_radar_market_cycle_mode'),
        db.CheckConstraint(
            "status IN ('accepted', 'duplicate', 'no_newer', 'rejected',"
            " 'transport_error')",
            name='ck_radar_market_cycle_status'),
        db.CheckConstraint("channel IN ('pretrade', 'posttrade')",
                           name='ck_radar_market_cycle_channel'),
        {'mysql_charset': 'utf8mb4'},
    )

    id                 = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    source             = db.Column(db.String(32), nullable=False)
    mic                = db.Column(db.String(4), nullable=False)
    channel            = db.Column(db.String(12), nullable=False)
    scheduled_at       = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    completed_at       = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    mode               = db.Column(db.String(8), nullable=False)
    status             = db.Column(db.String(16), nullable=False)
    newest_remote_id   = db.Column(db.String(160), nullable=True)
    newest_source_ts   = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    files_seen         = db.Column(db.Integer, nullable=False, default=0)
    files_accepted     = db.Column(db.Integer, nullable=False, default=0)
    record_count       = db.Column(db.Integer, nullable=False, default=0)
    selected_count     = db.Column(db.Integer, nullable=False, default=0)
    rejected_records   = db.Column(db.Integer, nullable=False, default=0)
    compressed_bytes   = db.Column(db.BigInteger, nullable=False, default=0)
    uncompressed_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    parse_ms           = db.Column(db.Integer, nullable=False, default=0)
    provider_lag_s     = db.Column(db.Integer, nullable=True)
    fetch_lag_s        = db.Column(db.Integer, nullable=True)
    error_code         = db.Column(db.String(48), nullable=True)


class RadarMarketTradeEvent(db.Model):
    """One normalized post-trade event inside the 48-hour journal.

    Kept so the native-close materialization can re-derive the last valid
    trade of a session the next morning. The captured feed showed no
    correction/cancellation semantics (contract ruling R4); ``action``
    therefore stores 'new' today, and the enum keeps the reviewed slots so
    an observed correction one day becomes a schema fact, not a surprise.
    """
    __tablename__ = 'radar_market_trade_events'
    __table_args__ = (
        db.UniqueConstraint('mic', 'event_id',
                            name='uq_radar_market_trade_event'),
        db.CheckConstraint("action IN ('new', 'correct', 'cancel')",
                           name='ck_radar_trade_event_action'),
        db.Index('ix_radar_trade_events_mic_isin_ts',
                 'mic', 'isin', 'event_ts'),
        db.Index('ix_radar_trade_events_received', 'received_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    id                = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    mic               = db.Column(db.String(4), nullable=False)
    isin              = db.Column(db.String(12), nullable=False)
    event_id          = db.Column(db.String(64), nullable=False)
    original_event_id = db.Column(db.String(64), nullable=True)
    action            = db.Column(db.String(8), nullable=False)
    event_ts          = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    price             = db.Column(db.Numeric(18, 6), nullable=True)
    volume            = db.Column(db.BigInteger, nullable=True)
    is_official_close = db.Column(db.Boolean, nullable=False, default=False)
    source_remote_id  = db.Column(db.String(160), nullable=False)
    received_at       = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarGroupedCloseDay(db.Model):
    """Durable state for one Massive grouped trading date and lane.

    THE resumable progress ledger for grouped closes: accepted rows are
    progress, everything else stays retryable. Massive never touches the
    MIC-keyed German cursor (spec §7, Codex correction).
    """
    __tablename__ = 'radar_grouped_close_days'
    __table_args__ = (
        db.UniqueConstraint('source', 'close_date', 'is_shadow',
                            name='uq_radar_grouped_close_day'),
        db.CheckConstraint(
            "status IN ('accepted', 'no_data', 'rejected',"
            " 'transport_error')",
            name='ck_radar_grouped_day_status'),
        {'mysql_charset': 'utf8mb4'},
    )

    id                  = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    source              = db.Column(db.String(32), nullable=False)
    close_date          = db.Column(db.Date, nullable=False)
    is_shadow           = db.Column(db.Boolean, nullable=False, default=False,
                                    server_default=sa.false())
    status              = db.Column(db.String(16), nullable=False)
    payload_sha256      = db.Column(db.String(64), nullable=True)
    fetched_at          = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    completed_at        = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    provider_rows       = db.Column(db.Integer, nullable=False, default=0)
    mapped_rows         = db.Column(db.Integer, nullable=False, default=0)
    written_rows        = db.Column(db.Integer, nullable=False, default=0)
    unmatched_provider  = db.Column(db.Integer, nullable=False, default=0)
    unmatched_universe  = db.Column(db.Integer, nullable=False, default=0)
    active_expected     = db.Column(db.Integer, nullable=False, default=0)
    active_matched      = db.Column(db.Integer, nullable=False, default=0)
    malformed_rows      = db.Column(db.Integer, nullable=False, default=0)
    duplicate_conflicts = db.Column(db.Integer, nullable=False, default=0)
    error_code          = db.Column(db.String(48), nullable=True)
    http_status         = db.Column(db.Integer, nullable=True)
    backoff_until       = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)


class RadarProviderSessionState(db.Model):
    """The durably claimed post-close cycle per provider and market.

    The claim commits under a row lock BEFORE the provider request, so a
    daemon restart cannot repeat the weekend request loop (spec §9.2 [A3]).
    """
    __tablename__ = 'radar_provider_session_states'
    __table_args__ = ({'mysql_charset': 'utf8mb4'},)

    source                       = db.Column(db.String(32), primary_key=True)
    market                       = db.Column(db.String(2), primary_key=True)
    last_post_close_session_date = db.Column(db.Date, nullable=True)
    claimed_at                   = db.Column(MYSQL_DATETIME(fsp=6),
                                             nullable=True)


class RadarLlmSpend(db.Model):
    """What the model sentiment pass cost, per day per model.

    Accumulated from the `usage` every API response already carries. There is
    no balance endpoint to ask instead: Anthropic's Cost API reports spend
    rather than remaining credit, needs a separate Admin API key, and is
    documented as unavailable for individual accounts.

    Money is INTEGER MICROS (1 USD = 1_000_000). A float column accumulates
    rounding on every call and then reports a total nobody can reconcile.

    cost_micros is stored rather than derived, because the rate that applied
    is part of what happened. Recomputing an old day against today's price
    list would silently restate what was actually paid.
    """
    __tablename__ = 'radar_llm_spend'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    day           = db.Column(db.Date, primary_key=True)
    model         = db.Column(db.String(40), primary_key=True)
    calls         = db.Column(db.Integer, nullable=False, default=0)
    input_tokens  = db.Column(db.BigInteger, nullable=False, default=0)
    output_tokens = db.Column(db.BigInteger, nullable=False, default=0)
    cost_micros   = db.Column(db.BigInteger, nullable=False, default=0)


class RadarWatch(db.Model):
    """A ticker one account is watching.

    The first per-account fact in radar. Every other radar row is shared --
    mention data is not personal -- but a mark is the reader's own, and the
    gym feature already scopes by `app_user.id` the same way. One row per
    (account, ticker); the surface orders by `created_at`, the order the
    reader made the marks in.
    """
    __tablename__ = 'radar_watch'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'ticker', name='uq_radar_watch_user_ticker'),
        {'mysql_charset': 'utf8mb4'},
    )

    id         = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer,
                           db.ForeignKey('app_user.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    # The radar ticker identity, market-independent. Same collation as
    # radar_ticker_universe.symbol so a join or comparison between the two
    # never mixes collations; watch.normalise() uppercases before every
    # write, which is what keeps 'IT' and 'it' from both existing.
    ticker     = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)


class RadarRedditCursor(db.Model):
    """Where the Arctic Shift reader is, per subreddit and kind.

    Not radar_source_cursors: that table holds ONE cursor per root source
    and ingest advances it every cycle; a per-sub watermark is a different
    fact (reddit.py explains why one shared watermark starves the quiet
    subs). Advanced only when a sub's read succeeded, and staged in the
    cycle's session so it commits with the posts it covers.
    """
    __tablename__ = 'radar_reddit_cursors'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    sub        = db.Column(db.String(64, collation='utf8mb4_bin'), primary_key=True)
    kind       = db.Column(db.String(12), primary_key=True)      # 'comments' | 'posts'
    cursor_utc = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    updated_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarSentimentJudgment(db.Model):
    """Append-only record of every successful primary or review answer.

    Never overwritten: the mention's materialized fields are the FINAL
    result, this table is the evidence -- Haiku-vs-Sonnet comparisons,
    prompt regressions, routing rates, and exact cost attribution all
    read from here. Follows mention retention via ON DELETE CASCADE.
    """
    __tablename__ = 'radar_sentiment_judgments'
    __table_args__ = (
        db.Index('ix_radar_sentiment_judgments_mention', 'mention_id'),
        db.Index('ix_radar_sentiment_judgments_created', 'created_utc'),
        db.CheckConstraint("stage IN ('primary','review')",
                           name='ck_radar_judgment_stage'),
        db.CheckConstraint(
            "relevance IN ('relevant','irrelevant','uncertain')",
            name='ck_radar_judgment_relevance'),
        db.CheckConstraint(
            "content_origin IN ('human_chatter','broadcast_or_automated',"
            "'uncertain')",
            name='ck_radar_judgment_origin'),
        db.CheckConstraint(
            "attitude IN ('positive','negative','mixed','none')",
            name='ck_radar_judgment_attitude'),
        db.CheckConstraint(
            "expected_move IN ('up','down','flat','unknown')",
            name='ck_radar_judgment_move'),
        db.CheckConstraint("confidence IN ('high','medium','low')",
                           name='ck_radar_judgment_conf'),
        {'mysql_charset': 'utf8mb4'},
    )

    id             = db.Column(db.BigInteger, primary_key=True,
                               autoincrement=True)
    mention_id     = db.Column(db.BigInteger,
                               db.ForeignKey('radar_mentions.id',
                                             ondelete='CASCADE'),
                               nullable=False)
    stage          = db.Column(db.String(8), nullable=False)
    model          = db.Column(db.String(40), nullable=False)
    prompt_version = db.Column(db.String(64), nullable=False)
    relevance      = db.Column(db.String(12), nullable=False)
    content_origin = db.Column(db.String(24), nullable=False)
    attitude       = db.Column(db.String(8), nullable=False)
    expected_move  = db.Column(db.String(8), nullable=False)
    confidence     = db.Column(db.String(8), nullable=False)
    input_tokens   = db.Column(db.Integer, nullable=False, default=0)
    output_tokens  = db.Column(db.Integer, nullable=False, default=0)
    created_utc    = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


class RadarReviewMeter(db.Model):
    """Review-tier demand accounting, one row per UTC day.

    All four counters are UNIQUE-mention counts anchored on
    RadarMention.review_requested_at: `demanded` and `capped` increment
    only when that stamp is first written, `attempted` when a mention is
    actually sent to the review model (a failed call still consumed
    ceiling), `served` when a valid answer was written. Hitting the
    ceiling must be visible, not silent (spec §5.3).
    """
    __tablename__ = 'radar_review_meter'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    day       = db.Column(db.Date, primary_key=True)
    demanded  = db.Column(db.Integer, nullable=False, default=0)
    attempted = db.Column(db.Integer, nullable=False, default=0)
    served    = db.Column(db.Integer, nullable=False, default=0)
    capped    = db.Column(db.Integer, nullable=False, default=0)


class RadarMentionEvent(db.Model):
    """Every extracted mention, kept just long enough to rebuild its bucket.

    roll_up recomputes a bucket from scratch on every pass. That is right --
    cycles overlap and additive rollup would double-count the boundary -- but
    it can only be right if the recompute sees the WHOLE quarter-hour. Cycles
    advance a cursor, so what one cycle holds in memory is a slice, and
    rebuilding from that slice erased the earlier ones. Measured in production
    2026-08-26: 4.4% lost on singleton buckets, 42.9% on the 10+ buckets the
    board exists to rank.

    radar_posts cannot serve as this record. A post whose tickers were all
    `low` is never stored -- Bluesky alone would be 100 million rows a month --
    so the promotion inputs are simply absent from it.

    NOT partitioned, unlike radar_buckets: retention here is 48 hours with
    chunked deletes, so there is no month-sized range to drop.
    """
    __tablename__ = 'radar_mention_events'
    __table_args__ = (
        # The identity of a mention. A post returned by two overlapping cycles
        # is one mention, and this is what makes the rebuild idempotent.
        db.UniqueConstraint('source', 'external_id', 'ticker',
                            name='uq_radar_mention_event'),
        # How roll_up reads it back: every event in one ticker's quarter-hour.
        db.Index('ix_radar_mention_events_bucket', 'ticker', 'bucket_start'),
        # How retention finds what to drop.
        db.Index('ix_radar_mention_events_created', 'created_utc'),
        # How the board counts distinct voices: one ticker's events inside a
        # created_utc window. The bucket index above cannot serve it, and
        # without this every candidate's whole history was read (6.7s).
        db.Index('ix_radar_mention_events_ticker_time',
                 'ticker', 'created_utc'),
        {'mysql_charset': 'utf8mb4'},
    )

    id           = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    # 48, not 24: a Reddit source name carries its subreddit
    # (`reddit:smallstreetbets`), and the width is not worth defending.
    source       = db.Column(db.String(48), nullable=False)
    external_id  = db.Column(db.String(128), nullable=False)
    ticker       = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    # The venue inside the source -- a subreddit, a board, a channel. Carried
    # because a broadcast network's independent unit is the CHANNEL and not the
    # author: one admin posts and thousands read, so every bucket has exactly
    # one author and an author gate can never be cleared however loud a symbol
    # is. No live source is broadcast today; Telegram is why the column exists.
    channel      = db.Column(db.String(64), nullable=False, default='')
    created_utc  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    # Denormalised so the rebuild is one indexed read rather than a scan with
    # date arithmetic in the predicate.
    bucket_start = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    author       = db.Column(db.String(64), nullable=True)
    simhash      = db.Column(MYSQL_BIGINT(unsigned=True), nullable=False, default=0)
    # PRE-promotion. `medium` is awarded at rollup from the complete bucket and
    # is never stored here, because storing it would freeze a decision that the
    # next cycle's arrivals can legitimately change.
    confidence   = db.Column(
        db.Enum('high', 'low', name='radar_event_confidence'), nullable=False)
    sentiment    = db.Column(db.Float, nullable=True)
    engagement   = db.Column(db.Float, nullable=False, default=0.0)
    # What _promote decided, written back after the rollup ran over the whole
    # bucket. `confidence` above is what the EXTRACTOR said, and stays that
    # way -- promotion is a property of the quarter-hour and legitimately
    # changes as more of it arrives, so the two facts are stored apart.
    promoted     = db.Column(db.Boolean, nullable=False, default=False)
    # Chatter eligibility (spec 2026-08-31 §7.2). NULL = not yet decided
    # (provisional: counts as before); False = a FINAL irrelevant or
    # broadcast_or_automated judgment excluded it from scored bucket
    # summaries and distinct-voice reads; True = explicitly judged
    # eligible (a review reversal restores counting through here). Only
    # an explicit final verdict moves it off NULL.
    counts_as_human_chatter = db.Column(db.Boolean, nullable=True)
    # WHEN the flag above was last decided. The rebuild retry net keys on
    # this, never on created_utc: a backfill decides OLD events, and a
    # crash between the flag commit and the rebuild must be rediscovered
    # by the next pass regardless of the post's age.
    chatter_decided_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
