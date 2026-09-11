"""Parity, adversarially: the stored board is the board the direct path builds.

The shared path's whole claim is that a viewer handed a stored blob was handed
exactly what the synchronous path would have built for them. The PERF2 spike
checked that on a fixture with no tones and no row the limit could cut -- two
of the things most likely to make two builds of "the same" board come out
different. This file checks it where it can fail:

* sixty tickers against a limit of fifty, so every sort decides which ten are
  cut, and has to decide it BEFORE the limit on both paths;
* real tones of every kind -- judged, legacy, word-list, null, none at all and
  judged out of the denominator -- so `lean` has ties and Nones;
* quotes that move for forty tickers and not for twenty, on two markets, with
  US fallbacks, a German listing that is mapped but silent, a stale German tape
  and a frozen US one, so `move` and `divergence` have values, ties and Nones;
* a pre-split root `reddit` bucket under the old source stamp, which a score
  must not see and a count must;
* selections spelled differently that are one question, and selections that
  look alike and are not.

Both sides are built at one instant from the same rows. The direct side is
`build_payload_direct`. The shared side goes the whole way a production board
goes: admitted, claimed, rebuilt from the CLAIM's key_json -- never from the
caller's Query, because canonicalising the key is exactly the step whose
harmlessness is being proved -- published, and read back through
`read_payload`. Every process-level memo a build reads through is emptied
before each side, so neither is quietly handed the other's work.

A difference here is a finding, not flake: both sides are handed the same
instant and nothing either reads from the wall clock reaches the payload, and
the fixture's default ranking is a total order -- which the first test
asserts, because every tie in every other sort falls back to it.
"""
import dataclasses
import datetime as dt
import decimal
import hashlib
import json
import secrets
import zlib

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import (board as board_mod, board_keys, board_namespace,
                            board_producer, board_shared, board_store,
                            coverage, leaderboard, watch)
from features.radar.config import (DEFAULT_SEGMENT, REDDIT_SUBS,
                                   source_config_version)
from features.radar.routes import api
from models import (AppUser, RadarBucketSource, RadarDailyClose,
                    RadarInstrument, RadarMention, RadarPost, RadarQuote,
                    RadarWatch, TickerUniverse)

DISPOSABLE = 'personal_apps_radar_perf3'

# A Tuesday in January, where the test database holds no radar data at all.
# Coverage is decided across EVERY ticker by design, so a clock overlapping
# real rows would let them decide which of this file's hours count as
# measured. At 15:00 UTC both sessions are regular, so an unqualified request
# opens on Germany (routes.api.default_market).
NOW = dt.datetime(2026, 1, 20, 15, 0)
# The omitted-market clocks: the US regular while Germany is in its evening
# session, and Germany regular while the US is in premarket.
US_CLOCK = dt.datetime(2026, 1, 20, 18, 0)
DE_CLOCK = dt.datetime(2026, 1, 20, 10, 0)

REVISION = 'c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3'
OWNER = 'parity-producer:1'

# Exact names, never a LIKE on the prefix: real listings start with PT too
# (PTON, PTC, PTEN), and a cleanup that matched them would delete somebody
# else's universe rows.
PREFIX = 'PT'
TICKERS = tuple(f'{PREFIX}{index:02d}' for index in range(60))
POST_PREFIX = f'{PREFIX}parity-'
USER_PREFIX = f'{PREFIX}parity '
# The real pre-split stamp -- 16 hex characters, the column's whole width.
OLD_STAMP = '8106787f1fa72179'

# --- who the sixty are ------------------------------------------------------

LARGE = frozenset({0, 12, 24, 36, 48})
FUNDS = frozenset({6, 30, 54})
RECENT_IPOS = frozenset({18, 42})
# A large cap printing at three dollars is micro: segment_for lets a penny
# price overrule a reported cap.
PENNY = 36

# Which feeds carry each ticker, by index % 4: one venue, two, three, and two
# that leave Bluesky out -- so `venues=2` and every one-source selection cut a
# different set.
SOURCE_SETS = (
    ('bluesky',),
    ('bluesky', 'fourchan'),
    ('bluesky', 'fourchan', 'reddit:wallstreetbets'),
    ('fourchan', 'reddit:wallstreetbets'),
)
# Baselines too thin to divide by: `ratio` is None for these.
RATIO_NONE = frozenset({7, 17, 27, 37, 47, 57})
TRUNCATED = frozenset({5, 25, 45})
PROVISIONAL = frozenset({4, 22, 40})
WARMING_UP = frozenset({9, 33})
# A second bucket in the last hour (1h triplet), and one a day back (24h only).
LAST_HOUR = frozenset(range(0, 60, 2))
DAY_OLD = frozenset(range(0, 60, 5))
PRE_SPLIT = 2
SOURCE_DOWN = 10

# Twenty tickers without a move: fifteen never quoted, five quoted once.
NO_QUOTE = frozenset({1, 9, 17, 23, 25, 27, 31, 33, 35, 39, 43, 47, 51, 55, 59})
ONE_QUOTE = frozenset({2, 14, 26, 38, 49})
MOVING = frozenset(range(60)) - NO_QUOTE - ONE_QUOTE
# Three polls of one print: `no-print`, and never a divergence.
FROZEN = 13
# Repeats on purpose, so a move sort has ties to break.
MOVES = ('0.05', '-0.03', '0', '0.12', '-0.08', '0.05', '0.021', '-0.15', '0',
         '0.07')
