# Radar Plan 2 — Baselines and Mention Z-Scores

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `radar_bucket_sources` counts into per-source mention z-scores that survive sparse data, quiet hours, source outages and cold starts — without needing a price feed.

**Architecture:** Three pure modules reading buckets and writing scores back onto the same rows. A per-source hour-of-week profile says what a normal bucket looks like; a rate estimator says how loud a ticker normally is; a negative-binomial variance says how surprised to be. Nothing here fetches anything, and nothing here knows about prices.

**Tech Stack:** Python 3.12, SQLAlchemy, MySQL 8 (dev) / MariaDB (prod), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-radar-social-sentiment-design.md` §6
**Predecessors:** Plan 1 and Plan 1b complete; ingest live on the VPS, 182 tests green.

## Global Constraints

- **No prices.** Divergence (§6.4), no-print detection (§6.5) and segments (§8.1) are Plan 3. This plan computes `mention_z` only.
- **`missing` and `truncated` never enter a baseline** (spec §4.5). Only `status = 'ok'` buckets are usable. This is the rule the whole plan rests on.
- **Baselines are per `(ticker, source)`.** Sources have different populations, rhythms and histories; nothing may pool them before scoring.
- **Nothing outside `config.py` names a source.** The set is open.
- **No live network calls in tests.** Everything is synthetic buckets.
- All datetimes UTC, `DATETIME(6)`.
- The radar suite must keep passing under `-W error::DeprecationWarning`.
- Working directory for every command: `C:\Users\michi\Desktop\CodingStuff\personal_apps`.

## Deviations from the spec, and why

**§6.1 describes one market-wide hour-share profile. This plan makes it per source.** StockTwits follows US market hours, Bluesky is global and diurnal, /biz/ is 24/7 crypto culture. A shared profile would tell Bluesky to expect silence at 03:00 ET while half its users are awake, and every one of those buckets would score as unusual.

**§6.8's cold-start prior uses a segment median. This plan uses a global per-source median.** Segments need market cap, which needs the Plan 3 price provider. The estimator takes a prior rate as an argument, so Plan 3 swaps in the segment one without touching it.

**§6.1's usable set excludes buckets inside an open spike. Spikes do not exist until Plan 3.** The exclusion is a caller-supplied set now and gets wired to real spikes then, so the estimator needs no revisiting.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `features/radar/profile.py` | Per-source hour-of-week share profile |
| `features/radar/baselines.py` | Rate estimation, NB dispersion, expected/variance |
| `features/radar/scoring.py` | Per-source z, pooling, eligibility, windows |
| `tests/test_radar_profile.py`, `tests/test_radar_baselines.py`, `tests/test_radar_scoring.py` | |

**Modify:** `models.py`, `features/radar/config.py`, `features/radar/buckets.py`, `run_radar_ingest.py`, `tests/test_radar_buckets.py`, `tests/test_radar_daemon.py`

---

## Task 1: `source_config_version` on the per-source row

Baselines exclude history from before a source-configuration change (§6.6), and that decision is made per `(ticker, source)`. The column exists only on the parent `radar_buckets` row today, so the baseline query has nowhere to read it from without joining a table it otherwise never touches.

**Files:**
- Modify: `personal_apps/models.py`, `personal_apps/features/radar/buckets.py`
- Create: migration
- Test: `personal_apps/tests/test_radar_buckets.py`

**Interfaces:**
- Produces: `RadarBucketSource.source_config_version`, written by `roll_up`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_buckets.py`:

```python
def test_the_config_version_is_stamped_on_each_source_row(clean_buckets):
    """Baselines exclude history from before a config change, and that
    exclusion is per (ticker, source). Reading it off the parent bucket would
    mean joining a table the baseline query has no other reason to touch."""
    from features.radar.config import source_config_version
    buckets.roll_up([row(source='stocktwits'), row(source='bluesky')],
                    {'stocktwits': 'ok', 'bluesky': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    versions = {r.source: r.source_config_version for r in
                RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert len(versions) == 2
    assert set(versions.values()) == {source_config_version()}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_buckets.py -v`
Expected: FAIL — `RadarBucketSource` has no attribute `source_config_version`

- [ ] **Step 3: Write minimal implementation**

Add to `RadarBucketSource` in `personal_apps/models.py`, beside `status`:

```python
    # Per source, not inherited from the parent bucket: baselines exclude
    # history from before a configuration change (spec 6.6), and that decision
    # is made per (ticker, source).
    #
    # Nullable because rows already written have no value, and back-filling a
    # version they were not collected under would be a lie. baselines.usable
    # treats a mismatch as unusable, so those rows age out of the window.
    source_config_version     = db.Column(db.String(16), nullable=True)
```

Generate the migration, review it, delete anything it emits against other tables, then apply:

```bash
python -m flask --app app db migrate -m "add source config version to bucket sources"
python -m flask --app app db upgrade
```

Stamp it in `roll_up`, in `personal_apps/features/radar/buckets.py`, beside the existing `child.status = statuses[source]`:

```python
            child.source_config_version = version
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_buckets.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/ personal_apps/features/radar/buckets.py personal_apps/tests/test_radar_buckets.py
git commit -m "feat(radar): stamp the config version where baselines read it"
```

---

## Task 2: Per-source hour-of-week profile

**Files:**
- Create: `personal_apps/features/radar/profile.py`
- Test: `personal_apps/tests/test_radar_profile.py`

