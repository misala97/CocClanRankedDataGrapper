from datetime import datetime, timezone
from extensions import db


class Player(db.Model):
    __tablename__ = 'player'

    tag                    = db.Column(db.String(50), primary_key=True)
    name                   = db.Column(db.String(100))
    current_th             = db.Column(db.Integer)
    in_clan                = db.Column(db.Boolean)
    league_tier            = db.Column(db.String(50))
    last_updated           = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    admin_comment          = db.Column(db.Text, nullable=True)
    in_group_chat          = db.Column(db.Boolean, default=False, nullable=False)   # fix #8: was nullable=True
    war_preference_in_game = db.Column(db.String(20), nullable=True)
    war_preference_custom  = db.Column(db.String(20), nullable=True)
    join_date              = db.Column(db.Date, nullable=True, default=lambda: datetime.now(timezone.utc).date())

    ranked_weeks = db.relationship('RankedWeek', back_populates='player', lazy=True, cascade="all, delete-orphan")
    battle_logs  = db.relationship('BattleLog',  back_populates='player', lazy=True, cascade="all, delete-orphan")

    @property
    def league_icon(self) -> str:
        from services.helpers import league_icon_url
        return league_icon_url(self.league_tier)


class RankedWeek(db.Model):
    __tablename__ = 'ranked_week'

    league_group_tag = db.Column(db.String(50), primary_key=True)
    league_season_id = db.Column(db.String(50), primary_key=True)
    player_tag       = db.Column(db.String(50), db.ForeignKey('player.tag'), primary_key=True)

    trophies       = db.Column(db.Integer)
    rank           = db.Column(db.Integer)
    start_day      = db.Column(db.Date)
    end_day        = db.Column(db.Date)
    max_attacks    = db.Column(db.Integer)
    townhall       = db.Column(db.Integer)
    attack_wins    = db.Column(db.Integer)
    attack_losses  = db.Column(db.Integer)
    defense_wins   = db.Column(db.Integer)
    defense_losses = db.Column(db.Integer)
    league_tier    = db.Column(db.String(50))
    is_done        = db.Column(db.Boolean, default=False)
    last_updated   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    player      = db.relationship('Player', back_populates='ranked_weeks')
    battle_logs = db.relationship('RankedBattleLog', back_populates='ranked_week', lazy=True, cascade="all, delete-orphan")

    @property
    def league_icon(self) -> str:
        from services.helpers import league_icon_url
        return league_icon_url(self.league_tier)


class RankedBattleLog(db.Model):
    __tablename__ = 'ranked_battle_log'

    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    opponent_tag     = db.Column(db.String(50), nullable=False)
    league_group_tag = db.Column(db.String(50))
    league_season_id = db.Column(db.String(50))
    player_tag       = db.Column(db.String(50))
    attack           = db.Column(db.Boolean)
    stars            = db.Column(db.Integer)
    percentage       = db.Column(db.Integer)
    trophies         = db.Column(db.Integer)
    opponent_name    = db.Column(db.String(100))
    opponent_th      = db.Column(db.Integer)    # fix #1: was String(100)
    time             = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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

    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)   # fix #3: surrogate PK
    player_tag       = db.Column(db.String(50), db.ForeignKey('player.tag'))
    opponent_tag     = db.Column(db.String(50))
    loot_gold        = db.Column(db.Integer)
    loot_elixir      = db.Column(db.Integer)
    loot_dark_elixir = db.Column(db.Integer)
    attack           = db.Column(db.Boolean)
    stars            = db.Column(db.Integer)
    percentage       = db.Column(db.Integer)
    type             = db.Column(db.String(50))
    time             = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', back_populates='battle_logs')

    __table_args__ = (
        db.UniqueConstraint('player_tag', 'opponent_tag', 'loot_gold', 'loot_elixir', 'loot_dark_elixir',
                            name='uq_battle_log'),
    )


