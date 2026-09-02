# Radar Judge Gate and Post Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Judge only mentions of tickers that are watched or can reach the board outside the large/fund segments (about 81% less model spend), and label every post card with who judged its tone.

**Architecture:** A new `judge_gate.py` computes, per ingest cycle, the set of judgeable tickers from three queries (trailing-window mention counts, universe profiles, watch marks); `llm_sentiment.pending()` filters by that set and by the window; `run_pass` logs the gate and skips the API entirely when the set is empty; `ops_summary` reports what the gate holds back. Separately, `detail_panel._posts` adds `judged_by` from the same tone precedence and the post card prints it.

**Tech Stack:** Flask + SQLAlchemy (MySQL 8 dev, MariaDB prod), pytest against the dev DB; React 19 + TypeScript, vitest + testing-library.

**Spec:** `docs/superpowers/specs/2026-09-02-radar-judge-gate-design.md` — read it first; the spec wins on any conflict.

## Global Constraints

- Paths are relative to `personal_apps/` unless they start with `docs/`. Run `python -m pytest <files> -q -p no:cacheprovider`, `npx vitest run -c vite.radar.config.ts`, `npx tsc --noEmit` from `personal_apps/`; run `git` from the repo root.
- A ticker is judgeable when watched by any account, OR (segment not in `JUDGE_SKIP_SEGMENTS = ('large', 'fund')` AND in the trailing `JUDGE_FLOOR_HOURS = 24` hours it has ≥ `MIN_MENTIONS` (5) high-confidence mentions from ≥ `MIN_DISTINCT_AUTHORS` (3) distinct authors, over all sources). The text-ratio gate is ignored on purpose. `JUDGE_GATE_ENABLED = True` is the kill switch; `False` restores today's behaviour exactly.
- Segment comes from `universe.segment_for(market_cap, ipo_date, None, today, name, is_etf)` on the `TickerUniverse` row; no row → `unknown` → judged when reachable.
- With the gate on, `pending()` also drops mentions older than the window; older unjudged mentions stay unjudged forever. With the gate off nothing changes.
- The review tier, spend booking, eligibility sync and bucket correction are untouched.
- Post cards: `judged_by` is `'model'` when a v2 attitude or a legacy LLM label exists on the mention (a decided neutral counts), `'lexicon'` when only the local float exists, `null` when nothing scored it. Card text `Claude` / `wording` / nothing, muted, after the tone word.
- Every stored datetime is naive UTC. Test fixtures are future-dated (`NOW = dt.datetime(2027, 1, 1, 12, 0, 0)`) because suites run against the real dev DB without transactional isolation; seed prefixes `zzgate*` (posts) and `ZG*` (tickers) and clean them up.
- Commit after every task; never stage `.superpowers/`, `.claude/`, `static/radar/dist/`. Verification chains use `&&` only. Work on `dev_personal`; merge at the end.

---

### Task 1: `judge_gate.py` and the config constants

**Files:**
- Modify: `features/radar/config.py` (append three constants near `MIN_MENTIONS`, line ~864)
- Create: `features/radar/judge_gate.py`
- Test: `tests/test_radar_judge_gate.py`

