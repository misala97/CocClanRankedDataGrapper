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
    bike_size    = db.Column(db.String(10))   # 'small' | 'big'
    weather      = db.Column(db.String(20))   # 'clear' | 'rain' | 'heavy_rain' | 'snow' | 'thunderstorm' | 'hail'
    notes        = db.Column(db.Text, nullable=True)