class RaidWeekend(db.Model):
    __tablename__ = 'raid_weekend'

    id                        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    start_time                = db.Column(db.DateTime)   # fix #5: was startTime
    end_time                  = db.Column(db.DateTime)   # fix #5: was endTime
    state                     = db.Column(db.String(20))
    capital_total_loot        = db.Column(db.Integer)    # fix #5: was capitalTotalLoot
    raids_completed           = db.Column(db.Integer)    # fix #5: was raidsCompleted
    total_attacks             = db.Column(db.Integer)    # fix #5: was totalAttacks
    enemy_districts_destroyed = db.Column(db.Integer)   # fix #5: was enemyDistrictsDestroyed
    offensive_reward          = db.Column(db.Integer)   # fix #5: was offensiveReward
    defensive_reward          = db.Column(db.Integer)   # fix #5: was defensiveReward

    logs = db.relationship('RaidWeekendLog', back_populates='raid_weekend', lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('start_time', 'end_time', name='uq_raid_weekend'),  # fix #4
    )


class RaidWeekendLog(db.Model):
    __tablename__ = 'raid_weekend_log'

    id                    = db.Column(db.Integer, primary_key=True, autoincrement=True)
    raid_weekend_id       = db.Column(db.Integer, db.ForeignKey('raid_weekend.id'))
    defender_name         = db.Column(db.String(30))    # fix #5: was defenderName
    defender_tag          = db.Column(db.String(30))    # fix #5: was defenderTag
    district_name         = db.Column(db.String(30))    # fix #5: was districtName
    district_level        = db.Column(db.Integer)       # fix #2+#5: was districLevel (typo)
    total_loot_all_attacks = db.Column(db.Integer)      # fix #5: was totalLootAllAttacks
    percentage            = db.Column(db.Integer)
    percentage_total      = db.Column(db.Integer)       # fix #5: was percentageTotal
    stars                 = db.Column(db.Integer)
    player_tag            = db.Column(db.String(50), db.ForeignKey('player.tag'))  # fix #5: was playerTag

    raid_weekend = db.relationship('RaidWeekend', back_populates='logs')
    player       = db.relationship('Player', foreign_keys=[player_tag])


class UptimeTracker(db.Model):
    __tablename__ = 'uptime_tracker'

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    function      = db.Column(db.String(50))
    time          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    duration      = db.Column(db.Float)     # fix #6: was String(50)
    status        = db.Column(db.String(20), default='success')
    error_message = db.Column(db.Text, nullable=True)
    summary       = db.Column(db.String(200), nullable=True)


class PubQuizRounds(db.Model):
    __tablename__ = 'pubquiz_rounds'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    datum      = db.Column(db.DateTime)
    bilderrunde = db.Column(db.String(100))
    quizmaster = db.Column(db.String(100))

    teams = db.relationship('PubQuizTeams', back_populates='round', lazy=True, cascade="all, delete-orphan")


class PubQuizTeams(db.Model):
    __tablename__ = 'pubquiz_teams'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name          = db.Column(db.String(100))
    round_id      = db.Column(db.Integer, db.ForeignKey('pubquiz_rounds.id'))
    round1_points = db.Column(db.Float)
    round2_points = db.Column(db.Float)
    round3_points = db.Column(db.Float)
    round4_points = db.Column(db.Float)
    round1_size   = db.Column(db.Integer)
    round2_size   = db.Column(db.Integer)
    round3_size   = db.Column(db.Integer)
    round4_size   = db.Column(db.Integer)

    round = db.relationship('PubQuizRounds', back_populates='teams')