**Interfaces:**
- Produces: `judge_gate.Gate` dataclass (`tickers: frozenset[str]`, `watched: int`, `reachable: int`, `skipped_segment: int`, `hours: int`, `skip_segments: tuple`, `enabled: bool`); `judge_gate.judgeable_tickers(now=None) -> Gate`; config `JUDGE_GATE_ENABLED`, `JUDGE_SKIP_SEGMENTS`, `JUDGE_FLOOR_HOURS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_judge_gate.py
"""Which tickers the model pass reads: watched ones, and reachable ones
outside the skipped segments. Real DB, future-dated seeds."""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import judge_gate
from models import RadarMention, RadarPost, RadarWatch, TickerUniverse
from conftest import _admin_id

NOW = dt.datetime(2027, 1, 1, 12, 0, 0)
AUTHORS = ['ann', 'bob', 'cy', 'dee', 'eve']


@pytest.fixture()
def clean():
    def wipe():
        RadarPost.query.filter(RadarPost.external_id.like('zzgate%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZG%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZG%')).delete(
            synchronize_session=False)
        db.session.commit()
    with flask_app.app_context():
        wipe()
        yield
        wipe()


def chatter(ticker, mentions, authors, minutes_ago=30):
    """`mentions` high-confidence mentions of `ticker` from `authors`
    distinct people, all `minutes_ago` before NOW."""
    when = NOW - dt.timedelta(minutes=minutes_ago)
    for i in range(mentions):
        post = RadarPost(source='bluesky', external_id=f'zzgate-{ticker}-{minutes_ago}-{i}',
                         channel='firehose', author=AUTHORS[i % authors],
                         created_utc=when, title=None, body=f'{ticker} chatter {i}',
                         first_seen=when, last_seen=when)
        db.session.add(post)
        db.session.flush()
        db.session.add(RadarMention(post_id=post.id, ticker=ticker, confidence='high',
                                    lexicon_sentiment=0.1))
    db.session.commit()


def profile(ticker, cap=None, is_etf=None):
    db.session.add(TickerUniverse(
        symbol=ticker, name=f'{ticker} Corp', exchange='Q',
        first_seen=dt.datetime(2020, 1, 1), is_etf=is_etf,
        market_cap=decimal.Decimal(cap) if cap else None))
    db.session.commit()


def gate():
    return judge_gate.judgeable_tickers(now=NOW)


# The gate reads every account's marks, and the dev DB carries real ones;
# counters are asserted as deltas against a baseline taken before seeding.
# Reachability is relative to NOW (2027), so real mentions contribute none.


def test_a_watched_ticker_is_judgeable_whatever_its_segment_or_volume(clean):
    with flask_app.app_context():
        baseline = gate()
        profile('ZGLARGE', cap='50000000000')
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZGLARGE', created_at=NOW))
        db.session.commit()

        g = gate()

        assert 'ZGLARGE' in g.tickers
        assert g.watched == baseline.watched + 1


def test_large_and_fund_tickers_are_skipped_even_with_plenty_of_chatter(clean):
    with flask_app.app_context():
        baseline = gate()
        profile('ZGLARGE', cap='50000000000')
        profile('ZGFUND', cap='900000000', is_etf=True)
        chatter('ZGLARGE', 8, 4)
        chatter('ZGFUND', 8, 4)

        g = gate()

        assert 'ZGLARGE' not in g.tickers
        assert 'ZGFUND' not in g.tickers
        assert g.reachable == baseline.reachable + 2
        assert g.skipped_segment == baseline.skipped_segment + 2


def test_the_floor_needs_five_mentions_from_three_voices(clean):
    with flask_app.app_context():
        for ticker in ('ZGFEW', 'ZGVOICE', 'ZGOK'):
            profile(ticker, cap='4000000')
        chatter('ZGFEW', 4, 3)      # under on mentions
        chatter('ZGVOICE', 5, 2)    # under on voices
        chatter('ZGOK', 5, 3)       # at the floor

        g = gate()

        assert 'ZGOK' in g.tickers
        assert 'ZGFEW' not in g.tickers
        assert 'ZGVOICE' not in g.tickers


def test_a_mention_outside_the_window_does_not_count(clean):
    with flask_app.app_context():
        profile('ZGOLD', cap='4000000')
        chatter('ZGOLD', 4, 3, minutes_ago=30)
        chatter('ZGOLD', 1, 1, minutes_ago=25 * 60)   # 25h ago: outside 24h

        assert 'ZGOLD' not in gate().tickers


def test_a_ticker_without_a_universe_row_is_judged_when_reachable(clean):
    with flask_app.app_context():
        chatter('ZGNOCAP', 5, 3)

        assert 'ZGNOCAP' in gate().tickers


def test_the_kill_switch_disables_the_gate(clean, monkeypatch):
    with flask_app.app_context():
        monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

        g = gate()

        assert g.enabled is False
        assert g.tickers == frozenset()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_judge_gate.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'judge_gate'`.

- [ ] **Step 3: Add the constants**

In `features/radar/config.py`, directly after the `MIN_DISTINCT_AUTHORS = 3` line (~865):

```python
# ---- the judge gate ---------------------------------------------------------
# What the model pass reads. Sized on the VPS on 2026-09-02: 1715 tickers were
# judged that day, 96 ever cleared the floor in a 24h window; large + fund
# took 61.5% of the spend, tickers that never reach the board 31.3%, both
# gates together 80.9%. A watched ticker is always read (the reader's mark
# says so); everything else must be outside the skipped segments AND able
# to reach the board -- MIN_MENTIONS mentions from MIN_DISTINCT_AUTHORS
# voices inside JUDGE_FLOOR_HOURS. The text-ratio gate is left out so the
# gate over-admits, never under-admits. 24h because the board's widest
# window is 24h. Not part of source_config_version: the gate changes what is
# judged, not what a mention means.
JUDGE_GATE_ENABLED = True            # False = judge everything, as before
JUDGE_SKIP_SEGMENTS = ('large', 'fund')
JUDGE_FLOOR_HOURS = 24
```

- [ ] **Step 4: Write `judge_gate.py`**