**Interfaces:**
- Produces:
  - `bucket_of_week(when: datetime) -> int` — 0..671
  - `build_profile(source: str, until: datetime, weeks: int = 8) -> dict[int, float]`
  - `hour_share(profile: dict, when: datetime) -> float`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_profile.py
"""What a normal bucket looks like, per source.

Chatter has a strong weekly shape, and comparing 03:00 Sunday against 15:00
Tuesday as one population makes every weekday afternoon a spike. The profile is
what removes that shape before anything is called unusual.

Per source, not market-wide: StockTwits follows US market hours, Bluesky is
global and diurnal, /biz/ runs around the clock. One shared profile would tell
Bluesky to expect silence when half its users are awake.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import profile

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)      # a Monday, 00:00 UTC


@pytest.fixture()
def buckets():
    with flask_app.app_context():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
        db.session.commit()


def add(source, when, count, ticker='PPA', status='ok'):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status))


def test_bucket_of_week_is_zero_at_monday_midnight():
    assert profile.bucket_of_week(MONDAY) == 0


def test_bucket_of_week_advances_every_fifteen_minutes():
    assert profile.bucket_of_week(MONDAY + dt.timedelta(minutes=15)) == 1
    assert profile.bucket_of_week(MONDAY + dt.timedelta(hours=1)) == 4


def test_bucket_of_week_wraps_after_a_week():
    assert profile.bucket_of_week(MONDAY + dt.timedelta(days=7)) == 0
    assert profile.bucket_of_week(
        MONDAY + dt.timedelta(days=6, hours=23, minutes=45)) == 671


def test_a_profile_sums_to_one(buckets):
    for hour in (2, 14, 20):
        add('stocktwits', MONDAY + dt.timedelta(hours=hour), count=hour)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    assert sum(built.values()) == pytest.approx(1.0)


def test_busy_buckets_get_a_larger_share(buckets):
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('stocktwits', MONDAY + dt.timedelta(hours=3), count=1)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    busy = profile.hour_share(built, MONDAY + dt.timedelta(hours=14))
    quiet = profile.hour_share(built, MONDAY + dt.timedelta(hours=3))
    assert busy > quiet * 10


def test_every_bucket_has_a_nonzero_share(buckets):
    """Smoothing is load-bearing. A share of zero makes expected zero, and any
    observation against it is an infinite z -- so one quiet hour in the sample
    window would manufacture a spike there forever after."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=50)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    assert len(built) == 672
    assert all(share > 0 for share in built.values())


def test_profiles_are_per_source(buckets):
    """StockTwits peaks in the US session; a 24/7 source does not. Sharing one
    profile would read half of Bluesky's normal traffic as unusual."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('bluesky', MONDAY + dt.timedelta(hours=3), count=100)
    db.session.commit()
    st = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    bs = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1))
    assert profile.hour_share(st, MONDAY + dt.timedelta(hours=14)) > \
        profile.hour_share(bs, MONDAY + dt.timedelta(hours=14))


def test_missing_and_truncated_buckets_are_ignored(buckets):
    """A source that was down did not observe a quiet hour. Counting the gap
    would bend the profile towards silence at exactly the wrong times."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('stocktwits', MONDAY + dt.timedelta(hours=15), count=0, status='missing')
    add('stocktwits', MONDAY + dt.timedelta(hours=16), count=5, status='truncated')
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    fifteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=15))
    sixteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=16))
    # Both fall back to the smoothing floor, and are equal because neither
    # contributed an observation.
    assert fifteen == pytest.approx(sixteen)


def test_an_empty_history_gives_a_flat_profile(buckets):
    """Day one. Flat means "no idea yet", which is the honest prior and cannot
    on its own make anything look unusual."""
    built = profile.build_profile('stocktwits', MONDAY)
    assert len(built) == 672
    assert len(set(round(v, 12) for v in built.values())) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_profile.py -v`
Expected: FAIL with `ImportError: cannot import name 'profile'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/profile.py
"""What a normal bucket looks like, per source.

Mention volume has a strong weekly shape. Comparing 03:00 on a Sunday against
15:00 on a Tuesday as though they were one population makes every weekday
afternoon look like a spike, which is most of what a naive z-score would report.

Built per source rather than market-wide, a deliberate departure from spec 6.1.
StockTwits follows US market hours, Bluesky is global and diurnal, /biz/ runs
around the clock. A shared profile would tell Bluesky to expect silence at
03:00 ET while half its users are awake, and every one of those buckets would
score as unusual.
"""
import collections
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource

from .config import BUCKET_MINUTES

BUCKETS_PER_WEEK = (7 * 24 * 60) // BUCKET_MINUTES      # 672

# Every bucket-of-week starts with this much pseudo-count before observations
# are added. A share of exactly zero makes `expected` zero, and any observation
# against a zero expectation is an infinite z -- so a single quiet hour in the
# sample window would manufacture a spike there forever. Smoothing is what
# stops "never seen" from meaning "impossible".
SMOOTHING = 1.0

DEFAULT_WEEKS = 8


def bucket_of_week(when):
    """0..671, counting 15-minute buckets from Monday 00:00 UTC."""
    minutes = (when.weekday() * 24 * 60) + (when.hour * 60) + when.minute
    return minutes // BUCKET_MINUTES