class AppUser(db.Model):
    __tablename__ = 'app_user'

    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username       = db.Column(db.String(80), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_approved    = db.Column(db.Boolean, default=False, nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    perm_create_reminder_ranked = db.Column(db.Boolean, default=False, nullable=False)
    perm_clan_war_edits         = db.Column(db.Boolean, default=False, nullable=False)


class ClanWar(db.Model):
    __tablename__ = 'clan_war'

    id                       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    state                    = db.Column(db.String(20))
    team_size                = db.Column(db.Integer)
    preparation_start_time   = db.Column(db.DateTime)
    start_time               = db.Column(db.DateTime, unique=True)
    end_time                 = db.Column(db.DateTime)
    clan_tag                 = db.Column(db.String(30), nullable=True)   # fix #9
    clan_name                = db.Column(db.String(100), nullable=True)
    clan_badge               = db.Column(db.String(200), nullable=True)
    cwl_league               = db.Column(db.String(50),  nullable=True)
    clan_location            = db.Column(db.String(100), nullable=True)
    clan_wars_won            = db.Column(db.Integer,     nullable=True)
    clan_war_frequency       = db.Column(db.String(50),  nullable=True)
    clan_win_streak          = db.Column(db.Integer,     nullable=True)
    opponent_tag             = db.Column(db.String(30))
    opponent_name            = db.Column(db.String(100))
    opponent_clan_level      = db.Column(db.Integer)
    opponent_clan_badge      = db.Column(db.String(200), nullable=True)
    opponent_clan_location   = db.Column(db.String(100), nullable=True)
    opponent_cwl_league      = db.Column(db.String(50),  nullable=True)
    opponent_wars_won        = db.Column(db.Integer,     nullable=True)
    opponent_war_frequency   = db.Column(db.String(50),  nullable=True)
    opponent_win_streak      = db.Column(db.Integer,     nullable=True)
    clan_stars               = db.Column(db.Integer, default=0)
    clan_attacks             = db.Column(db.Integer, default=0)
    clan_destruction_pct     = db.Column(db.Float, default=0.0)
    opponent_stars           = db.Column(db.Integer, default=0)
    opponent_attacks         = db.Column(db.Integer, default=0)
    opponent_destruction_pct = db.Column(db.Float, default=0.0)
    castle_empty             = db.Column(db.Boolean, default=False, nullable=False)

    members = db.relationship('ClanWarMember', back_populates='clan_war', lazy=True, cascade='all, delete-orphan')
    attacks = db.relationship('ClanWarAttack',  back_populates='clan_war', lazy=True, cascade='all, delete-orphan')


class ClanWarMember(db.Model):
    __tablename__ = 'clan_war_member'

    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    clan_war_id      = db.Column(db.Integer, db.ForeignKey('clan_war.id'))
    is_opponent      = db.Column(db.Boolean, default=False, nullable=False)
    player_tag       = db.Column(db.String(30))
    player_name      = db.Column(db.String(100))
    town_hall_level  = db.Column(db.Integer)
    map_position     = db.Column(db.Integer)
    opponent_attacks = db.Column(db.Integer, default=0)
    ranked_league    = db.Column(db.String(50), nullable=True)
    is_rushed        = db.Column(db.Boolean, default=False, nullable=False)
    is_troll         = db.Column(db.Boolean, default=False, nullable=False)

    clan_war = db.relationship('ClanWar', back_populates='members')


class ClanWarAttack(db.Model):
    __tablename__ = 'clan_war_attack'

    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    clan_war_id     = db.Column(db.Integer, db.ForeignKey('clan_war.id'))
    attacker_tag    = db.Column(db.String(30))
    defender_tag    = db.Column(db.String(30))
    stars           = db.Column(db.Integer)
    destruction_pct = db.Column(db.Float)
    attack_order    = db.Column(db.Integer)
    duration        = db.Column(db.Integer)

    clan_war = db.relationship('ClanWar', back_populates='attacks')


# ── Clan War League ───────────────────────────────────────────────────────────

class CWLSeason(db.Model):
    __tablename__ = 'cwl_season'

    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    season       = db.Column(db.String(10), unique=True, nullable=False)
    state        = db.Column(db.String(20))
    league_name  = db.Column(db.String(50), nullable=True)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    clans = db.relationship('CWLClan', back_populates='season', lazy=True, cascade='all, delete-orphan')
    wars  = db.relationship('CWLWar',  back_populates='season', lazy=True, cascade='all, delete-orphan')


class CWLClan(db.Model):
    __tablename__ = 'cwl_clan'

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    season_id  = db.Column(db.Integer, db.ForeignKey('cwl_season.id'), nullable=False)
    tag        = db.Column(db.String(30), nullable=False)
    name       = db.Column(db.String(100))
    badge_url  = db.Column(db.String(200), nullable=True)

    season  = db.relationship('CWLSeason', back_populates='clans')
    members = db.relationship('CWLClanMember', back_populates='clan', lazy=True, cascade='all, delete-orphan')


class CWLWar(db.Model):
    __tablename__ = 'cwl_war'

    id                    = db.Column(db.Integer, primary_key=True, autoincrement=True)
    season_id             = db.Column(db.Integer, db.ForeignKey('cwl_season.id'), nullable=False)
    round_number          = db.Column(db.Integer, nullable=False)
    war_tag               = db.Column(db.String(50), nullable=False)
    state                 = db.Column(db.String(20))
    start_time            = db.Column(db.DateTime)
    end_time              = db.Column(db.DateTime)
    team_size             = db.Column(db.Integer)
    clan_tag              = db.Column(db.String(30))
    clan_name             = db.Column(db.String(100))
    clan_badge            = db.Column(db.String(200), nullable=True)
    clan_level            = db.Column(db.Integer,     nullable=True)
    clan_cwl_league       = db.Column(db.String(50),  nullable=True)
    clan_location         = db.Column(db.String(100), nullable=True)
    clan_wars_won         = db.Column(db.Integer,     nullable=True)
    clan_war_frequency    = db.Column(db.String(50),  nullable=True)
    clan_win_streak       = db.Column(db.Integer,     nullable=True)
    clan_stars            = db.Column(db.Integer, default=0)
    clan_attacks          = db.Column(db.Integer, default=0)
    clan_destruction_pct  = db.Column(db.Float, default=0.0)
    opp_tag               = db.Column(db.String(30))
    opp_name              = db.Column(db.String(100))
    opp_badge             = db.Column(db.String(200), nullable=True)
    opp_level             = db.Column(db.Integer,     nullable=True)
    opp_cwl_league        = db.Column(db.String(50),  nullable=True)
    opp_location          = db.Column(db.String(100), nullable=True)
    opp_wars_won          = db.Column(db.Integer,     nullable=True)
    opp_war_frequency     = db.Column(db.String(50),  nullable=True)
    opp_win_streak        = db.Column(db.Integer,     nullable=True)
    opp_stars             = db.Column(db.Integer, default=0)
    opp_attacks           = db.Column(db.Integer, default=0)
    opp_destruction_pct   = db.Column(db.Float, default=0.0)

    season  = db.relationship('CWLSeason', back_populates='wars')
    members = db.relationship('CWLMember', back_populates='war', lazy=True, cascade='all, delete-orphan')
    attacks = db.relationship('CWLAttack', back_populates='war', lazy=True, cascade='all, delete-orphan')


class CWLClanMember(db.Model):
    """Day-1 roster snapshot for every member of every CWL clan."""
    __tablename__ = 'cwl_clan_member'

    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    clan_id         = db.Column(db.Integer, db.ForeignKey('cwl_clan.id'), nullable=False)
    player_tag      = db.Column(db.String(30))
    player_name     = db.Column(db.String(100))
    town_hall_level = db.Column(db.Integer)
    ranked_league   = db.Column(db.String(50), nullable=True)
    is_rushed       = db.Column(db.Boolean, default=False, nullable=False)
    is_troll        = db.Column(db.Boolean, default=False, nullable=False)

    clan = db.relationship('CWLClan', back_populates='members')


class CWLMember(db.Model):
    __tablename__ = 'cwl_member'

    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    war_id           = db.Column(db.Integer, db.ForeignKey('cwl_war.id'), nullable=False)
    clan_tag         = db.Column(db.String(30))
    player_tag       = db.Column(db.String(30))
    player_name      = db.Column(db.String(100))
    town_hall_level  = db.Column(db.Integer)
    map_position     = db.Column(db.Integer)
    is_opponent      = db.Column(db.Boolean, default=False)
    ranked_league    = db.Column(db.String(50), nullable=True)
    opponent_attacks = db.Column(db.Integer, default=0)
    is_rushed        = db.Column(db.Boolean, default=False, nullable=False)
    is_troll         = db.Column(db.Boolean, default=False, nullable=False)

    war = db.relationship('CWLWar', back_populates='members')


class CWLAttack(db.Model):
    __tablename__ = 'cwl_attack'

    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    war_id          = db.Column(db.Integer, db.ForeignKey('cwl_war.id'), nullable=False)
    attacker_tag    = db.Column(db.String(30))
    defender_tag    = db.Column(db.String(30))
    stars           = db.Column(db.Integer)
    destruction_pct = db.Column(db.Float)
    attack_order    = db.Column(db.Integer)
    duration        = db.Column(db.Integer)

    war = db.relationship('CWLWar', back_populates='attacks')