# Quoted on both markets: a verified Tradegate primary plus the US tape.
XGAT = frozenset({3, 4, 10, 16, 21, 28, 34, 41, 46, 53})
# Mapped to Tradegate and never quoted there: the German board must show it
# unavailable, not dress its US quote up as German.
XGAT_SILENT = 45
# Its last Tradegate print is two hours old: shown, never scored.
XGAT_STALE = 53
# Daily closes behind a volatility estimate, without which no divergence.
US_HISTORY = frozenset(index for index in MOVING if index % 3 != 2)
XGAT_HISTORY = frozenset({3, 4, 10, 16, 21})

# Three accounts reading one key, and one whose enrichment will fail.
ACCOUNTS = (('one', ('PT05',)), ('two', ('PT58', 'PT01')), ('three', ()))
BROKEN = ('broken', ('PT07',))
ACCOUNT_KEYS = ('watching', 'watch_rows')

# The three operational summaries a serialized board freezes, as constants --
# so both paths write identical blocks and the blocks stay IN the digest. The
# market-data one echoes the instant it was asked about, which both paths must
# agree on as well.
SPEND = {'today_usd': 0.42, 'month_usd': 3.17}
SENTIMENT_OPS = {'backlog': 7, 'p95_age_seconds': 120.0}
MARKET_DATA_OPS = {'quotes_last_hour': 150, 'feeds': ['finnhub']}


def _at(minutes_ago):
    return NOW - dt.timedelta(minutes=minutes_ago)


def _money(value):
    return decimal.Decimal(value).quantize(decimal.Decimal('0.000001'))


# --- seeding helpers, in test_radar_board.py's shape ------------------------

def universe(index):
    ticker = TICKERS[index]
    name, cap, ipo, fund = f'{ticker} Parity Corp', None, None, False
    if index in FUNDS:
        name, fund = f'{ticker} Parity Index Fund', True
    elif index in LARGE:
        cap = '50000000000'
    elif index in RECENT_IPOS:
        cap, ipo = '2000000000', NOW.date() - dt.timedelta(days=90)
    elif index % 3 == 0:
        cap = '2000000000'                     # mid
    elif index % 3 == 1:
        cap = '100000000'                      # micro
    db.session.add(TickerUniverse(
        symbol=ticker, name=name, exchange='NASDAQ',
        first_seen=dt.datetime(2020, 1, 1), is_etf=fund,
        market_cap=decimal.Decimal(cap) if cap else None, ipo_date=ipo))


def bucket(ticker, minutes_ago, source, mentions, expected, variance, *,
           status='ok', baseline=30.0, stamp=None, z=None, scored=True):
    if scored and z is None:
        z = (mentions - expected) / variance ** 0.5
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=_at(minutes_ago), source=source,
        mention_count=mentions, high_confidence_count=mentions, low_count=0,
        distinct_authors=6, distinct_text_ratio=0.9,
        engagement_weighted_count=float(mentions), status=status,
        source_config_version=stamp or source_config_version(),
        expected=expected, variance=variance, mention_z=z if scored else None,
        baseline_days=baseline))


def post(ticker, number, minutes_ago, source, *, lexicon=0.0, llm=None,
         attitude=None, relevance=None, origin=None, confidence='high'):
    """One post and its one mention. A distinct author per post, as ever."""
    external = f'{POST_PREFIX}{ticker}-{number}'
    when = _at(minutes_ago)
    judged = attitude is not None or relevance is not None or origin is not None
    db.session.add(RadarPost(
        source=source, external_id=external, channel='parity',
        author=f'author-{external}', created_utc=when, body='x', score=0,
        num_comments=0, simhash=zlib.crc32(external.encode('utf-8')),
        first_seen=when, last_seen=when,
        mentions=[RadarMention(
            ticker=ticker, confidence=confidence, lexicon_sentiment=lexicon,
            llm_sentiment=llm, sentiment_attitude=attitude,
            sentiment_relevance=relevance or ('relevant' if judged else None),
            sentiment_content_origin=(origin or
                                      ('human_chatter' if judged else None)),
            sentiment_judged_at=when if judged else None)]))


def quote(ticker, minutes_ago, price, *, market='us', prev_close=None,
          printed_minutes_ago=None):
    fetched = _at(minutes_ago)
    printed = _at(minutes_ago if printed_minutes_ago is None
                  else printed_minutes_ago)
    us = market == 'us'
    db.session.add(RadarQuote(
        ticker=ticker, market=market, mic='XNAS' if us else 'XGAT',
        currency='USD' if us else 'EUR', provider_symbol=ticker,
        fetched_at=fetched, quote_ts=printed, price=price,
        prev_close=prev_close if prev_close is not None else price,
        provider_delay='live' if us else 'delayed', volume=None,
        source='finnhub' if us else 'deutsche_boerse_delayed',
        price_basis='trade', is_shadow=False))


