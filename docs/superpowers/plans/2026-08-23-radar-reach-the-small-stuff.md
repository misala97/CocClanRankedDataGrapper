# Radar: Reach the Small Stuff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the board reach penny stocks and unknowns — by fixing a distinctiveness bug that silently blocks promotion, by stopping the Bluesky firehose from discarding bare mentions, and by opening on the segment the tool exists for.

**Architecture:** Distinctiveness counts issuers rather than listings, with its tunables moved into `config` so the version stamp can see them. Bluesky's bare-token flag flips behind a live measurement. `Small` is a segment *group* resolved at read time, not a sixth segment value.

**Tech Stack:** Flask + SQLAlchemy, React 19 + TypeScript + Vite island, pytest + vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-radar-reach-the-small-stuff-design.md`. Read it before Task 1.
- **No new source.** Telegram and InvestorsHub are both closed — see the spec's context section. Nothing here adds a venue.
- **No size penalty in the ranking.** `mention_z` already measures each ticker against its own baseline. A second mechanism doing the same job would fight it.
- **Tasks 1–3 change what gets counted**, so they reset baselines. Ship them as one batch: one warm-up, not three.
- Files are CRLF. Prefer the Edit tool; LF-keyed `str.replace` silently no-ops here.
- TypeScript runs `strict` + `noUncheckedIndexedAccess`. `npm run build` typechecks gym **and** radar.
- Run pytest from `personal_apps/`; radar vitest with `-c vite.radar.config.ts`.
- Four pytest failures in `test_gym_ownership`, `test_gym_exercise_ownership` and `test_gym_routes_smoke` are pre-existing dev-database state. Ignore them.

---

### Task 1: Move the distinctiveness tunables, and hash them

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/features/radar/universe.py`
- Test: `personal_apps/tests/test_radar_config.py`

**Interfaces:**
- Produces, in `config`: `MAX_NAME_TOKEN_DF`, `MAX_NAME_TOKEN_RATIO`, `MIN_NAME_TOKEN_LEN`, `FUND_NAME_PATTERN`, and their inclusion in `source_config_version()`.
- `universe` imports all four from `config` instead of defining them.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_the_version_stamp_covers_the_distinctiveness_rule():
    """Distinctiveness decides whether a bare mention is promoted to `high`,
    so changing it changes WHICH mentions get counted -- the exact
    discontinuity the stamp warms up from. It hashed the source list and the
    extraction patterns but not this, which is the same omission that shipped
    three extraction fixes over stale baselines on 2026-08-22.
    """
    from features.radar import config

    before = config.source_config_version()
    original = config.MAX_NAME_TOKEN_DF
    try:
        config.MAX_NAME_TOKEN_DF = original + 5
        assert config.source_config_version() != before
    finally:
        config.MAX_NAME_TOKEN_DF = original
    assert config.source_config_version() == before
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_radar_config.py -k distinctiveness -v`
Expected: FAIL — `AttributeError: module 'features.radar.config' has no attribute 'MAX_NAME_TOKEN_DF'`

- [ ] **Step 3: Move the tunables into config**

Cut this block from `personal_apps/features/radar/universe.py` (lines ~20–36,
the comment plus the three constants plus `_NAME_WORD_RE`) and paste it into
`config.py` next to `CASHTAG_PATTERN`, keeping the existing comment and adding
the fund pattern:

```python
# Distinctiveness of a company-name token, which decides whether a bare
# mention can be promoted to `high`. These live here rather than in universe.py
# for the same reason the two match patterns do: changing any of them changes
# WHICH mentions get counted, and source_config_version() below has to see it.
# universe imports config, so the dependency cannot run the other way.
MAX_NAME_TOKEN_DF = 3
MAX_NAME_TOKEN_RATIO = 0.25
MIN_NAME_TOKEN_LEN = 4

NAME_WORD_PATTERN = r"[a-z']+"