```python
# features/radar/judge_gate.py
"""Which tickers the model pass reads.

Judging costs money per mention and most mentions are of tickers nobody
will ever see: the floor keeps them off the board, and the large and fund
segments are the ones the reader cares least about. So the pass reads a
ticker only when someone watches it, or when it is outside the skipped
segments and can reach the board in the trailing window. Three queries,
no state, recomputed every cycle -- reachability changes hour by hour.
"""
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost, RadarWatch, TickerUniverse

from . import universe
from .config import (JUDGE_FLOOR_HOURS, JUDGE_GATE_ENABLED, JUDGE_SKIP_SEGMENTS,
                     MIN_DISTINCT_AUTHORS, MIN_MENTIONS)


@dataclasses.dataclass(frozen=True)
class Gate:
    """The judgeable set and the numbers behind it, for the log line."""
    tickers: frozenset
    watched: int
    reachable: int
    skipped_segment: int
    hours: int = JUDGE_FLOOR_HOURS
    skip_segments: tuple = JUDGE_SKIP_SEGMENTS
    # False only under the kill switch: the pass then ignores `tickers`
    # and reads everything, the pre-gate behaviour.
    enabled: bool = True


def _reachable(now, hours):
    """Tickers that clear the floor in the trailing window: MIN_MENTIONS
    high-confidence mentions from MIN_DISTINCT_AUTHORS distinct authors.
    NULL authors do not count as voices, the same as the board's rule."""
    since = now - dt.timedelta(hours=hours)
    rows = (db.session.query(RadarMention.ticker)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.confidence == 'high',
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now)
            .group_by(RadarMention.ticker)
            .having(sa.and_(
                sa.func.count(RadarMention.id) >= MIN_MENTIONS,
                sa.func.count(sa.distinct(RadarPost.author)) >= MIN_DISTINCT_AUTHORS))
            .all())
    return {ticker for (ticker,) in rows}


def _segments(tickers, today):
    """Segment per ticker, the way the board and the search decide it. No
    price at hand: the penny override only matters on a board row."""
    if not tickers:
        return {}
    profiles = {u.symbol: u for u in TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()}
    out = {}
    for ticker in tickers:
        u = profiles.get(ticker)
        out[ticker] = ('unknown' if u is None else universe.segment_for(
            u.market_cap, u.ipo_date, None, today, u.name, u.is_etf))
    return out


def _watched():
    return {ticker for (ticker,) in db.session.query(RadarWatch.ticker).distinct().all()}


def judgeable_tickers(now=None):
    """The gate for this cycle."""
    now = now or dt.datetime.utcnow()
    if not JUDGE_GATE_ENABLED:
        return Gate(tickers=frozenset(), watched=0, reachable=0,
                    skipped_segment=0, enabled=False)
    reachable = _reachable(now, JUDGE_FLOOR_HOURS)
    segments = _segments(reachable, now.date())
    admitted = {t for t in reachable if segments[t] not in JUDGE_SKIP_SEGMENTS}
    watched = _watched()
    return Gate(tickers=frozenset(admitted | watched),
                watched=len(watched),
                reachable=len(reachable),
                skipped_segment=len(reachable) - len(admitted))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_judge_gate.py -q -p no:cacheprovider`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/features/radar/judge_gate.py personal_apps/tests/test_radar_judge_gate.py
git commit -m "feat(radar): the judge gate -- watched, or reachable outside large and fund

Three queries per cycle, no state: trailing-window counts, universe
profiles through the board's own segment_for, the watch marks. Kill
switch in config.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `pending()` and `run_pass()` honour the gate

**Files:**
- Modify: `features/radar/llm_sentiment.py` (`pending`, `pending_v2` alias unchanged, `run_pass`; import `judge_gate`)
- Modify: `tests/test_radar_llm_sentiment.py` (an autouse fixture, `make_post` gains `when`, new tests)

**Interfaces:**
- Consumes: `judge_gate.judgeable_tickers(now)`, `Gate`.
- Produces: `pending(limit=PASS_LIMIT, tickers=None, since=None)`; `run_pass(client=None, limit=PASS_LIMIT, model=PRIMARY_MODEL, now=None)`; one log line per gated cycle.

- [ ] **Step 1: Keep the existing suite meaningful under the gate**

The existing tests seed one `ZZA` mention and expect it judged; under the gate a lone mention is not judgeable. Add, after the `clean_posts` fixture in `tests/test_radar_llm_sentiment.py`:

```python
@pytest.fixture(autouse=True)
def gate_off(monkeypatch):
    """The pass tests below are about the pass, not the gate: a lone seeded
    mention must still be judged. The gate tests re-enable it explicitly."""
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)
```