def build_profile(source, until, weeks=DEFAULT_WEEKS):
    """Share of this source's weekly volume falling in each bucket-of-week.

    Only `ok` buckets contribute. A `missing` bucket is a source that was down,
    not an hour that was quiet, and counting it would bend the profile towards
    silence at precisely the times ingest tends to fail. `truncated` is a known
    undercount and equally unusable as a description of normal.
    """
    since = until - dt.timedelta(weeks=weeks)

    rows = (db.session.query(RadarBucketSource.bucket_start,
                             sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.source == source,
                    RadarBucketSource.status == 'ok',
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < until)
            .group_by(RadarBucketSource.bucket_start).all())

    weights = collections.defaultdict(float)
    for index in range(BUCKETS_PER_WEEK):
        weights[index] = SMOOTHING
    for bucket_start, total in rows:
        weights[bucket_of_week(bucket_start)] += float(total or 0)

    grand_total = sum(weights.values())
    return {index: weight / grand_total for index, weight in weights.items()}


def hour_share(profile, when):
    """This instant's share of a normal week for the profile's source."""
    return profile[bucket_of_week(when)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_profile.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/profile.py personal_apps/tests/test_radar_profile.py
git commit -m "feat(radar): learn each source's weekly rhythm before calling anything unusual"
```

---

## Task 3: Rate estimation with observed mass

**Files:**
- Create: `personal_apps/features/radar/baselines.py`
- Test: `personal_apps/tests/test_radar_baselines.py`

**Interfaces:**
- Produces:
  - `Observation` — dataclass: `bucket_start`, `count`, `status`, `config_version`
  - `usable(observations, config_version, excluded) -> list[Observation]`
  - `weekly_rate(observations, prof, prior_rate=None, prior_weight=0.0) -> tuple[float, float]`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_baselines.py
"""How loud a ticker normally is on one source.

The estimator divides by the observed MASS of the buckets it used, not by their
count. That is what makes dropping buckets safe: a dropped bucket removes its
share from the denominator too, so the rate stays unbiased no matter which ones
went missing. Every gap rule in the design rests on this one division.
"""
import datetime as dt

import pytest

from features.radar import baselines

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)


def flat_profile():
    """Every bucket-of-week equally likely -- 1/672 each."""
    return {index: 1.0 / 672 for index in range(672)}


def obs(hours, count, status='ok', config_version='v1'):
    return baselines.Observation(
        bucket_start=MONDAY + dt.timedelta(hours=hours),
        count=count, status=status, config_version=config_version)


def test_a_flat_week_recovers_its_own_rate():
    """672 buckets of 1 mention each is 672 mentions a week."""
    observations = [obs(i * 0.25, 1) for i in range(672)]
    rate, mass = baselines.weekly_rate(observations, flat_profile())
    assert rate == pytest.approx(672.0)
    assert mass == pytest.approx(1.0)


def test_dropping_buckets_leaves_the_rate_unbiased():
    """The property the whole gap design rests on. Half the week is missing and
    the estimate is unchanged, because the denominator shrank with it."""
    full = [obs(i * 0.25, 1) for i in range(672)]
    half = full[::2]
    full_rate, _ = baselines.weekly_rate(full, flat_profile())
    half_rate, half_mass = baselines.weekly_rate(half, flat_profile())
    assert half_rate == pytest.approx(full_rate)
    assert half_mass == pytest.approx(0.5)


def test_dropping_a_busy_stretch_is_also_unbiased():
    """Bucket counts alone would be fooled here: the dropped buckets are the
    loud ones, so a count-based divisor would report the ticker as gone quiet."""
    prof = {index: (2.0 / 672 if index < 336 else 1.0 / 1008)
            for index in range(672)}
    total = sum(prof.values())
    prof = {k: v / total for k, v in prof.items()}

    everything = [obs(i * 0.25, 10 if i < 336 else 1) for i in range(672)]
    quiet_only = [o for i, o in enumerate(everything) if i >= 336]

    all_rate, _ = baselines.weekly_rate(everything, prof)
    quiet_rate, _ = baselines.weekly_rate(quiet_only, prof)
    assert quiet_rate == pytest.approx(all_rate, rel=0.15)


def test_missing_and_truncated_are_not_usable():
    observations = [obs(0, 5), obs(1, 0, status='missing'),
                    obs(2, 3, status='truncated')]
    assert [o.count for o in baselines.usable(observations, 'v1', set())] == [5]


def test_a_stale_config_version_is_not_usable():
    """Adding a source changes the population being measured, so history from
    before it describes something else (spec 6.6)."""
    observations = [obs(0, 5), obs(1, 9, config_version='v0')]
    assert [o.count for o in baselines.usable(observations, 'v1', set())] == [5]


def test_excluded_buckets_are_dropped():
    """The hook Plan 3 wires to open spikes: a ticker that squeezed last week
    must not carry an inflated mean into this week's baseline."""
    observations = [obs(0, 5), obs(1, 500)]
    excluded = {MONDAY + dt.timedelta(hours=1)}
    assert [o.count for o in baselines.usable(observations, 'v1', excluded)] == [5]


def test_no_usable_history_gives_a_zero_rate_and_zero_mass():
    rate, mass = baselines.weekly_rate([], flat_profile())
    assert rate == 0.0
    assert mass == 0.0


def test_a_prior_pulls_a_thin_estimate_towards_it():
    """Cold start. Two buckets of history should not be trusted on their own."""
    thin = [obs(0, 100), obs(1, 100)]
    alone, _ = baselines.weekly_rate(thin, flat_profile())
    shrunk, _ = baselines.weekly_rate(thin, flat_profile(),
                                      prior_rate=10.0, prior_weight=0.05)
    assert shrunk < alone
    assert shrunk > 10.0


def test_a_prior_barely_moves_a_thick_estimate():
    """Once there is real history, the prior should stop mattering."""
    thick = [obs(i * 0.25, 1) for i in range(672)]
    alone, _ = baselines.weekly_rate(thick, flat_profile())
    shrunk, _ = baselines.weekly_rate(thick, flat_profile(),
                                      prior_rate=10.0, prior_weight=0.05)
    assert shrunk == pytest.approx(alone, rel=0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_baselines.py -v`
Expected: FAIL with `ImportError: cannot import name 'baselines'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/baselines.py
"""How loud a ticker normally is, per source.

The estimator divides observed counts by the observed MASS of the buckets it
used -- their combined share of a normal week -- rather than by how many
buckets there were. That single choice is what makes every gap rule in the
design safe rather than merely survivable: dropping a bucket removes its share
from the denominator as well as its count from the numerator, so the rate is
unchanged no matter which buckets went or how busy they usually are.

Dividing by bucket count would be fooled by exactly the case that matters. Lose
the US session to an outage and a count-based divisor reports the ticker as
having gone quiet.
"""
import dataclasses
import datetime as dt

from .profile import hour_share


@dataclasses.dataclass
class Observation:
    """One bucket of one ticker on one source."""
    bucket_start: dt.datetime
    count: int
    status: str
    config_version: str


def usable(observations, config_version, excluded):
    """The buckets a baseline may be built from.

    Three exclusions, all for one reason -- each describes something other than
    this ticker being normally quiet or normally loud:

    - `missing` is a source that was down, `truncated` a known undercount
      (spec 4.5)
    - a different `source_config_version` measured a different population
      (spec 6.6)
    - `excluded` is the caller's own set, wired to open spikes in Plan 3, so a
      ticker that squeezed last week does not carry the squeeze into its own
      baseline
    """
    return [o for o in observations
            if o.status == 'ok'
            and o.config_version == config_version
            and o.bucket_start not in excluded]


def weekly_rate(observations, prof, prior_rate=None, prior_weight=0.0):
    """Mentions per week, and the mass of week actually observed.

    `prior_weight` is in the same units as mass -- 0.05 is worth about eight
    hours of observation, so it dominates on day one and disappears once there
    is real history (spec 6.8).
    """
    if not observations:
        return 0.0, 0.0

    observed_mass = sum(hour_share(prof, o.bucket_start) for o in observations)
    total = sum(o.count for o in observations)

    if observed_mass <= 0:
        return 0.0, 0.0

    if prior_rate is None or prior_weight <= 0:
        return total / observed_mass, observed_mass

    # Shrink towards the prior in mass units, so the weight of the evidence
    # decides, not the number of rows it arrived in.
    blended = (total + prior_rate * prior_weight) / (observed_mass + prior_weight)
    return blended, observed_mass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_baselines.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/baselines.py personal_apps/tests/test_radar_baselines.py
git commit -m "feat(radar): divide by observed mass so a gap cannot bend the baseline"
```

---

## Task 4: Negative-binomial dispersion

**Files:**
- Modify: `personal_apps/features/radar/baselines.py`, `personal_apps/features/radar/config.py`
- Modify: `personal_apps/tests/test_radar_baselines.py`

**Interfaces:**
- Produces: `dispersion(observations, prof, rate) -> float`; `expected_for(rate, prof, when) -> float`; `variance_for(expected, k) -> float`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_baselines.py`:

```python
def test_variance_grows_with_the_level():
    """A Poisson assumption says variance equals the mean. Real chatter is
    burstier, and treating it as Poisson makes every busy hour significant."""
    small = baselines.variance_for(1.0, k=5.0)
    large = baselines.variance_for(100.0, k=5.0)
    assert large > small * 100


def test_a_large_k_approaches_poisson():
    assert baselines.variance_for(10.0, k=1e6) == pytest.approx(10.0, rel=1e-3)


def test_an_overnight_spike_is_not_suppressed():
    """The failure the count model exists to fix. Expected 0.3, observed 6:
    under a pooled standard deviation dominated by busy hours this reads
    z ~ 1.4 and vanishes. Under the count model it is unmistakable."""
    variance = baselines.variance_for(0.3, k=5.0)
    assert (6 - 0.3) / (variance ** 0.5) > 6


def test_dispersion_is_clamped_at_the_top():
    """The operative guard. Dispersion is estimated on spike-excluded buckets,
    which makes the sample look calmer than reality and biases k upward --
    smaller variance, larger z, more spikes, more exclusions, round again."""
    quiet = [obs(i * 0.25, 1) for i in range(200)]
    assert baselines.dispersion(quiet, flat_profile(), rate=672.0) <= baselines.K_MAX


def test_dispersion_is_clamped_at_the_bottom():
    bursty = [obs(i * 0.25, 0 if i % 2 else 500) for i in range(200)]
    assert baselines.dispersion(bursty, flat_profile(), rate=672.0) >= baselines.K_MIN


def test_thin_history_falls_back_to_the_global_default():
    assert baselines.dispersion([], flat_profile(), rate=1.0) == baselines.K_DEFAULT
    assert baselines.dispersion([obs(0, 3)], flat_profile(),
                                rate=1.0) == baselines.K_DEFAULT


def test_expected_scales_with_the_share_of_the_week():
    prof = flat_profile()
    assert baselines.expected_for(672.0, prof, MONDAY) == pytest.approx(1.0)
    assert baselines.expected_for(1344.0, prof, MONDAY) == pytest.approx(2.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_baselines.py -v`
Expected: FAIL — `baselines` has no attribute `variance_for`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Negative-binomial dispersion bounds. variance = mu + mu**2 / k, so a large k
# approaches Poisson and a small k allows heavy bursting.
#
# The UPPER bound is the one doing work. Dispersion is estimated over buckets
# that exclude known spikes, which makes the sample look calmer than the world
# is and biases k upward -- and a k that is too high shrinks the variance,
# inflates every z, produces more spikes, excludes more buckets, and biases k
# further. The clamp keeps that from running away.
K_MIN = 0.5
K_MAX = 50.0
K_DEFAULT = 5.0

# Below this many usable buckets, per-ticker dispersion is noise.
K_MIN_OBSERVATIONS = 20

# Floor under the variance, so a near-zero expectation cannot divide to
# infinity.
VARIANCE_FLOOR = 0.25
```

Add to `personal_apps/features/radar/baselines.py`:

```python
from .config import (K_DEFAULT, K_MAX, K_MIN, K_MIN_OBSERVATIONS,
                     VARIANCE_FLOOR)


def expected_for(rate, prof, when):
    """Mentions expected in the bucket containing `when`."""
    return rate * hour_share(prof, when)


def variance_for(expected, k):
    """Negative-binomial variance: mu + mu**2 / k.

    Poisson (variance = mean) is wrong for chatter in the direction that
    matters: real volume is bursty, so a Poisson model calls every busy hour
    significant. This lets variance grow faster than the mean.
    """
    return expected + (expected ** 2) / k


def dispersion(observations, prof, rate):
    """Estimate k by method of moments, clamped.

    Falls back to the global default when history is too thin for the estimate
    to mean anything -- a handful of buckets produces a number, just not one
    worth trusting.
    """
    if len(observations) < K_MIN_OBSERVATIONS:
        return K_DEFAULT

    total_expected = 0.0
    total_sq_residual = 0.0
    for observation in observations:
        expected = expected_for(rate, prof, observation.bucket_start)
        total_expected += expected
        total_sq_residual += (observation.count - expected) ** 2

    n = len(observations)
    mean_expected = total_expected / n
    sample_variance = total_sq_residual / n

    # Underdispersed relative to Poisson: nothing to estimate, treat as Poisson.
    if sample_variance <= mean_expected or mean_expected <= 0:
        return K_MAX

    k = (mean_expected ** 2) / (sample_variance - mean_expected)
    return max(K_MIN, min(K_MAX, k))
```

The variance floor is applied where the division happens (Task 5), not inside `variance_for` — keeping that function pure is what makes it testable.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_baselines.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/baselines.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_baselines.py
git commit -m "feat(radar): model bursty chatter so overnight spikes stop vanishing"
```

---

## Task 5: Per-source z-scores, written back

**Files:**
- Create: `personal_apps/features/radar/scoring.py`
- Test: `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Produces: `score_source(source, now, lookback_days=30, excluded=None) -> int`, writing `expected`, `variance`, `mention_z`, `baseline_days`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_scoring.py
"""Turning counts into surprise.

Everything here reads radar_bucket_sources and writes back onto the same rows.
No prices and no divergence -- those need a market feed and are Plan 3.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import scoring
from features.radar.config import source_config_version

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
NOW = MONDAY + dt.timedelta(days=35)


@pytest.fixture()
def rows():
    with flask_app.app_context():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
        db.session.commit()


def add(when, count, ticker='SSA', source='stocktwits', status='ok',
        version=None):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status,
        source_config_version=version or source_config_version()))


def steady_history(ticker='SSA', per_bucket=2, days=30, source='stocktwits'):
    """A boringly consistent ticker, so anything unusual is the test's doing.

    2880 rows at 15-minute grain. Added to the session and committed once by
    the caller -- committing per row makes this suite take minutes.
    """
    for step in range(days * 96):
        add(MONDAY + dt.timedelta(minutes=15 * step), per_bucket,
            ticker=ticker, source=source)


def test_a_normal_bucket_scores_near_zero(rows):
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.mention_z is not None
    assert abs(row.mention_z) < 2


def test_a_spike_scores_high(rows):
    steady_history()
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 60})
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud).one().mention_z > 5


def test_expected_and_variance_are_stored_too(rows):
    """Pooling a user-selected subset means summing components, so the parts
    have to survive, not just the z (spec 6.2)."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.expected > 0
    assert row.variance >= row.expected


def test_missing_buckets_are_never_scored(rows):
    """A source that was down has nothing to be surprised about."""
    steady_history()
    gap = MONDAY + dt.timedelta(days=12)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=gap).update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=gap).one().mention_z is None