# Names that are derivatives rather than issuers. A leveraged ETF, a warrant
# or a share class naming its underlying is not independent evidence that the
# name is common -- counting them is why `tesla` scored a document frequency
# of 4 against a ceiling of 3 and Tesla could never be promoted.
FUND_NAME_PATTERN = (
    r'\b(etf|etn|fund|trust|index|portfolio|inverse|bull|bear|\d+x'
    r'|daily target|yield premium|covered call|leveraged|warrant|rights?'
    r'|units?|notes due|preferred|depositary)\b'
)
```

In `universe.py`, delete those definitions. The import is currently

```python
from .config import (LARGE_CAP_FLOOR, MID_CAP_FLOOR, PENNY_PRICE,
                     RECENT_IPO_DAYS)
```

and becomes

```python
from .config import (FUND_NAME_PATTERN, LARGE_CAP_FLOOR, MAX_NAME_TOKEN_DF,
                     MAX_NAME_TOKEN_RATIO, MID_CAP_FLOOR, MIN_NAME_TOKEN_LEN,
                     NAME_WORD_PATTERN, PENNY_PRICE, RECENT_IPO_DAYS)
```

Then, also in `universe.py`:

```python
_NAME_WORD_RE = re.compile(NAME_WORD_PATTERN)
_FUND_NAME_RE = re.compile(FUND_NAME_PATTERN, re.IGNORECASE)
```

- [ ] **Step 4: Add them to the hash**

In `config.source_config_version()`, extend the payload:

```python
        'cashtag_re': CASHTAG_PATTERN,
        'bare_re': BARE_PATTERN,
        'bot_re': _EXCHANGE_BOT_RE.pattern,
        'name_df': [MAX_NAME_TOKEN_DF, MAX_NAME_TOKEN_RATIO,
                    MIN_NAME_TOKEN_LEN],
        'fund_re': FUND_NAME_PATTERN,
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_radar_config.py tests/test_radar_universe.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/features/radar/universe.py personal_apps/tests/test_radar_config.py
git commit -m "refactor(radar): put the distinctiveness rule where the version stamp can see it"
```

---

### Task 2: Count issuers, not listings

**Files:**
- Modify: `personal_apps/features/radar/universe.py` (`annotate_distinctive`)
- Test: `personal_apps/tests/test_radar_universe.py`

**Interfaces:**
- Consumes: `FUND_NAME_PATTERN` etc. from Task 1.
- Produces: `universe._issuer_of(name) -> str`; `annotate_distinctive` unchanged in signature and return.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_universe.py`:

```python
def test_a_company_and_its_own_etfs_count_once():
    """`tesla` had a document frequency of 4 against a ceiling of 3 -- Tesla
    plus three leveraged ETFs tracking it -- so a bare TSLA mention could
    never be promoted. Measured on the live 12,359-symbol universe."""
    lookup = universe.annotate_distinctive({
        'TSLA': {'name': 'Tesla, Inc. - Common Stock'},
        'TSLL': {'name': 'Direxion Daily TSLA Bull 2X Shares'},
        'TSLQ': {'name': 'T-Rex 2X Inverse Tesla Daily Target ETF'},
        'TSLR': {'name': 'T-Rex 2X Long Tesla Daily Target ETF'},
    })

    assert 'tesla' in lookup['TSLA']['distinctive']


def test_share_classes_of_one_issuer_count_once():
    lookup = universe.annotate_distinctive({
        'GOOGL': {'name': 'Alphabet Inc. - Class A Common Stock'},
        'GOOG': {'name': 'Alphabet Inc. - Class C Capital Stock'},
        'GOOGP': {'name': 'Alphabet Inc. - Depositary Shares Series A'},
        'GOOGQ': {'name': 'Alphabet Inc. - Depositary Shares Series B'},
    })

    assert 'alphabet' in lookup['GOOGL']['distinctive']


def test_a_spac_listing_four_ways_counts_once():
    """The small-cap version of the same bug, and the one that matters here:
    a recent IPO lists as Common Stock plus Units plus Warrants plus Rights."""
    lookup = universe.annotate_distinctive({
        'IPEX': {'name': 'Inflection Point Acquisition Corp. - Common Stock'},
        'IPEXU': {'name': 'Inflection Point Acquisition Corp. - Unit'},
        'IPEXW': {'name': 'Inflection Point Acquisition Corp. - Warrant'},
        'IPEXR': {'name': 'Inflection Point Acquisition Corp. - Right'},
    })

    assert 'inflection' in lookup['IPEX']['distinctive']


def test_boilerplate_is_still_not_distinctive():
    """The guard on the whole change. Four DIFFERENT issuers sharing a word
    means the word is common, and no amount of deduping should rescue it."""
    lookup = universe.annotate_distinctive({
        'AAA': {'name': 'Alpha Bancorp Inc. - Common Stock'},
        'BBB': {'name': 'Beta Bancorp Inc. - Common Stock'},
        'CCC': {'name': 'Gamma Bancorp Inc. - Common Stock'},
        'DDD': {'name': 'Delta Bancorp Inc. - Common Stock'},
    })

    for symbol in lookup:
        assert 'bancorp' not in lookup[symbol]['distinctive']
        assert 'common' not in lookup[symbol]['distinctive']
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_universe.py -k "counts_once or boilerplate" -v`
Expected: the first three FAIL, `test_boilerplate_is_still_not_distinctive` PASSES.
That last one passing now is the point — it must still pass after the change.