and give `make_post` a time: change its signature to `def make_post(external_id, ticker='ZZA', confidence='high', llm=None, body='ZZA ripping', judged_at=None, when=NOW):` and use `when` for `created_utc`, `first_seen`, `last_seen`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_radar_llm_sentiment.py`:

```python
def gate_on(monkeypatch):
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', True)


def test_pending_honours_a_ticker_set_and_a_window(clean_posts):
    with flask_app.app_context():
        a = make_post('zztest-gate-a', ticker='ZZA')
        b = make_post('zztest-gate-b', ticker='ZZB')
        old = make_post('zztest-gate-old', ticker='ZZB', when=NOW - dt.timedelta(hours=30))

        only_b = {m.id for m, _ in llm_sentiment.pending(50, tickers={'ZZB'})}
        assert b in only_b and old in only_b and a not in only_b

        windowed = {m.id for m, _ in llm_sentiment.pending(
            50, tickers={'ZZB'}, since=NOW - dt.timedelta(hours=24))}
        assert windowed == {b}

        assert llm_sentiment.pending(50, tickers=frozenset()) == []


def test_run_pass_with_an_empty_gate_makes_no_call_and_books_nothing(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    with flask_app.app_context():
        make_post('zztest-gate-lone', ticker='ZZLONE')      # one mention: under the floor
        client = FakeClient([])                             # any call would pop from empty
        spent_before = db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL))
        calls_before = spent_before.calls if spent_before else 0

        judged = llm_sentiment.run_pass(client=client, limit=5, now=NOW)

        assert judged == 0
        assert client.messages.requests == []
        spent = db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL))
        assert (spent.calls if spent else 0) == calls_before


