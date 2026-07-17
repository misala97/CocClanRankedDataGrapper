import datetime as dt

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


class Exercise(db.Model):
    __tablename__ = 'gym_exercises'
    id                   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name                 = db.Column(db.String(150), nullable=False, unique=True)
    previous_name        = db.Column(db.String(150), nullable=True)  # set to the prior name on rename, so anything still referencing the old name (e.g. historical data, or a rename made by mistake) can still resolve to this exercise instead of creating a duplicate
    muscle_group         = db.Column(db.String(100), nullable=True)
    default_rest_seconds = db.Column(db.Integer, nullable=True)
    is_unilateral        = db.Column(db.Boolean, nullable=False, default=False)  # logged weight/reps are per side (e.g. one-arm curls); volume must be doubled

    session_exercises  = db.relationship('SessionExercise', back_populates='exercise', lazy=True)
    template_exercises = db.relationship('TemplateExercise', back_populates='exercise', lazy=True)


class WorkoutTemplate(db.Model):
    __tablename__ = 'gym_workout_templates'
    id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)

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
    template_id  = db.Column(db.Integer, db.ForeignKey('gym_workout_templates.id'), nullable=True)
    started_at   = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    finished_at  = db.Column(db.DateTime, nullable=True)
    rest_ends_at = db.Column(db.DateTime, nullable=True)  # display-only target for the in-page countdown
    resting_set_id = db.Column(db.Integer, db.ForeignKey('gym_session_sets.id'), nullable=True)  # which set's completion started the current rest timer, for the per-set progress bar

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
    skipped      = db.Column(db.Boolean, nullable=False, default=False)  # True when this exercise is intentionally not being done this session; the row (and any already-completed sets) is kept as-is so a later "save/update as template" still includes it

    session  = db.relationship('WorkoutSession', back_populates='exercises')
    exercise = db.relationship('Exercise', back_populates='session_exercises')
    # self-referential: `replaces` points at the original exercise this substitutes for;
    # `replaced_by` (backref) points the other way, so the original can tell it's been superseded
    replaces = db.relationship('SessionExercise', remote_side=[id], backref=db.backref('replaced_by', uselist=False))
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

    session_exercise = db.relationship('SessionExercise', back_populates='sets')


class PushSubscription(db.Model):
    __tablename__ = 'gym_push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    endpoint   = db.Column(db.String(500), nullable=False, unique=True)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key   = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)


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
