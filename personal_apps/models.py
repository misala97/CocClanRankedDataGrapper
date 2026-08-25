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
    source       = db.Column(db.String(16), nullable=False)
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

    post = db.relationship('RadarPost', back_populates='mentions')


class RadarBucket(db.Model):
    """(ticker x 15 minutes). Retained forever; this is what scoring reads.

    Status is per source, not per bucket. With one column and two sources,
    StockTwits dropping while Reddit keeps working forces a choice between
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
        {'mysql_charset': 'utf8mb4'},
    )

    ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'),
                                          primary_key=True)
    bucket_start              = db.Column(MYSQL_DATETIME(fsp=6), primary_key=True)
    source                    = db.Column(db.String(24), primary_key=True)

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
    baseline_days             = db.Column(db.SmallInteger, nullable=True)


class RadarPollState(db.Model):
    """When each symbol was last polled, and when it is next due.

    Per source, because the same symbol has a different message rate on each.
    """
    __tablename__ = 'radar_poll_state'
    __table_args__ = (
        db.Index('ix_radar_poll_state_due', 'source', 'next_due_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    source          = db.Column(db.String(24), primary_key=True)
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
        db.UniqueConstraint('ticker', 'fetched_at', name='uq_radar_quote'),
        db.Index('ix_radar_quotes_ticker_fetched', 'ticker', 'fetched_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    id          = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker      = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    fetched_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)

    # The exchange's timestamp for the print, not ours. A tape that has not
    # moved reuses the same one, which is what makes it detectable.
    quote_ts    = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    price       = db.Column(db.Numeric(18, 6), nullable=False)
    prev_close  = db.Column(db.Numeric(18, 6), nullable=True)
    volume      = db.Column(db.BigInteger, nullable=True)


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
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    ticker     = db.Column(db.String(12, collation='utf8mb4_bin'),
                           primary_key=True)
    close_date = db.Column(db.Date, primary_key=True)
    close      = db.Column(db.Numeric(18, 4), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)


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