def test_a_watched_tickers_backlog_inside_the_window_is_judged(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    from conftest import _admin_id
    from models import RadarWatch
    with flask_app.app_context():
        RadarWatch.query.filter_by(ticker='ZZW').delete()
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZZW', created_at=NOW))
        db.session.commit()
        fresh = make_post('zztest-gate-w-new', ticker='ZZW', when=NOW - dt.timedelta(hours=1))
        stale = make_post('zztest-gate-w-old', ticker='ZZW', when=NOW - dt.timedelta(hours=30))
        client = FakeClient([answer([entry(1)], usage=usage_of(100, 20))])
        try:
            judged = llm_sentiment.run_pass(client=client, limit=5, now=NOW)

            assert judged == 1
            assert db.session.get(RadarMention, fresh).sentiment_judged_at is not None
            assert db.session.get(RadarMention, stale).sentiment_judged_at is None
        finally:
            RadarWatch.query.filter_by(ticker='ZZW').delete()
            db.session.commit()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_llm_sentiment.py -q -p no:cacheprovider -k "gate or window"`
Expected: FAIL — `TypeError: pending() got an unexpected keyword argument 'tickers'`.

- [ ] **Step 4: Implement**

In `features/radar/llm_sentiment.py`, extend the local import to `from . import config, judge_gate, sentiment_input, spend` and replace `pending`:

```python
def pending(limit=PASS_LIMIT, tickers=None, since=None):
    """[(mention, post)] for high-confidence mentions with no v2 judgment.

    Only `high`: RadarMention holds high or low, `medium` is awarded in
    memory at rollup and never written back, and `low` is never scored.
    Newest first -- a backlog means the newest posts are the ones a live
    board is about to render. Keyed on sentiment_judged_at, not the
    legacy llm_sentiment: the projection column keeps being written for
    compatibility and must not hide unjudged rows.

    `tickers` narrows the pick to the judge gate's set (judge_gate.py) and
    `since` to its window; None for either means no narrowing, the
    pre-gate behaviour the rejudge script and the pass tests rely on. An
    empty set answers [] without a query.
    """
    if tickers is not None and not tickers:
        return []
    query = (db.session.query(RadarMention, RadarPost)
             .join(RadarPost, RadarPost.id == RadarMention.post_id)
             .filter(RadarMention.confidence == 'high',
                     RadarMention.sentiment_judged_at.is_(None),
                     RadarPost.created_utc >= V2_ACTIVATION_CUTOFF))
    if tickers is not None:
        query = query.filter(RadarMention.ticker.in_(list(tickers)))
    if since is not None:
        query = query.filter(RadarPost.created_utc >= since)
    return query.order_by(RadarPost.created_utc.desc()).limit(limit).all()
```

and the head of `run_pass`:

```python
def run_pass(client=None, limit=PASS_LIMIT, model=PRIMARY_MODEL, now=None):
    """Judge the pending mentions with the v2 prompt. Returns how many.

    Reads only what the judge gate admits (judge_gate.py): watched
    tickers, and tickers outside the skipped segments that can reach the
    board in the trailing window. Older backlog of an admitted ticker
    stays unjudged; it keeps counting provisionally and nothing shows it.

    Books what it cost off the responses rather than estimating, which
    keeps the figure exact for radar specifically.
    """
    now = now or dt.datetime.utcnow()
    gate = judge_gate.judgeable_tickers(now)
    if gate.enabled:
        rows = pending(limit, tickers=gate.tickers,
                       since=now - dt.timedelta(hours=gate.hours))
        logger.info('radar judge gate: %d judgeable (%d watched, %d reachable, '
                    '%d skipped by segment); %d mentions picked',
                    len(gate.tickers), gate.watched, gate.reachable,
                    gate.skipped_segment, len(rows))
    else:
        rows = pending(limit)
    if not rows:
        return 0
    # ... the rest unchanged (meter, judge, spend.record, apply, sync, commit, rebuild)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_llm_sentiment.py tests/test_radar_sentiment_v2.py tests/test_radar_daemon.py tests/test_radar_judge_gate.py -q -p no:cacheprovider`
Expected: all pass (the three new tests plus the pre-existing pass tests under `gate_off`). If `test_radar_daemon.py` or `test_radar_sentiment_v2.py` seeds a lone mention and calls `run_pass` expecting it judged, add the same `gate_off` autouse fixture there and say so in the report — never loosen the assertion.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/llm_sentiment.py personal_apps/tests/test_radar_llm_sentiment.py
git commit -m "feat(radar): the judge pass reads only what the gate admits

pending() narrows to the gate's tickers and window; an empty gate makes
no API call and books nothing; one log line per cycle says what the
gate did. Kill switch off restores the old pass exactly.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `ops_summary` reports what the gate holds back

**Files:**
- Modify: `features/radar/llm_sentiment.py` (`pending_count`, `ops_summary`, new `gated_count`)
- Modify: `static/radar/src/types.ts` (`sentiment_ops.gated_pending`)
- Modify: `static/radar/src/list/Spend.tsx`
- Test: `tests/test_radar_llm_sentiment.py` (append), `static/radar/src/list/Spend.test.tsx` (append)

**Interfaces:**
- Produces: `pending_count(tickers=None, since=None) -> int`; `gated_count(gate, now) -> int`; `ops_summary()` keys `pending` (what the pass will still take), `gated_pending` (held back), the rest unchanged; client `sentiment_ops.gated_pending: number`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_llm_sentiment.py`:

```python
def test_ops_summary_counts_the_gated_backlog_apart_from_the_pending_one(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    from conftest import _admin_id
    from models import RadarWatch
    with flask_app.app_context():
        RadarWatch.query.filter_by(ticker='ZZW').delete()
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZZW', created_at=NOW))
        db.session.commit()
        make_post('zztest-ops-w', ticker='ZZW', when=NOW - dt.timedelta(hours=1))      # admitted
        make_post('zztest-ops-lone', ticker='ZZLONE', when=NOW - dt.timedelta(hours=1)) # held back
        make_post('zztest-ops-old', ticker='ZZW', when=NOW - dt.timedelta(hours=30))    # outside the window
        try:
            before = llm_sentiment.ops_summary(now=NOW)
            # Only the seeded rows carry these tickers; the dev DB's own
            # backlog is far older than NOW and outside the window.
            assert before['pending'] == 1
            assert before['gated_pending'] == 1
        finally:
            RadarWatch.query.filter_by(ticker='ZZW').delete()
            db.session.commit()
```

Append to `static/radar/src/list/Spend.test.tsx` (inside `describe('the review meter line', ...)` or as a third describe; reuse the file's existing payload helper — read it first):

```tsx
  it('says how many mentions the gate left unread', () => {
    render(<Spend payload={payload({
      spend: { today_usd: 0.42, month_usd: 3.1, unpriced_tokens: 0 },
      sentiment_ops: { pending: 12, gated_pending: 1234, p95_age_minutes: 3,
        review: { demanded: 0, attempted: 0, served: 0, capped: 0, over_ceiling: 0 } },
    })} />)
    expect(screen.getByText(/1,234/)).toBeInTheDocument()
    expect(screen.getByText(/left unread/)).toBeInTheDocument()
  })
```

(`payload` here is whatever helper `Spend.test.tsx` already uses to build a `BoardPayload` — if it imports one from `../fixtures`, use that: `payload({...})` from `static/radar/src/fixtures.ts` accepts overrides.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_llm_sentiment.py -q -p no:cacheprovider -k gated_backlog && npx vitest run -c vite.radar.config.ts static/radar/src/list/Spend.test.tsx`
Expected: FAIL — `KeyError: 'gated_pending'`; and `Unable to find an element with the text: /left unread/`.

- [ ] **Step 3: Implement the server side**

In `features/radar/llm_sentiment.py`, replace `pending_count` and add `gated_count`:

```python
def _unjudged(since=None):
    """The unjudged high-confidence mentions the live pass could owe."""
    query = (db.session.query(RadarMention.id, RadarMention.ticker, RadarPost.created_utc)
             .join(RadarPost, RadarPost.id == RadarMention.post_id)
             .filter(RadarMention.confidence == 'high',
                     RadarMention.sentiment_judged_at.is_(None),
                     RadarPost.created_utc >= V2_ACTIVATION_CUTOFF))
    if since is not None:
        query = query.filter(RadarPost.created_utc >= since)
    return query


def pending_count(tickers=None, since=None):
    """How many mentions the LIVE pass still owes. For the daemon log.

    Same activation cutoff as pending(): the legacy backlog is the rejudge
    script's business and must not read as a live backlog here or in
    ops_summary's p95. With the gate's `tickers` and `since`, counts only
    what the pass will actually take.
    """
    if tickers is not None and not tickers:
        return 0
    query = _unjudged(since)
    if tickers is not None:
        query = query.filter(RadarMention.ticker.in_(list(tickers)))
    return query.count()


def gated_count(gate, now):
    """Unjudged mentions inside the window that the gate holds back --
    what was NOT spent. Zero when the gate is off."""
    if not gate.enabled:
        return 0
    query = _unjudged(now - dt.timedelta(hours=gate.hours))
    if gate.tickers:
        query = query.filter(~RadarMention.ticker.in_(list(gate.tickers)))
    return query.count()
```

and in `ops_summary`, replace the `waiting = pending_count()` line and the p95 query's filters so both follow the gate:

```python
    now = now or dt.datetime.utcnow()
    gate = judge_gate.judgeable_tickers(now)
    tickers = gate.tickers if gate.enabled else None
    since = now - dt.timedelta(hours=gate.hours) if gate.enabled else None
    waiting = pending_count(tickers=tickers, since=since)
    p95 = None
    if waiting:
        offset = int(waiting * 0.05)
        query = (db.session.query(RadarPost.created_utc)
                 .join(RadarMention, RadarMention.post_id == RadarPost.id)
                 .filter(RadarMention.confidence == 'high',
                         RadarMention.sentiment_judged_at.is_(None),
                         RadarPost.created_utc >= V2_ACTIVATION_CUTOFF))
        if tickers is not None:
            query = query.filter(RadarMention.ticker.in_(list(tickers)))
        if since is not None:
            query = query.filter(RadarPost.created_utc >= since)
        oldest_5th = query.order_by(RadarPost.created_utc.asc()).offset(offset).limit(1).scalar()
        if oldest_5th is not None:
            p95 = max(0.0, (now - oldest_5th).total_seconds() / 60.0)
```

and add `'gated_pending': gated_count(gate, now)` to the returned dict, beside `'pending': waiting`. The daemon's log call `llm_sentiment.pending_count()` in `run_radar_ingest.py:1055` keeps its ungated meaning (total owed) — leave it.

- [ ] **Step 4: Implement the client side**

`static/radar/src/types.ts`, inside `sentiment_ops`: after `pending: number` add

```ts
    /** Unjudged mentions in the window the judge gate held back -- what
     *  was not spent. Absent on payloads embedded before the gate. */
    gated_pending?: number
```

`static/radar/src/list/Spend.tsx`, after the review sentence inside the `<p className="below">`:

```tsx
      {(payload.sentiment_ops?.gated_pending ?? 0) > 0 && (
        // The gate's day so far: mentions it declined to read because their
        // ticker cannot reach the board or sits in a skipped segment.
        <> {count(payload.sentiment_ops!.gated_pending!)} mentions left unread by the gate.</>
      )}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_llm_sentiment.py tests/test_radar_api.py -q -p no:cacheprovider && npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all pass (`test_radar_api.py` renders `sentiment_ops` through the board payload; vitest full suite + 1).

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/llm_sentiment.py personal_apps/tests/test_radar_llm_sentiment.py personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/list/Spend.tsx personal_apps/static/radar/src/list/Spend.test.tsx
git commit -m "feat(radar): the ops line says what the judge gate left unread

pending now counts what the pass will take; gated_pending what it held
back inside the window; the spend footnote prints it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Post cards say who judged

**Files:**
- Modify: `features/radar/detail_panel.py` (`_posts`, new `_judged_by`)
- Modify: `features/radar/routes/api.py` (~line 610-618, the posts serialization)
- Modify: `static/radar/src/types.ts` (`Post.judged_by`)
- Modify: `static/radar/src/detail/Posts.tsx`
- Modify: `static/radar/radar.css` (after `.post.bear .ptone`, ~line 1354)
- Modify: `static/radar/src/fixtures.ts` (posts in `detail()` stay `[]`; no change needed unless a fixture post is added)
- Test: `tests/test_radar_detail.py` (append), `static/radar/src/detail/Posts.test.tsx` (create)

**Interfaces:**
- Produces: `_posts()` returns `([(post, tone, judged_by)], total)` with `judged_by in ('model', 'lexicon', None)`; API post dict gains `judged_by`; `Post.judged_by: 'model' | 'lexicon' | null`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_detail.py` (its helpers `post_for`, `panel_ticker`, `PREFIX`, `NOW`, `clean` exist; `post_for` marks the mention judged when `attitude`/`relevance`/`origin` is given):

```python
def test_each_post_says_who_judged_it(clean):
    """The label follows the same precedence as the tone, so it can never
    disagree with the colour: model for a v2 attitude or a legacy label
    (a decided neutral included), lexicon for the local float alone."""
    from features.radar import detail_panel
    from models import RadarMention, RadarPost
    ticker = f'{PREFIX}J'
    post_for(ticker, 10, 'ann', 'to the moon', attitude='positive')           # model, bullish
    post_for(ticker, 20, 'bob', 'meh', attitude='none')                        # model, neutral
    post_for(ticker, 30, 'cy', 'looks weak', llm_sentiment='bearish')          # model (legacy)
    post_for(ticker, 40, 'dee', 'to the moon again')                           # lexicon, bullish
    post_for(ticker, 50, 'eve', 'nothing has scored this yet')                 # nothing at all
    unscored = (db.session.query(RadarMention)
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarMention.ticker == ticker, RadarPost.author == 'eve').one())
    unscored.lexicon_sentiment = None      # post_for always scores; undo that here
    db.session.commit()

    posts, total = detail_panel._posts(ticker, ['bluesky'], NOW - dt.timedelta(hours=2), NOW)

    assert total == 5
    by_author = {post.author: (tone, judged_by) for post, tone, judged_by in posts}
    assert by_author['ann'] == ('bullish', 'model')
    assert by_author['bob'] == ('neutral', 'model')
    assert by_author['cy'] == ('bearish', 'model')
    assert by_author['dee'] == ('bullish', 'lexicon')
    assert by_author['eve'] == ('neutral', None)
```

Create `static/radar/src/detail/Posts.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Posts } from './Posts'
import type { Post } from '../types'

const post = (over: Partial<Post>): Post => ({
  source: 'bluesky', author: 'ann', channel: 'firehose', created: '2026-09-02T14:00:00Z',
  title: null, body: 'to the moon', url: null, tone: 'bullish', judged_by: 'model', ...over,
})

describe('who judged a post', () => {
  it('prints Claude for the model, wording for the lexicon, nothing when unscored', () => {
    const { container } = render(<Posts total={3} posts={[
      post({ author: 'ann', judged_by: 'model' }),
      post({ author: 'bob', judged_by: 'lexicon', tone: 'bearish' }),
      post({ author: 'cy', judged_by: null, tone: 'neutral' }),
    ]} />)

    const labels = Array.from(container.querySelectorAll('.post')).map(
      (card) => card.querySelector('.pby')?.textContent ?? '')
    expect(labels).toEqual(['Claude', 'wording', ''])
    expect(screen.getByText('Claude')).toHaveClass('pby')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_detail.py -q -p no:cacheprovider -k who_judged && npx vitest run -c vite.radar.config.ts static/radar/src/detail/Posts.test.tsx`
Expected: FAIL — `ValueError: not enough values to unpack (expected 3, got 2)`; and `expected [ '', '', '' ] to deeply equal [ 'Claude', 'wording', '' ]`.

- [ ] **Step 3: Server**

In `features/radar/detail_panel.py`, add below `_tone_of`:

```python
def _judged_by(local, legacy, attitude):
    """Who decided the tone _tone_of returns -- the same precedence, so
    the label can never disagree with the colour. 'model' for a v2
    attitude or a legacy LLM label (a decided neutral counts: the model
    read it and found no lean); 'lexicon' when only the local float has
    scored it; None when nothing has."""
    if attitude is not None or legacy is not None:
        return 'model'
    if local is not None:
        return 'lexicon'
    return None
```

and change the `posts = [...]` line in `_posts` to:

```python
    posts = [(post, _tone_of(local, legacy, attitude) or 'neutral',
              _judged_by(local, legacy, attitude))
             for post, local, legacy, attitude in rows]
```

Update the docstring's "Returns ([(post, tone)], total)" to "Returns ([(post, tone, judged_by)], total)". In `features/radar/routes/api.py` (~line 605-618) change `for p, tone in d.posts` to `for p, tone, judged_by in d.posts` and add, after `'tone': tone,`:

```python
            # Who decided that tone: the model, or the local wording score.
            'judged_by': judged_by,
```

Grep for any other consumer of `d.posts` / `.posts` tuples (`grep -rn "for .*tone in" features/radar tests`) and update it the same way.

- [ ] **Step 4: Client**

`static/radar/src/types.ts`, in `Post` after `tone`:

```ts
  /** Who decided `tone`: the model (a decided neutral included), the local
   *  wording score, or nothing yet. */
  judged_by: 'model' | 'lexicon' | null
```

`static/radar/src/detail/Posts.tsx`, directly after the `.ptone` span:

```tsx
                {post.judged_by && (
                  // A fact, not a badge: who read this post -- the model, or
                  // the wording score that stands in until it does.
                  <span className="pby">{post.judged_by === 'model' ? 'Claude' : 'wording'}</span>
                )}
```

`static/radar/radar.css`, after `.post.bear .ptone { color: var(--down); }`:

```css
/* Who judged the post, beside the tone word: same size, never coloured --
   the colour belongs to the tone, the provenance is a fact. */
.phead .pby { flex: none; font-size: var(--t-xs); color: var(--muted); }
```

If `hardening.test.tsx` or `BoardPage.test.tsx` build `Post` objects inline, add `judged_by: null` to them (the field is required so a forgotten producer fails typecheck).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -q -p no:cacheprovider && npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/detail_panel.py personal_apps/features/radar/routes/api.py personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/detail/Posts.tsx personal_apps/static/radar/src/detail/Posts.test.tsx personal_apps/static/radar/radar.css personal_apps/tests/test_radar_detail.py
git commit -m "feat(radar): each post says who judged it

judged_by from the same precedence as the tone -- Claude for the model,
wording for the lexicon float, nothing when unscored -- printed muted
beside the tone word.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Gate, verify, merge

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-radar-judge-gate-design.md` (status line)

- [ ] **Step 1: Full gate**

From `personal_apps/`:

```bash
npx vitest run -c vite.radar.config.ts && npx tsc --noEmit && npx vite build -c vite.radar.config.ts && python -m pytest tests/test_radar_judge_gate.py tests/test_radar_llm_sentiment.py tests/test_radar_sentiment_v2.py tests/test_radar_daemon.py tests/test_radar_detail.py tests/test_radar_api.py -q -p no:cacheprovider
```

Expected: every suite green.

- [ ] **Step 2: Browser check of the post labels**

Start the Flask dev server (`preview_start` name `personal_apps`, port 5001) and run a python-playwright script with the minted session cookie (`scratchpad/radar_cookie.txt`, value after `session=`): open `/radar/?market=us&window=24&t=<a ticker with posts>`, wait for `.post`, print `[...document.querySelectorAll('.post')].map(p => [p.querySelector('.ptone')?.textContent, p.querySelector('.pby')?.textContent])`, screenshot the panel at 1440×900 and 390×844, and view the PNGs. Expect `Claude` on judged posts, `wording` on unjudged posts that carry a lexicon score, and no label on a post nothing has scored (rare live: ingest scores every mention; if the window has none, the Python test covers it); nothing overlapping the author handle.

- [ ] **Step 3: Dry-run the gate against the dev DB**

From `personal_apps/`: `python -c "from app import app; from features.radar import judge_gate; import datetime as dt; app.app_context().push(); g = judge_gate.judgeable_tickers(); print(len(g.tickers), g.watched, g.reachable, g.skipped_segment)"` — a prod copy gives numbers of the order of the sizing (tens of judgeable tickers, a few hundred reachable, most of those skipped by segment); print them in the report.

- [ ] **Step 4: Docs and merge**

Change the spec's status line to `**Status:** built <date> (plan docs/superpowers/plans/2026-09-02-radar-judge-gate.md)`, commit it, then:

```bash
git checkout main && git merge dev_personal && git push origin main && git push origin dev_personal && git checkout dev_personal
```

Deploy is routine (`update_coc.sh` restarts `radar_ingest`, which picks the gate up on its next cycle). The first gated cycle logs `radar judge gate: ...` in `journalctl -u radar_ingest.service`; the masthead footnote shows `N mentions left unread by the gate` once it has held anything back.