def test_a_gap_does_not_depress_the_baseline(rows):
    """The observed-mass property, end to end. A week of outage must not make
    the ticker look like it went quiet, or everything after would spike."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    reference = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z

    outage_start = MONDAY + dt.timedelta(days=5)
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker == 'SSA',
        RadarBucketSource.bucket_start >= outage_start,
        RadarBucketSource.bucket_start < outage_start + dt.timedelta(days=7)
    ).update({'status': 'missing', 'mention_count': 0}, synchronize_session=False)
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    after = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
    assert after == pytest.approx(reference, abs=0.5)


def test_baseline_days_is_recorded(rows):
    steady_history(days=30)
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.baseline_days >= 14


def test_a_brand_new_ticker_is_provisional(rows):
    """Two days of history cannot support a z-score anyone should act on."""
    for step in range(2 * 96):
        add(NOW - dt.timedelta(days=2) + dt.timedelta(minutes=15 * step), 3,
            ticker='SSNEW')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = (RadarBucketSource.query.filter_by(ticker='SSNEW')
           .order_by(RadarBucketSource.bucket_start.desc()).first())
    assert row.baseline_days < 14


def test_scoring_only_touches_its_own_source(rows):
    steady_history(source='stocktwits')
    steady_history(ticker='SSB', source='bluesky')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='SSB', source='bluesky').first().mention_z is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: FAIL with `ImportError: cannot import name 'scoring'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/scoring.py
"""Counts into surprise.

