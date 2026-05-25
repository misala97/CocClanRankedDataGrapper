from datetime import datetime, timezone
from extensions import db


# Tabellen
class Player(db.Model):
    __tablename__ = 'player'
    
    # Player Tags in CoC sind meist unter 15 Zeichen, 50 ist ein sicherer Puffer
    tag = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100))
    current_th = db.Column(db.Integer)
    in_clan = db.Column(db.Boolean)
    
    # z.B. "Legend", "Titan", etc.
    league_tier = db.Column(db.String(50))
    league_icon = db.Column(db.String(150)) 
    
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Beziehungen zu anderen Tabellen
    ranked_weeks = db.relationship('RankedWeek', back_populates='player', lazy=True, cascade="all, delete-orphan")
    battle_logs = db.relationship('BattleLog', back_populates='player', lazy=True, cascade="all, delete-orphan")


class RankedWeek(db.Model):
    __tablename__ = 'ranked_week'
    
    league_group_tag = db.Column(db.String(50), primary_key=True)
    league_season_id = db.Column(db.String(50), primary_key=True)
    player_tag = db.Column(db.String(50), db.ForeignKey('player.tag'), primary_key=True)
    
    trophies = db.Column(db.Integer)
    rank = db.Column(db.Integer)
    start_day = db.Column(db.Date)
    end_day = db.Column(db.Date)
    max_attacks = db.Column(db.Integer)
    townhall = db.Column(db.Integer)
    attack_wins = db.Column(db.Integer)
    attack_losses = db.Column(db.Integer)
    defense_wins = db.Column(db.Integer)
    defense_losses = db.Column(db.Integer)
    league_tier = db.Column(db.String(50))
    league_icon = db.Column(db.String(150)) 
    
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Beziehung zu den Ranked Logs
    player = db.relationship('Player', back_populates='ranked_weeks')
    battle_logs = db.relationship('RankedBattleLog', back_populates='ranked_week', lazy=True, cascade="all, delete-orphan")

class RankedBattleLog(db.Model):
    __tablename__ = 'ranked_battle_log'
    
    # MySQL braucht ein festes Limit. 255 reicht für generierte IDs.
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    opponent_tag = db.Column(db.String(50), nullable=False)
    
    
    # Composite foreign key to RankedWeek
    league_group_tag = db.Column(db.String(50))
    league_season_id = db.Column(db.String(50))
    player_tag = db.Column(db.String(50))
    
    attack = db.Column(db.Boolean)
    stars = db.Column(db.Integer)
    percentage = db.Column(db.Integer)
    trophies = db.Column(db.Integer)
    
    
    opponent_name = db.Column(db.String(100))
    opponent_th = db.Column(db.String(100))
    
    time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    ranked_week = db.relationship('RankedWeek', back_populates='battle_logs')
    
    player = db.relationship(
        'Player',
        primaryjoin='foreign(RankedBattleLog.player_tag) == Player.tag',
        viewonly=True,
        uselist=False
    )
    
    __table_args__ = (
        db.ForeignKeyConstraint(
            ['league_group_tag', 'league_season_id', 'player_tag'],
            ['ranked_week.league_group_tag', 'ranked_week.league_season_id', 'ranked_week.player_tag']
        ),
    )


class BattleLog(db.Model):
    __tablename__ = 'battle_log'
    
    player_tag = db.Column(db.String(50), db.ForeignKey('player.tag'), primary_key=True,)
    opponent_tag = db.Column(db.String(50), primary_key=True,)
    loot_gold = db.Column(db.Integer, primary_key=True)
    loot_elixir = db.Column(db.Integer, primary_key=True)
    loot_dark_elixir = db.Column(db.Integer, primary_key=True)
    
    attack = db.Column(db.Boolean)
    stars = db.Column(db.Integer)
    percentage = db.Column(db.Integer) 

    # Type ist z.B. "ranked" oder "homeVillage"
    type = db.Column(db.String(50)) 
    
    time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    player = db.relationship('Player', back_populates='battle_logs')


class UptimeTracker(db.Model):
    __tablename__ = 'uptime_tracker'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    function = db.Column(db.String(50))
    time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    duration = db.Column(db.String(50))