- [ ] **Step 3: Rewrite annotate_distinctive**

In `personal_apps/features/radar/universe.py`:

```python
def _issuer_of(name):
    """The issuer a listing belongs to.

    Everything before the first comma or ' - ', so every share class, unit,
    warrant and right of one company collapses to a single key. Crude, and it
    only has to be good enough to stop one company counting as four.
    """
    return re.split(r',| - ', name or '', maxsplit=1)[0].strip().lower()


def annotate_distinctive(lookup):
    """Add a `distinctive` token set to every entry, in place.

    A token qualifies when at most MAX_NAME_TOKEN_DF distinct ISSUERS use it,
    it is long enough to be a real word, and it is not the symbol echoing
    itself. Measured against the passed lookup rather than a constant, so it
    calibrates to whatever universe it is given -- including the small ones in
    tests.

    ISSUERS, not listings, and funds excluded from the count. Counting
    listings made a company compete with its own derivatives: `tesla` appeared
    in four names -- Tesla plus three leveraged ETFs -- against a ceiling of
    three, so TSLA could never be promoted from a bare mention. The same shape
    hits small caps harder, because a recent IPO lists as Common Stock plus
    Units plus Warrants plus Rights. Both exclusions are needed: dropping
    funds alone leaves Alphabet's five share classes, and issuer-deduping
    alone leaves Tesla's three ETFs.

    Symbols left with an empty set can never be promoted from a bare mention.
    That remains the intended outcome for tickers like HR or DYOR, whose names
    carry nothing but boilerplate.
    """
    issuers = collections.defaultdict(set)
    tokens_by_symbol = {}
    for symbol, entry in lookup.items():
        name = entry.get('name') or ''
        tokens = set(_NAME_WORD_RE.findall(name.lower()))
        tokens_by_symbol[symbol] = tokens
        if _FUND_NAME_RE.search(name):
            continue
        for token in tokens:
            issuers[token].add(_issuer_of(name))

    ceiling = min(MAX_NAME_TOKEN_DF,
                  max(1, int(MAX_NAME_TOKEN_RATIO * len(lookup))))

    for symbol, tokens in tokens_by_symbol.items():
        lookup[symbol]['distinctive'] = {
            token for token in tokens
            if len(issuers.get(token, ())) <= ceiling
            and len(token) >= MIN_NAME_TOKEN_LEN
            and token != symbol.lower()
        }
    return lookup
```

Note `issuers.get(token, ())` returning empty: a token appearing only in fund
names has no issuers, so it passes the ceiling. That is deliberate — an ETF's
own name should be able to promote its own ticker.

- [ ] **Step 4: Pin the accepted cost**

Append to `personal_apps/tests/test_radar_universe.py`:

```python
def test_an_ordinary_word_can_become_distinctive_and_that_is_accepted():
    """The known cost of counting issuers. `peace` goes from 4 listings to 1
    issuer because three of the four are Peace Acquisition's warrant, unit and
    right -- so an ordinary English word qualifies.

    Recorded rather than fixed. Promotion still needs the BARE TICKER in the
    same post, so this only misfires on a post containing both PEACE and the
    word "peace". If that trade ever stops being worth it, this test is where
    the decision was made.
    """
    lookup = universe.annotate_distinctive({
        'PECE': {'name': 'Peace Acquisition Corp - Common Stock'},
        'PECEU': {'name': 'Peace Acquisition Corp - Unit'},
        'PECEW': {'name': 'Peace Acquisition Corp - Warrant'},
    })

    assert 'peace' in lookup['PECE']['distinctive']
```

- [ ] **Step 5: Run the tests, then check the real universe**

Run: `python -m pytest tests/test_radar_universe.py -v`
Expected: PASS

Then confirm against live data, because the unit tests use four-symbol
lookups and the ratio arm of the ceiling behaves differently at scale:

```bash
PYTHONPATH=. python -c "
from app import app
from features.radar import universe
with app.app_context():
    lookup = universe.load_lookup()
for sym in ('TSLA','NVDA','AAPL','GOOGL','SBFM','HTOO','WMT'):
    e = lookup.get(sym)
    print(sym, sorted(e['distinctive'])[:4] if e else 'absent')
"
```

Expected: `TSLA ['tesla']`, `NVDA ['nvidia']`, `GOOGL ['alphabet']`, and `WMT`
still `['walmart']`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/universe.py personal_apps/tests/test_radar_universe.py
git commit -m "fix(radar): a company should not compete with its own derivatives"
```

---

### Task 3: Bare tokens on for Bluesky, behind a measurement

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Create: `personal_apps/scripts/measure_bare_tokens.py`
- Test: `personal_apps/tests/test_radar_config.py`

**Interfaces:**
- Produces: `BARE_TOKENS_ALLOWED['bluesky'] = True`; a reporting script.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_bluesky_reads_bare_tokens_now():
    """Off since the first live measurement, when Bluesky's top bare tokens
    were IA (Iowa), GOP and AP. That reasoning expired: an uncorroborated bare
    token is now stored `low` and never scored, and only becomes countable via
    a distinctive company name in the same post or a different author
    cashtagging it in the same bucket. Bluesky has the many independent
    authors that second path needs; a broadcast channel does not.
    """
    from features.radar.config import bare_tokens_allowed

    assert bare_tokens_allowed('bluesky') is True
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_radar_config.py -k bare_tokens_now -v`
Expected: FAIL — `assert False is True`

- [ ] **Step 3: Flip the flag**

In `personal_apps/features/radar/config.py`, in `BARE_TOKENS_ALLOWED`:

```python
    # Was False, set after the first live pass found IA (Iowa), GOP and AP
    # among the top bare tokens. Re-enabled 2026-08-23: an uncorroborated bare
    # token is stored `low` and never scored, so the junk that measurement
    # found now costs a row in a table and nothing on the board. What it buys
    # is the promotion path -- a distinctive company name in the same post, or
    # a different author cashtagging the same ticker in the same bucket --
    # which needs many independent authors and is therefore exactly this
    # source. See scripts/measure_bare_tokens.py; revert if the top twenty
    # stop looking like equities.
    'bluesky': True,
```

- [ ] **Step 4: Write the measurement script**

Create `personal_apps/scripts/measure_bare_tokens.py`:

```python
"""What turning bare tokens on for Bluesky actually did.

Run an hour or so after the change is live. The flag is one line; this is the
deliverable. /biz/ looked promising too and produced three scored mentions in
fourteen hours -- the difference between a good idea and a working one is this
report.

    cd personal_apps && PYTHONPATH=. python scripts/measure_bare_tokens.py
"""
import datetime as dt

import sqlalchemy as sa

from app import app
from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost

HOURS = 2


def main():
    with app.app_context():
        # Naive UTC, the convention every datetime here is stored in.
        # datetime.utcnow() is deprecated and was already removed from the
        # daemon once for printing a warning into the service log.
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        since = now - dt.timedelta(hours=HOURS)

        by_conf = dict(db.session.query(
            RadarMention.confidence, sa.func.count())
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.source == 'bluesky',
                    RadarPost.created_utc >= since)
            .group_by(RadarMention.confidence).all())
        total = sum(by_conf.values()) or 1
        print(f'bluesky mentions in {HOURS}h: {by_conf}')
        scored = by_conf.get('high', 0) + by_conf.get('medium', 0)
        print(f'  scored (high+medium): {scored}  '
              f'({scored / total:.0%} of all extracted)')
        print(f'  promotion rate low->medium: '
              f'{by_conf.get("medium", 0) / max(by_conf.get("low", 1), 1):.3f}')

        print('\ntop 20 by SCORED mentions -- these must look like equities:')
        rows = (db.session.query(RadarMention.ticker, sa.func.count())
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarPost.source == 'bluesky',
                        RadarPost.created_utc >= since,
                        RadarMention.confidence.in_(('high', 'medium')))
                .group_by(RadarMention.ticker)
                .order_by(sa.func.count().desc()).limit(20).all())
        for ticker, count in rows:
            print(f'  {ticker:8s} {count}')

        ratio = (db.session.query(sa.func.avg(
            RadarBucketSource.distinct_text_ratio))
            .filter(RadarBucketSource.source == 'bluesky',
                    RadarBucketSource.bucket_start >= since).scalar())
        print(f'\nmean distinct_text_ratio: '
              f'{float(ratio):.2f}' if ratio else '\nno buckets yet')


if __name__ == '__main__':
    main()
```

- [ ] **Step 5: Run the tests and commit**

Run: `python -m pytest tests/ -q -k radar`
Expected: PASS

```bash
git add personal_apps/features/radar/config.py personal_apps/scripts/measure_bare_tokens.py personal_apps/tests/test_radar_config.py
git commit -m "feat(radar): let Bluesky's bare tokens through, and measure what happens"
```

- [ ] **Step 6: The measurement itself is a gate, not a step**

After deploying, wait an hour and run the script. **Report the numbers to
michi before treating this as done.** Revert the flag if `IA`, `GOP`, `AP` or
similar appear among the top twenty scored tickers.

---

### Task 4: Open on the small stuff

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/features/radar/leaderboard.py`, `board.py`, `routes/api.py`
- Modify: `personal_apps/static/radar/src/{types.ts,board/Controls.tsx,board/BoardPage.tsx}`
- Test: `personal_apps/tests/test_radar_board.py`, `tests/test_radar_api.py`, `static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Produces: `config.SEGMENT_GROUPS = {'small': ('micro', 'unknown', 'recent_ipo')}`, `config.segments_in(selection) -> tuple`; `DEFAULT_SEGMENT = 'small'`.
- `build_rows`/`board.build` keep taking one `segment` string; it resolves through the group map.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_board.py`:

```python
def test_small_unions_the_three_segments_below_mid(clean):
    """The tool is for penny stocks and unknowns. `Small` is what that means
    in the segment vocabulary: anything not large and not mid."""
    universe(f'{PREFIX}A', cap='50000000000')      # large
    universe(f'{PREFIX}B', cap='100000000')        # micro
    universe(f'{PREFIX}C', cap=None)               # unknown
    for suffix in 'ABC':
        bucket(f'{PREFIX}{suffix}', minutes_ago=30)
    db.session.commit()

    built = board.build(['bluesky'], NOW, segment='small')
    got = {entry.rank.ticker for entry in built.rows}

    assert got == {f'{PREFIX}B', f'{PREFIX}C'}