Reads radar_bucket_sources and writes expected, variance, mention_z and
baseline_days back onto the same rows. No prices here -- divergence and
no-print detection need a market feed and belong to Plan 3.

Per (ticker, source), never pooled before scoring: the sources have different
populations, rhythms and histories, and a ticker can be loud on one while
silent on another. Pooling happens at read time, over whichever sources the
viewer selected (spec 8.6).
"""
import collections
import datetime as dt

from extensions import db
from models import RadarBucketSource

from . import baselines, profile
from .config import VARIANCE_FLOOR, source_config_version

# Weight of the cold-start prior, in units of observed mass. 0.05 of a week is
# about eight hours: enough to dominate on day one and vanish by week two.
PRIOR_WEIGHT = 0.05


def _rows_by_ticker(source, since, until):
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.source == source,
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < until)
            .all())

    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row.ticker].append(row)
    return grouped


def _observations(rows):
    return [baselines.Observation(r.bucket_start, r.mention_count, r.status,
                                  r.source_config_version)
            for r in rows]


def score_source(source, now, lookback_days=30, excluded=None):
    """Score every bucket of every ticker on one source. Returns rows written.

    `excluded` is the set of bucket starts to keep out of baselines, wired to
    open spikes in Plan 3 so a ticker that squeezed last week does not carry
    the squeeze into its own expectation.
    """
    excluded = excluded or set()
    since = now - dt.timedelta(days=lookback_days)
    version = source_config_version()

    prof = profile.build_profile(source, now)
    grouped = _rows_by_ticker(source, since, now)

    # The prior a thin ticker is pulled towards: what a typical ticker on this
    # source does. Spec 6.8 wants a segment median, which needs market cap and
    # therefore Plan 3; a global median is the same shape with a coarser peer
    # group.
    rates = []
    for rows in grouped.values():
        good = baselines.usable(_observations(rows), version, excluded)
        if good:
            rate, _ = baselines.weekly_rate(good, prof)
            rates.append(rate)
    prior_rate = sorted(rates)[len(rates) // 2] if rates else 0.0

    written = 0
    for rows in grouped.values():
        good = baselines.usable(_observations(rows), version, excluded)
        if not good:
            continue

        rate, _ = baselines.weekly_rate(good, prof, prior_rate=prior_rate,
                                        prior_weight=PRIOR_WEIGHT)
        k = baselines.dispersion(good, prof, rate)
        span = max(o.bucket_start for o in good) - min(o.bucket_start for o in good)
        baseline_days = span.days

        for row in rows:
            # A source that was down, or a known undercount, has nothing to be
            # surprised about. Scoring it would invent a reading from a gap.
            if row.status != 'ok':
                continue

            expected = baselines.expected_for(rate, prof, row.bucket_start)
            variance = baselines.variance_for(expected, k)
            row.expected = expected
            row.variance = variance
            row.mention_z = ((row.mention_count - expected)
                             / max(variance, VARIANCE_FLOOR) ** 0.5)
            row.baseline_days = baseline_days
            written += 1

    db.session.commit()
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scoring.py personal_apps/tests/test_radar_scoring.py
git commit -m "feat(radar): score each source against its own history"
```

---

## Task 6: Pooling a selected subset

**Files:**
- Modify: `personal_apps/features/radar/scoring.py`, `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Produces: `pooled_z(ticker, bucket_start, sources) -> tuple[float | None, int]`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_scoring.py`:

```python
def test_pooling_sums_components_not_z_scores(rows):
    """A weighted mean of z-scores is not a z-score. Two sources each two
    sigma over is stronger evidence than either alone, and averaging would
    report the same two."""
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 12})
    db.session.commit()

    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    single, n_single = scoring.pooled_z('SSA', loud, ['stocktwits'])
    both, n_both = scoring.pooled_z('SSA', loud, ['stocktwits', 'bluesky'])
    assert n_single == 1 and n_both == 2
    assert both > single


def test_pooling_ignores_unselected_sources(rows):
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    _, n = scoring.pooled_z('SSA', when, ['bluesky'])
    assert n == 1


def test_a_missing_source_drops_out_rather_than_contributing_zero(rows):
    """The rule, at read time. A source that was down must not drag the pooled
    reading towards nothing."""
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=when, source='bluesky').update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()
    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    pooled, n = scoring.pooled_z('SSA', when, ['stocktwits', 'bluesky'])
    only, _ = scoring.pooled_z('SSA', when, ['stocktwits'])
    assert n == 1
    assert pooled == pytest.approx(only)


def test_pooling_nothing_returns_none(rows):
    assert scoring.pooled_z('SSNOPE', MONDAY, ['stocktwits']) == (None, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: FAIL — `scoring` has no attribute `pooled_z`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/scoring.py`:

```python
def pooled_z(ticker, bucket_start, sources):
    """Combined z over the selected sources. Returns (z, contributing count).

    Sums the components rather than averaging the z-scores, because a weighted
    mean of z-scores is not a z-score (spec 6.2). Two sources each two sigma
    over is stronger evidence than either alone; averaging reports the same two
    sigma and throws the corroboration away.

    A source with no scored row for this bucket -- down, or truncated -- drops
    out of all three sums rather than contributing zero.
    """
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.bucket_start == bucket_start,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.mention_z.isnot(None))
            .all())
    if not rows:
        return None, 0

    observed = sum(r.mention_count for r in rows)
    expected = sum(r.expected for r in rows)
    variance = sum(r.variance for r in rows)

    return (observed - expected) / max(variance, VARIANCE_FLOOR) ** 0.5, len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scoring.py personal_apps/tests/test_radar_scoring.py
git commit -m "feat(radar): pool selected sources by summing components, not z-scores"
```

---

## Task 7: Eligibility and windows

**Files:**
- Modify: `personal_apps/features/radar/scoring.py`, `personal_apps/features/radar/config.py`, `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Produces: `is_eligible(mentions, authors, text_ratio) -> bool`; `window_z(ticker, sources, end, hours) -> tuple[float | None, dict]`; `is_sustained(ticker, sources, end) -> bool`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_scoring.py`:

```python
def test_eligibility_needs_volume_authors_and_variety():
    assert scoring.is_eligible(mentions=10, authors=6, text_ratio=0.9) is True
    assert scoring.is_eligible(mentions=2, authors=2, text_ratio=1.0) is False
    assert scoring.is_eligible(mentions=10, authors=1, text_ratio=1.0) is False
    assert scoring.is_eligible(mentions=40, authors=40, text_ratio=0.05) is False


def test_the_author_gate_stops_one_person_shouting():
    assert scoring.is_eligible(mentions=50, authors=1, text_ratio=1.0) is False


def test_the_text_gate_stops_fifty_people_pasting_one_thing():
    """Distinct authors cannot see a brigade; distinct text can."""
    assert scoring.is_eligible(mentions=50, authors=50, text_ratio=0.02) is False


def test_a_window_aggregates_its_buckets(rows):
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    end = MONDAY + dt.timedelta(days=20)

    _, parts_1h = scoring.window_z('SSA', ['stocktwits'], end, hours=1)
    _, parts_4h = scoring.window_z('SSA', ['stocktwits'], end, hours=4)
    assert parts_4h['mentions'] > parts_1h['mentions']
    assert parts_4h['expected'] > parts_1h['expected']


def test_a_window_with_no_scored_buckets_is_none(rows):
    assert scoring.window_z('SSNOPE', ['stocktwits'], NOW, hours=1) == (None, {})


def test_sustained_needs_several_non_overlapping_hours(rows):
    """1h, 4h and 24h are nested, so one loud hour lifts all three and
    "elevated in all three" would just restate it. Sustained is measured over
    consecutive separate hours instead (spec 6.9)."""
    steady_history()
    end = MONDAY + dt.timedelta(days=20)
    db.session.commit()

    for step in range(4):                      # one loud hour only
        RadarBucketSource.query.filter_by(
            ticker='SSA',
            bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
            {'mention_count': 40})
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    assert scoring.is_sustained('SSA', ['stocktwits'], end) is False

    for step in range(12):                     # three of the last four hours
        RadarBucketSource.query.filter_by(
            ticker='SSA',
            bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
            {'mention_count': 40})
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    assert scoring.is_sustained('SSA', ['stocktwits'], end) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: FAIL — `scoring` has no attribute `is_eligible`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Eligibility floor (spec 6.3). Three gates, each closing a hole the others
# cannot see: volume alone is meaningless at low counts, one account can supply
# any volume, and fifty accounts can paste one message.
MIN_MENTIONS = 5
MIN_DISTINCT_AUTHORS = 3
MIN_DISTINCT_TEXT_RATIO = 0.35

# A window counts as elevated at or above this z.
ELEVATED_Z = 2.0

# Sustained: this many of the last four non-overlapping hours elevated.
SUSTAINED_HOURS_REQUIRED = 3
SUSTAINED_HOURS_CONSIDERED = 4
```

Add to `personal_apps/features/radar/scoring.py`:

```python
from .config import (ELEVATED_Z, MIN_DISTINCT_AUTHORS, MIN_DISTINCT_TEXT_RATIO,
                     MIN_MENTIONS, SUSTAINED_HOURS_CONSIDERED,
                     SUSTAINED_HOURS_REQUIRED)


def is_eligible(mentions, authors, text_ratio):
    """Whether a reading is worth ranking at all.

    Three gates, because each is blind to what the others catch: raw volume
    means nothing at low counts, one determined account can supply any volume,
    and fifty accounts pasting one message defeat the author gate completely.
    """
    return (mentions >= MIN_MENTIONS
            and authors >= MIN_DISTINCT_AUTHORS
            and text_ratio >= MIN_DISTINCT_TEXT_RATIO)


def window_z(ticker, sources, end, hours):
    """Pooled z over a time window. Returns (z, component parts).

    Components are summed across both time and sources for the same reason
    pooled_z sums them: the sum of independent counts has the sum of their
    expectations and variances, and no other combination is a z-score.
    """
    start = end - dt.timedelta(hours=hours)
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < end,
                    RadarBucketSource.mention_z.isnot(None))
            .all())
    if not rows:
        return None, {}

    parts = {
        'mentions': sum(r.mention_count for r in rows),
        'expected': sum(r.expected for r in rows),
        'variance': sum(r.variance for r in rows),
        'authors': max((r.distinct_authors for r in rows), default=0),
        'text_ratio': min((r.distinct_text_ratio for r in rows), default=1.0),
        'buckets': len(rows),
    }
    z = ((parts['mentions'] - parts['expected'])
         / max(parts['variance'], VARIANCE_FLOOR) ** 0.5)
    return z, parts


def is_sustained(ticker, sources, end):
    """Elevated across most of the last four separate hours.

    Not "elevated in the 1h, 4h and 24h windows" -- those are nested, so one
    loud hour lifts all three and their agreement means nothing. Consecutive
    non-overlapping hours are independent evidence (spec 6.9).
    """
    elevated = 0
    for step in range(SUSTAINED_HOURS_CONSIDERED):
        z, _ = window_z(ticker, sources, end - dt.timedelta(hours=step), hours=1)
        if z is not None and z >= ELEVATED_Z:
            elevated += 1
    return elevated >= SUSTAINED_HOURS_REQUIRED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scoring.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_scoring.py
git commit -m "feat(radar): gate on volume, authors and variety, and sustain over separate hours"
```

---

## Task 8: Schedule the scoring pass

**Files:**
- Modify: `personal_apps/run_radar_ingest.py`, `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Produces: `score_all(now_utc) -> dict[str, int]`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_daemon.py`:

```python
def test_scoring_covers_every_configured_source(monkeypatch):
    seen = []
    monkeypatch.setattr(daemon.scoring, 'score_source',
                        lambda source, now, **k: seen.append(source) or 1)
    daemon.score_all(_utc(2026, 8, 21, 14))
    assert set(seen) == set(daemon.SOURCES)


def test_one_source_failing_to_score_does_not_stop_the_others(monkeypatch):
    """Same rule as ingest. A bad baseline on one source is not a reason to
    leave the others unscored."""
    def flaky(source, now, **k):
        if source == 'bluesky':
            raise RuntimeError('bad baseline')
        return 3

    monkeypatch.setattr(daemon.scoring, 'score_source', flaky)
    result = daemon.score_all(_utc(2026, 8, 21, 14))
    assert result['bluesky'] == 0
    assert result['stocktwits'] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: FAIL — `run_radar_ingest` has no attribute `score_all`

- [ ] **Step 3: Write minimal implementation**

In `personal_apps/run_radar_ingest.py`, add `scoring` to the `features.radar` import and add:

```python
def score_all(now_utc):
    """Rescore every source. Returns rows written per source.

    Separate from ingest and slower -- it walks 30 days of buckets per ticker,
    so it runs on its own schedule rather than inside a three-minute cycle.

    Failures are isolated per source for the same reason ingest isolates them:
    one source's baseline going wrong is not a reason to leave the rest
    unscored.
    """
    written = {}
    for source in SOURCES:
        try:
            written[source] = scoring.score_source(
                source, now_utc.replace(tzinfo=None))
        except Exception:
            logger.exception('radar scoring failed for %s', source)
            written[source] = 0
    return written


def _scheduled_scoring():
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        written = score_all(now)
    logger.info('radar scoring wrote %s', written)
```

Register it in `main()`, after the cycle job:

```python
    scheduler.add_job(_scheduled_scoring, 'interval', minutes=15,
                      id='radar_scoring', max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=2))
```

Two minutes of delay so the first ingest cycle has landed before the first scoring pass reads its buckets.

- [ ] **Step 4: Run the full radar suite**

Run: `python -m pytest tests/test_radar_*.py -q -W error::DeprecationWarning`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): rescore every source on its own schedule"
```

---

## Done when

- `python -m pytest tests/test_radar_*.py -q -W error::DeprecationWarning` passes
- `radar_bucket_sources` rows carry `expected`, `variance`, `mention_z`, `baseline_days`
- A bucket whose status is `missing` has `mention_z IS NULL`
- A seven-day outage in the middle of a ticker's history leaves later z-scores unchanged

## Calibration is deliberately not in this plan

Thresholds — `ELEVATED_Z`, the eligibility floor, `K_MAX`, `PRIOR_WEIGHT` — ship at their initial values and get tuned against real data later, each tuning round frozen as a new `threshold_version` (spec §7.4). Tuning them now, against a database holding hours of history, would be fitting to noise.

## What Plan 3 picks up

A price provider, and with it divergence (§6.4), no-print detection (§6.5), market-cap segments (§8.1) and the spike history log (§7). `score_source` already takes an `excluded` set for open-spike buckets, so wiring real spikes into baselines needs no change here.
