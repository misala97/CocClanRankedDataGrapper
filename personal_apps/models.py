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