def test_a_row_in_small_still_reports_its_own_segment(clean):
    """`Small` is a filter, not a sixth segment. A micro-cap is still micro,
    or the segment counts would stop summing to the total."""
    universe(f'{PREFIX}B', cap='100000000')
    bucket(f'{PREFIX}B', minutes_ago=30)
    db.session.commit()

    built = board.build(['bluesky'], NOW, segment='small')

    assert built.rows[0].rank.segment == 'micro'
```

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_small_is_an_accepted_segment(client):
    assert client.get('/radar/api/board?segment=small').status_code == 200


def test_the_board_opens_on_the_small_stuff(client):
    """It is a discovery radar for penny stocks. Opening on All means reading
    megacaps and micro-caps in one list."""
    payload = json.loads(client.get('/radar/api/board').data)

    assert payload['segment'] == 'small'
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_board.py -k small -v`
Expected: FAIL — `small` is not a known segment, so no rows come back

- [ ] **Step 3: Add the group**

In `personal_apps/features/radar/config.py`, beside the cap floors:

```python
# Segment groups. `Small` is what "penny stocks and unknown stuff" means in
# the segment vocabulary -- anything that is not large or mid.
#
# A GROUP, not a sixth segment: universe.segment_for still returns exactly one
# of the five and every row still reports its own, so the counts keep summing
# to the total. `unknown` is folded in on an assumption worth naming -- it
# means no market cap is known, not that the cap is small -- and it holds
# because a ticker no provider has profiled is overwhelmingly a tiny one.
SEGMENT_GROUPS = {
    'small': ('micro', 'unknown', 'recent_ipo'),
}

# What the board opens on. It is a discovery radar for the things nobody has
# heard of; opening on everything buries them under megacap chatter.
DEFAULT_SEGMENT = 'small'


def segments_in(selection):
    """The concrete segments a selection covers, or () for everything."""
    if selection is None:
        return ()
    return SEGMENT_GROUPS.get(selection, (selection,))
```

- [ ] **Step 4: Resolve it at read time**

In `leaderboard.py`, extend the import:

```python
from .config import PROVISIONAL_BASELINE_DAYS, segments_in, source_kind
```

Resolve the selection once, before the `for ticker, buckets in ...` loop:

```python
    # A selection may name a group ('small') or a single segment. Resolved
    # once rather than per row; empty means everything.
    allowed = segments_in(segment)
```

and replace the per-row comparison

```python
        if segment is not None and row_segment != segment:
            continue
```

with

```python
        if allowed and row_segment not in allowed:
            continue
```

In `routes/api.py`, add `'small'` to `SEGMENTS`, and default the query to
`DEFAULT_SEGMENT`:

```python
    segment = args.get('segment', DEFAULT_SEGMENT) or None
```

Note `or None`: `?segment=` with an empty value is how the surface asks for
All, and it must stay reachable now that the default is not None.

- [ ] **Step 5: Surface it**

In `Controls.tsx`, add `small` to `SEGMENT_ORDER` immediately after `all`, and
give it a label in `format.ts`:

```ts
  small: 'Small',
```

In `board.py`, extend the import:

```python
from .config import SEGMENT_GROUPS, VARIANCE_FLOOR
```

and include `small` in `segment_counts`, computed like the others from the
unfiltered pass — before either filter runs:

```python
    segment_counts['small'] = sum(
        1 for row in ranked if row.segment in SEGMENT_GROUPS['small'])
```

In `BoardPage.tsx` the initial `Selection` already seeds `segment` from
`initial.segment`, so the default arrives from the server with no client
change.

- [ ] **Step 6: Verify in a browser**

Screenshot `/radar/` at 1440 and confirm: the `Small` chip is pressed on load,
its count is plausible against `All`, clicking `All` refetches and shows more
rows, and no horizontal overflow.

- [ ] **Step 7: Run everything and commit**

Run: `npx tsc --noEmit` — no output
Run: `npx vitest run -c vite.radar.config.ts` — PASS
Run: `python -m pytest tests/ -q -k "radar or vite or auth"` — PASS

```bash
git add personal_apps
git commit -m "feat(radar): open on the small stuff, since that is what it is for"
```