def closes(ticker, index, base, *, market='us'):
    """Fifteen weekday closes before NOW, moving by -2..+2 percent."""
    us = market == 'us'
    days, day = [], NOW.date() - dt.timedelta(days=1)
    while len(days) < 15:
        if day.weekday() < 5:
            days.append(day)
        day -= dt.timedelta(days=1)
    for number, close_date in enumerate(sorted(days)):
        change = decimal.Decimal(((number * 7 + index) % 5) - 2) / 100
        db.session.add(RadarDailyClose(
            ticker=ticker, market=market, mic='XNAS' if us else 'XGAT',
            currency='USD' if us else 'EUR', close_date=close_date,
            close=(base * (1 + change)).quantize(decimal.Decimal('0.0001')),
            fetched_at=NOW - dt.timedelta(days=1),
            source='finnhub' if us else 'deutsche_boerse_delayed',
            price_basis='close', adjustment_basis='split', is_shadow=False))


def tone_posts(index):
    """Posts whose tones cover every kind the lean has to order.

    By index % 8. Net leans on the all-sources board: +2, -2, 0, None, 0, +2,
    None, +1 -- so there are ties at both signs and at zero, and two different
    roads to None.
    """
    ticker = TICKERS[index]
    first = SOURCE_SETS[index % 4][0]
    kind = index % 8
    if kind == 0:
        # Bullish, judged twice. The low-confidence bear is never scored and
        # the 02:00 one is outside the twelve-hour window.
        post(ticker, 1, 40, first, attitude='positive')
        post(ticker, 2, 200, first, lexicon=-0.2, attitude='positive')
        post(ticker, 3, 100, first, lexicon=-0.9, confidence='low')
        post(ticker, 4, 13 * 60, first, lexicon=-0.9)
    elif kind == 1:
        # Bearish: one judged, one only on the legacy projection -- which
        # outranks the word list's opposite reading.
        post(ticker, 1, 40, first, attitude='negative')
        post(ticker, 2, 200, first, lexicon=0.5, llm='bearish')
    elif kind == 2:
        # Neutral on the word list, never judged.
        post(ticker, 1, 40, first, lexicon=0.0)
        post(ticker, 2, 200, first, lexicon=0.0)
    elif kind == 3:
        # Unknown: nobody said anything about it at all.
        pass
    elif kind == 4:
        # Null: mentions with no score of any kind, not yet judged.
        post(ticker, 1, 40, first, lexicon=None)
        post(ticker, 2, 200, first, lexicon=None)
    elif kind == 5:
        # Bullish on two venues, so a one-venue selection sees half of it.
        post(ticker, 1, 40, 'bluesky', lexicon=0.6)
        post(ticker, 2, 200, 'fourchan', lexicon=0.0, llm='bullish')
    elif kind == 6:
        # Judged out of the denominator: irrelevant, and broadcast.
        post(ticker, 1, 40, first, lexicon=0.6, attitude='none',
             relevance='irrelevant')
        post(ticker, 2, 200, first, lexicon=-0.6, attitude='positive',
             origin='broadcast_or_automated')
    else:
        # One bullish word, and a judged mixed read that votes neither way.
        post(ticker, 1, 40, first, lexicon=0.3)
        post(ticker, 2, 200, first, lexicon=0.8, attitude='mixed')


# --- the fixture ------------------------------------------------------------

def _seed():
    for index in range(60):
        universe(index)

    for index, ticker in enumerate(TICKERS):
        sources = SOURCE_SETS[index % 4]
        for position, source in enumerate(sources):
            # 09:30: inside the twelve-hour window at all three clocks.
            bucket(ticker, 330, source,
                   mentions=6 + (index * 3 + position * 11) % 50,
                   expected=(0.05 if index in RATIO_NONE else
                             round(0.6 + ((index * 5 + position * 3) % 30) / 5.0,
                                   2)),
                   variance=1.0 + ((index * 7 + position) % 13) / 2.0,
                   status=('truncated' if index in TRUNCATED and position == 0
                           else 'ok'),
                   baseline=(7.0 if index in PROVISIONAL else
                             0.4 if index in WARMING_UP else 30.0))
        if index in LAST_HOUR:
            bucket(ticker, 30, sources[0], mentions=5 + index % 7,
                   expected=0.5, variance=1.0)
        if index in DAY_OLD:
            bucket(ticker, 20 * 60, sources[-1], mentions=8, expected=1.0,
                   variance=2.0)
        tone_posts(index)

    # The pre-split root, under the stamp it was written with: counted by
    # the series and the tone, invisible to every score.
    bucket(TICKERS[PRE_SPLIT], 195, 'reddit', mentions=7, expected=1.0,
           variance=2.0, stamp=OLD_STAMP, z=9.9)
    post(TICKERS[PRE_SPLIT], 9, 150, 'reddit', lexicon=0.6)
    # A feed that was down: a row, but not a measurement.
    bucket(TICKERS[SOURCE_DOWN], 180, 'bluesky', mentions=0, expected=None,
           variance=None, status='missing', scored=False)

    for index in sorted(MOVING):
        ticker = TICKERS[index]
        base = decimal.Decimal(3 if index == PENNY else 10 + index)
        if index == FROZEN:
            for minutes in (180, 90, 10):
                quote(ticker, minutes, _money(base), printed_minutes_ago=180)
            continue
        move = decimal.Decimal(MOVES[index % len(MOVES)])
        for minutes, fraction in ((360, 0), (180, move / 2), (10, move)):
            quote(ticker, minutes, _money(base * (1 + fraction)),
                  prev_close=_money(base))
        if index in US_HISTORY:
            closes(ticker, index, base)
    for index in sorted(ONE_QUOTE):
        quote(TICKERS[index], 10, _money(10 + index))

    for index in sorted(XGAT | {XGAT_SILENT}):
        db.session.add(RadarInstrument(
            ticker=TICKERS[index], market='de', venue='Tradegate', mic='XGAT',
            provider_symbol=TICKERS[index], currency='EUR', isin=None,
            is_primary=True, mapping_status='mapped', mapping_source='parity',
            mapped_at=NOW - dt.timedelta(days=30)))
    for index in sorted(XGAT):
        ticker = TICKERS[index]
        base = _money(decimal.Decimal(10 + index) * decimal.Decimal('0.9'))
        move = decimal.Decimal(MOVES[(index + 3) % len(MOVES)])
        times = (355, 240, 120) if index == XGAT_STALE else (355, 175, 5)
        for minutes, fraction in zip(times, (0, move / 2, move)):
            quote(ticker, minutes, _money(base * (1 + fraction)), market='de',
                  prev_close=base)
        if index in XGAT_HISTORY:
            closes(ticker, index, base, market='de')
    db.session.commit()

    from werkzeug.security import generate_password_hash
    accounts = {}
    for label, tickers in ACCOUNTS + (BROKEN,):
        user = AppUser(username=USER_PREFIX + label,
                       password_hash=generate_password_hash('x'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        accounts[label] = user.id
        # One at a time and in this order: `tickers_for` answers in the
        # order the marks were made, and ['PT58', 'PT01'] is not sorted.
        for ticker in tickers:
            watch.add(user.id, ticker)
    return accounts


def _forget_memos():
    """The process-level memos a board build reads through, for these rows."""
    coverage.clear_memo()
    for key in [key for key in list(leaderboard.sigma_cache)
                if key[0] in TICKERS]:
        leaderboard.sigma_cache.pop(key, None)


def _wipe():
    """Every row this module writes, by exact name. Both ends of the module:
    a run that died before its own cleanup must not decide the next one."""
    users = [user_id for (user_id,) in db.session.query(AppUser.id).filter(
        AppUser.username.like(USER_PREFIX + '%')).all()]
    RadarWatch.query.filter(sa.or_(
        RadarWatch.ticker.in_(TICKERS),
        RadarWatch.user_id.in_(users or [-1]))).delete(
            synchronize_session=False)
    AppUser.query.filter(AppUser.id.in_(users or [-1])).delete(
        synchronize_session=False)
    RadarMention.query.filter(RadarMention.ticker.in_(TICKERS)).delete(
        synchronize_session=False)
    RadarPost.query.filter(RadarPost.external_id.like(POST_PREFIX + '%')).delete(
        synchronize_session=False)
    for model in (RadarBucketSource, RadarQuote, RadarDailyClose,
                  RadarInstrument):
        model.query.filter(model.ticker.in_(TICKERS)).delete(
            synchronize_session=False)
    TickerUniverse.query.filter(TickerUniverse.symbol.in_(TICKERS)).delete(
        synchronize_session=False)
    db.session.commit()
    _forget_memos()


@pytest.fixture(scope='module')
def seeded():
    """The sixty tickers and four accounts, built once for the module.

    Once, because forty-odd cases each rebuilding a few hundred rows would
    spend the module's time on INSERTs. The rows are read-only to every test
    here, which is what makes sharing them safe.
    """
    with flask_app.app_context():
        if db.engine.url.database != DISPOSABLE:
            pytest.skip(f'not the disposable database: {db.engine.url.database}')
        _wipe()
        try:
            accounts = _seed()
        except BaseException:
            db.session.rollback()
            _wipe()
            raise
    try:
        yield accounts
    finally:
        with flask_app.app_context():
            db.session.rollback()
            _wipe()


class _Store:
    """One namespace of this test's own, and the producer's road into it."""

    def __init__(self, engine, ns):
        self.engine = engine
        self.ns = ns

    def publish(self, args, *, now=NOW):
        """admit -> claim -> build_blob -> publish, as `serve_once` does it.

        Built from `query_from_json(claim.key_json)` and not from the Query the
        caller's arguments parse to. That is what the producer builds from, and
        it is the whole point: the key sorts and deduplicates the sources, so
        a board built from the key is only the viewer's board if that
        normalisation cannot change the answer. A key already published here
        -- a second spelling of one question -- is left as it is.
        """
        query = api.parse_query(args, now=now)
        key_hash, key_json = board_keys.canonical(query)
        existing = board_store.read(self.engine, self.ns, key_hash)
        if existing is not None and existing.payload is not None:
            return key_hash, key_json

        assert board_store.admit(self.engine, self.ns, key_hash, key_json,
                                 now) == 'pending'
        claim = board_store.claim(self.engine, self.ns, OWNER, now,
                                  prefer='demand')
        assert claim is not None and claim.key_hash == key_hash
        assert board_keys.round_trips(claim.key_hash, claim.key_json)
        with flask_app.app_context():
            _forget_memos()
            blob, as_of, built_at, build_ms, _ = board_producer.build_blob(
                board_keys.query_from_json(claim.key_json), now=lambda: now)
        assert (as_of, built_at) == (now, now)
        assert board_store.publish(self.engine, self.ns, claim, blob,
                                   as_of=as_of, built_at=built_at,
                                   build_ms=build_ms,
                                   producer_revision=REVISION)
        return key_hash, key_json

    def read(self, args, *, now=NOW, user_id=None):
        with flask_app.app_context():
            _forget_memos()
            return board_shared.read_payload(self.engine, dict(args), now,
                                             user_id, poll=False)

    def stored(self, key_hash):
        return board_store.read(self.engine, self.ns, key_hash)


@pytest.fixture
def store(seeded, monkeypatch):
    """A namespace of this test's own, a private board memo, frozen ops."""
    with flask_app.app_context():
        engine = db.engine
        with engine.connect() as connection:
            if not connection.execute(sa.text(
                    "show tables like 'radar_board_results'")).first():
                pytest.fail('radar_board_results is missing: run '
                            'PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask '
                            'db upgrade first')

        name = 'perf3parity-' + secrets.token_hex(20)
        monkeypatch.setattr(board_namespace, 'namespace', lambda: name)
        monkeypatch.setattr(board_namespace, 'describe', lambda: {
            'payload_version': board_namespace.PAYLOAD_VERSION,
            'revision': REVISION, 'fingerprint': 'f' * 16, 'namespace': name})
        # `board_cache` is process-global: a board this file built must never
        # be served to a later test asking the same selection, nor the other
        # way round.
        monkeypatch.setattr(api, 'board_cache', {})
        monkeypatch.setattr(api.spend, 'summary', lambda: dict(SPEND))
        monkeypatch.setattr(api.llm_sentiment, 'ops_summary',
                            lambda: dict(SENTIMENT_OPS))
        monkeypatch.setattr(api.market_data, 'ops_summary', lambda now: {
            **MARKET_DATA_OPS, 'asked_at': api._iso_z(now)})
        board_shared.reset_namespace_memo()
        try:
            yield _Store(engine, name)
        finally:
            board_shared.reset_namespace_memo()
            with engine.begin() as connection:
                for table in ('radar_board_results', 'radar_board_namespaces'):
                    connection.execute(sa.text(
                        f'delete from {table} where namespace = :ns'),
                        {'ns': name})


# --- the comparison ---------------------------------------------------------

def _body(payload):
    """The board itself: everything but how it was delivered and to whom."""
    return {name: value for name, value in payload.items()
            if name not in board_shared.ENVELOPE_KEYS
            and name not in ACCOUNT_KEYS}


def digest(payload):
    return hashlib.sha256(json.dumps(
        _body(payload), sort_keys=True, default=str).encode('utf-8')).hexdigest()


def tickers(payload):
    return [row['ticker'] for row in payload['rows']]


def _short(value, width=400):
    text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= width else text[:width] + '...'


def explain(direct, shared):
    """Which payload keys differ, and the smallest diff of each."""
    left = json.loads(json.dumps(_body(direct), sort_keys=True, default=str))
    right = json.loads(json.dumps(_body(shared), sort_keys=True, default=str))
    keys = sorted(name for name in set(left) | set(right)
                  if name not in left or name not in right
                  or left[name] != right[name])
    lines = [f'payload keys that differ: {keys}']
    for name in keys:
        a, b = left.get(name), right.get(name)
        if name == 'rows' and isinstance(a, list) and isinstance(b, list):
            lines.append(f'rows: direct {len(a)} / shared {len(b)}')
            for position, (one, other) in enumerate(zip(a, b)):
                if one == other:
                    continue
                fields = sorted(field for field in set(one) | set(other)
                                if one.get(field) != other.get(field))
                lines.append(
                    f'first differing row #{position} ({one.get("ticker")} / '
                    f'{other.get("ticker")}): ' + '; '.join(
                        f'{field}: {_short(one.get(field), 160)} != '
                        f'{_short(other.get(field), 160)}' for field in fields))
                break
        else:
            lines.append(f'{name}: direct={_short(a)} shared={_short(b)}')
    return '\n'.join(lines)


def assert_same_board(direct, shared):
    """The two answers to one question are one board.

    The digest is the claim; the ticker order is asserted beside it so a
    failure names the rows. The envelope is compared as well rather than only
    subtracted: both boards were built and read at the same instant, so the
    ONLY field allowed to differ is `shared` itself.
    """
    assert direct['shared'] is False and shared['shared'] is True
    assert shared['pending'] is False and shared['rows'] is not None
    assert digest(direct) == digest(shared), explain(direct, shared)
    assert tickers(direct) == tickers(shared)
    assert direct['watching'] == shared['watching']
    assert direct['watch_rows'] == shared['watch_rows']
    assert set(direct) == set(shared)
    envelope = sorted(board_shared.ENVELOPE_KEYS - {'shared'})
    assert ({name: direct[name] for name in envelope} ==
            {name: shared[name] for name in envelope})


def assert_echoes(payload, args, now):
    """Every field that is the QUESTION says what was asked."""
    query = api.parse_query(args, now=now)
    assert payload['market'] == query.market
    assert payload['segments'] == list(query.segments)
    assert payload['window_hours'] == query.window
    assert payload['min_venues'] == query.min_venues
    assert payload['sort'] == query.sort
    assert payload['dir'] == query.direction
    assert payload['sources'] == sorted({api.source_root(name)
                                         for name in query.sources})


@dataclasses.dataclass
class Answer:
    direct: dict
    shared: dict
    key_hash: str
    key_json: str
    stored: board_store.Result


def direct_payload(args, *, now=NOW, user_id=None):
    with flask_app.app_context():
        _forget_memos()
        return api.build_payload_direct(dict(args), now=now, user_id=user_id)


def parity(store, args, *, now=NOW):
    """Both paths, one question, one instant -- and the store's own record."""
    direct = direct_payload(args, now=now)
    key_hash, key_json = store.publish(args, now=now)
    shared = store.read(args, now=now)
    assert_same_board(direct, shared)
    assert_echoes(shared, args, now)
    stored = store.stored(key_hash)
    assert stored.queue_state == 'idle'
    assert stored.as_of == now and stored.built_at == now
    assert stored.key_json == key_json
    return Answer(direct=direct, shared=shared, key_hash=key_hash,
                  key_json=key_json, stored=stored)


def lean(tone):
    """`board._lean_value`, from the wire's three counts."""
    if tone['bullish'] + tone['neutral'] + tone['bearish'] <= 0:
        return None
    return tone['bullish'] - tone['bearish']


def _keys(value):
    """Every dict key anywhere inside a decoded payload."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


# --- the fixture is what it claims to be ------------------------------------

def test_the_fixture_is_adversarial(store):
    """Asserted, not assumed: a parity test on a fixture that cannot tell two
    builds apart would pass whatever the two paths did.

    Every property below is one a parity case leans on. Distinct mention_z
    makes the default ranking a total order, which is what every stable-sort
    tie in the other keys falls back to -- without it, two correct builds
    could disagree about a tie and look like a finding.
    """
    assert api.default_market(NOW) == 'de'
    assert api.default_market(US_CLOCK) == 'us'
    assert api.default_market(DE_CLOCK) == 'de'

    boards = {market: direct_payload({'market': market, 'segment': '',
                                      'limit': '100'})
              for market in ('us', 'de')}
    for market, payload in boards.items():
        rows = payload['rows']
        assert len(rows) == 60, market
        assert len({row['mention_z'] for row in rows}) == 60, (
            f'{market}: the default ranking is not a total order')

        moves = [row['price_move'] for row in rows]
        valued = [move for move in moves if move is not None]
        assert None in moves and valued, market
        assert len(valued) > len(set(valued)), f'{market}: no tied move'

        divergences = [row['divergence'] for row in rows]
        assert None in divergences, market
        assert any(value is not None for value in divergences), market

        leans = [lean(row['tone']) for row in rows]
        known = [value for value in leans if value is not None]
        assert None in leans, market
        assert {-2, 0, 1, 2} <= set(known), market
        assert all(known.count(value) > 1 for value in (-2, 0, 1, 2)), (
            f'{market}: every lean value should be tied')
        assert any(row['tone']['bullish'] for row in rows)
        assert any(row['tone']['bearish'] for row in rows)
        assert any(row['tone']['neutral'] for row in rows)

        by_ticker = {row['ticker']: row for row in rows}
        assert all(by_ticker[TICKERS[index]]['ratio'] is None
                   for index in RATIO_NONE)
        assert sum(row['ratio'] is None for row in rows) == len(RATIO_NONE)

    us = {row['ticker']: row for row in boards['us']['rows']}
    de = {row['ticker']: row for row in boards['de']['rows']}
    assert sum(row['price_move'] is not None for row in us.values()) == 40
    assert us[TICKERS[FROZEN]]['price_status'] == 'stale'
    assert 'no-print' in us[TICKERS[FROZEN]]['marks']
    assert us[TICKERS[PENNY]]['segment'] == 'micro'
    # Germany: its own quotes, US fallbacks, and a mapped listing that is
    # silent rather than dressed in a dollar price.
    assert {de[TICKERS[index]]['quote']['mic'] for index in XGAT} == {'XGAT'}
    assert any(row['quote']['is_fallback'] for row in de.values())
    assert de[TICKERS[XGAT_SILENT]]['price'] is None
    assert us[TICKERS[XGAT_SILENT]]['price'] is not None
    assert de[TICKERS[XGAT_STALE]]['quote']['quality'] == 'stale'
    assert sum(row['divergence'] is not None for row in de.values()) == len(
        XGAT_HISTORY)

    # The source-version rule is exercised: PT02's pre-split root bucket is in
    # its 11:00 series point and nowhere in its score.
    pre_split = us[TICKERS[PRE_SPLIT]]
    series = {point['hour']: point['count'] for point in pre_split['series']}
    assert series['2026-01-20T11:00:00Z'] == 7
    assert pre_split['mentions'] == 12 + 23 + 34 + 7, (
        'the root reddit bucket reached the scored read')
    assert 'reddit' not in pre_split['sources']

    # Tone kinds in the rows themselves, including the two that leave no row.
    with flask_app.app_context():
        mentions = RadarMention.query.filter(
            RadarMention.ticker.in_(TICKERS)).all()
        assert any(m.sentiment_judged_at is not None for m in mentions)
        assert any(m.sentiment_judged_at is None and m.lexicon_sentiment is None
                   and m.llm_sentiment is None for m in mentions), 'no null tone'
        assert set(TICKERS) - {m.ticker for m in mentions}, 'no unknown tone'

    # Sort before limit: which fifty survive depends on the sort.
    memberships = {}
    for key in board_mod.SORT_KEYS:
        for direction in ('asc', 'desc'):
            payload = direct_payload({'market': 'us', 'segment': '',
                                      'sort': key, 'dir': direction})
            assert len(payload['rows']) == 50, (key, direction)
            memberships[(key, direction)] = frozenset(tickers(payload))
    default = frozenset(tickers(direct_payload({'market': 'us',
                                                'segment': ''})))
    distinct = set(memberships.values()) | {default}
    assert len(distinct) >= 2
    assert memberships[('ticker', 'asc')] != memberships[('ticker', 'desc')]
    assert memberships[('mentions', 'asc')] != memberships[('mentions', 'desc')]
    assert any(members != default for members in memberships.values())


# --- every sort, both directions, both markets, across the limit ------------

MATRIX = [
    pytest.param({'market': market, 'segment': '', 'sort': key,
                  'dir': direction, 'limit': str(limit)},
                 id=f'{market}-{key}-{direction}-{limit}')
    for market in ('us', 'de')
    for key in board_mod.SORT_KEYS
    for direction in ('asc', 'desc')
    for limit in (50, 100)
]

OTHERS = [
    # No sort named, the direction still asked for: the echo keeps it and so
    # does the key. The market is omitted, so this is Germany at NOW.
    pytest.param({'segment': '', 'dir': 'asc'}, id='no-sort-dir-asc'),
    pytest.param({'market': 'us', 'segment': '', 'venues': '2'},
                 id='venues-2'),
    pytest.param({'market': 'de'}, id='market-de'),
    pytest.param({'market': 'us', 'segment': '', 'sources': 'reddit'},
                 id='sources-reddit-root'),
    pytest.param({'market': 'us', 'segment': '',
                  'sources': 'reddit:wallstreetbets'},
                 id='sources-one-subreddit'),
]


@pytest.mark.parametrize('args', MATRIX + OTHERS)
def test_the_stored_board_is_the_direct_board(store, args):
    answer = parity(store, args)

    if 'limit' in args:
        # All sixty clear the floor, so a limit of fifty always cuts ten and
        # the sort decides which.
        assert len(answer.shared['rows']) == min(int(args['limit']), 60)
    if args.get('venues') == '2':
        assert answer.shared['excluded'].get('one_venue', 0) > 0
        assert all(len({api.source_root(name) for name in row['sources']}) > 1
                   for row in answer.shared['rows'])
    if args.get('dir') == 'asc' and 'sort' not in args:
        assert answer.shared['sort'] is None and answer.shared['dir'] == 'asc'
        assert json.loads(answer.key_json)['dir'] == 'asc'


# --- what the key keeps and what it normalises ------------------------------

def test_segments_are_keyed_verbatim_and_the_answer_does_not_care(store):
    """`mid,micro,mid` and `micro,mid` select the same rows and echo different
    chips, so they are two keys -- the PERF2 spike's collision, pinned."""
    answers = {segment: parity(store, {'market': 'us', 'segment': segment})
               for segment in ('', DEFAULT_SEGMENT, 'mid,micro,mid',
                               'micro,mid')}

    repeated, plain = answers['mid,micro,mid'], answers['micro,mid']
    assert repeated.key_hash != plain.key_hash
    assert repeated.shared['segments'] == ['mid', 'micro', 'mid']
    assert plain.shared['segments'] == ['micro', 'mid']
    assert digest(repeated.shared) != digest(plain.shared)
    assert tickers(repeated.shared) == tickers(plain.shared)

    # The limit cuts the default board too: fifty-one candidates in Discover.
    assert answers[DEFAULT_SEGMENT].shared['segment_counts']['discover'] == 51
    assert len(answers[DEFAULT_SEGMENT].shared['rows']) == 50
    assert len(answers[''].shared['rows']) == 50


@pytest.mark.parametrize('spellings', [
    ('bluesky,bluesky', 'bluesky'),
    ('reddit,bluesky', 'bluesky,reddit'),
], ids=['duplicates', 'order'])
def test_one_question_spelled_two_ways_is_one_key_and_one_board(store,
                                                                spellings):
    """Sources are the key's one normalisation. Each spelling is built as
    spelled on the direct path; the stored board is built once, from the
    sorted and deduplicated key -- and all of them must be the same bytes."""
    answers = [parity(store, {'market': 'us', 'segment': '', 'sources': value})
               for value in spellings]

    assert len({answer.key_hash for answer in answers}) == 1
    assert len({digest(answer.direct) for answer in answers} |
               {digest(answer.shared) for answer in answers}) == 1
    assert all(tickers(answer.shared) == tickers(answers[0].shared)
               for answer in answers)
    assert answers[0].shared['rows']


@pytest.mark.parametrize('clock, market', [
    (US_CLOCK, 'us'), (DE_CLOCK, 'de'), (NOW, 'de'),
], ids=['18:00-resolves-us', '10:00-resolves-de', '15:00-resolves-de'])
def test_an_omitted_market_is_keyed_by_the_market_it_resolved_to(
        store, clock, market):
    assert api.default_market(clock) == market

    answer = parity(store, {}, now=clock)

    assert json.loads(answer.key_json)['market'] == market
    assert answer.shared['market'] == market
    assert answer.key_hash == board_keys.canonical(
        api.parse_query({'market': market}, now=clock))[0]
    assert answer.shared['rows'], 'an empty board proves nothing'


def test_the_longest_selection_the_parser_accepts(store):
    """Thirty-seven sources -- every configured subreddit and three long legal
    placeholders -- given in an order the key will not keep."""
    subreddits = ['reddit:' + name for name in REDDIT_SUBS]
    fillers = [f'reddit:parity_placeholder_{number}_' + 'x' * 40
               for number in range(api.MAX_SOURCES - len(subreddits))]
    selection = list(reversed(subreddits + fillers))
    assert len(selection) == api.MAX_SOURCES == 37
    with pytest.raises(api.BadQuery):
        api.parse_query({'sources': ','.join(selection + ['reddit:one_more'])},
                        now=NOW)

    answer = parity(store, {'market': 'us', 'segment': '',
                            'sources': ','.join(selection)})

    assert len(answer.key_json) > 900
    assert answer.stored.key_json == answer.key_json
    assert board_keys.round_trips(answer.key_hash, answer.stored.key_json)
    assert answer.shared['sources'] == ['reddit']
    assert answer.shared['rows']


# --- accounts ---------------------------------------------------------------

def test_three_accounts_read_one_stored_board_and_keep_their_own_marks(
        store, seeded):
    """One blob, three readers. Each gets exactly the marks the direct path
    gives that account, and the blob carries nobody's."""
    args = {'market': 'us', 'segment': '', 'sort': 'lean', 'dir': 'desc'}
    key_hash, _ = store.publish(args)
    published = store.stored(key_hash).payload

    for label, watched in ACCOUNTS:
        user_id = seeded[label]
        direct = direct_payload(args, user_id=user_id)
        shared = store.read(args, user_id=user_id)
        assert_same_board(direct, shared)
        assert shared['watching'] == list(watched), label
        assert [row['ticker'] for row in shared['watch_rows']] == list(
            watched), label

    # Reading it wrote nothing back into it.
    assert store.stored(key_hash).payload == published
    text = zlib.decompress(published).decode('utf-8')
    keys = set(_keys(json.loads(text)))
    assert not keys & set(ACCOUNT_KEYS)
    assert not any('user' in key or 'account' in key for key in keys)
    for label, _ in ACCOUNTS + (BROKEN,):
        assert USER_PREFIX + label not in text


class PinnedRowsFailed(RuntimeError):
    """The enrichment half of a board response, failing."""


def test_a_failing_enrichment_fails_the_request_on_both_paths(
        store, seeded, monkeypatch):
    """The per-account half is not a cache and must not fail like one.

    Through the real route, as the fourth account, with the flag on after its
    board is stored and with the flag off. Healthy first, so the failure below
    is shown to be the enrichment's and nothing else's. The route reads its
    own clock; `build_payload` is wrapped only to hand it NOW, and the
    dispatch inside it is the real one.

    Under Flask's TESTING config an unhandled exception propagates to the test
    client instead of being rendered as the 500 a production worker answers,
    so "fails the request" is asserted as the exception itself -- identically
    on both paths. What neither path may do is swallow it into a 200 whose
    watch list came back empty.
    """
    args = {'market': 'us', 'segment': ''}
    url = '/radar/api/board?market=us&segment='
    store.publish(args)

    dispatch = api.build_payload
    monkeypatch.setattr(api, 'build_payload',
                        lambda request_args, now=None, user_id=None,
                        poll=False: dispatch(request_args, now=NOW,
                                             user_id=user_id, poll=poll))
    real_build, real_rows = board_mod.build, leaderboard.build_rows

    def forbidden(*args, **kwargs):
        raise AssertionError('the shared path built a board')

    def flag(state):
        monkeypatch.setenv('RADAR_BOARD_SHARED_RESULTS', state)
        # With the flag on, a build anywhere is the one thing that must not
        # happen: the stored board is what is being served.
        monkeypatch.setattr(board_mod, 'build',
                            forbidden if state == 'on' else real_build)
        monkeypatch.setattr(leaderboard, 'build_rows',
                            forbidden if state == 'on' else real_rows)
        monkeypatch.setattr(api, 'board_cache', {})
        _forget_memos()

    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session['user_id'] = seeded[BROKEN[0]]

        healthy = {}
        for state in ('on', 'off'):
            flag(state)
            response = client.get(url)
            assert response.status_code == 200, state
            healthy[state] = response.get_json()
        assert healthy['on']['shared'] is True
        assert healthy['off']['shared'] is False
        assert healthy['on']['watching'] == healthy['off']['watching'] == [
            'PT07']
        assert healthy['on']['watch_rows'] == healthy['off']['watch_rows']
        assert digest(healthy['on']) == digest(healthy['off'])

        def broken(*args, **kwargs):
            raise PinnedRowsFailed('pinned rows unavailable')

        monkeypatch.setattr(board_mod, 'build_pinned_rows', broken)
        outcomes = {}
        for state in ('on', 'off'):
            flag(state)
            try:
                response = client.get(url)
            except PinnedRowsFailed:
                outcomes[state] = 'raised'
            else:
                outcomes[state] = (response.status_code,
                                   response.get_json(silent=True))
    assert outcomes == {'on': 'raised', 'off': 'raised'}, outcomes
