# Radar Breadth and Per-Kind Eligibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a broadcast venue put a row on the board, and make "how many venues are talking" a dimension you can see and filter on.

**Architecture:** Eligibility becomes a union across source kinds — distinct authors on a forum, distinct channels on a broadcast network — so a ticker qualifies on whichever kind can vouch for it. Breadth is already in the payload as `row.sources`; the surface starts using it, as fixed lit/dim slots plus a `2+` filter applied at read time.

**Tech Stack:** Flask + SQLAlchemy, React 19 + TypeScript + Vite island, pytest + vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-radar-breadth-and-broadcast-design.md`. Read it before Task 1.
- **Parts 1 and 2 only.** No Telegram module — it needs credentials that do not exist yet and gets its own plan.
- **Breadth never enters divergence.** If a task appears to make it a scoring input, stop and re-read the spec.
- **The scan-row grid stays at six tracks.** Breadth goes inside the existing `Mentions / people` cell. A seventh track means removing something else.
- **An absence is never a zero**, and the two kinds of absence are drawn differently — see the existing `SpanChart` and `Sparkline` handling.
- TypeScript runs `strict` + `noUncheckedIndexedAccess`; `npm run build` typechecks `static/gym/src` **and** `static/radar/src`.
- Run pytest from `personal_apps/`; radar vitest with `-c vite.radar.config.ts`.
- Four pytest failures in `test_gym_ownership`, `test_gym_exercise_ownership` and `test_gym_routes_smoke` are pre-existing dev-database state. Ignore them.
- **Files are CRLF.** Prefer the Edit tool over scripted string replacement; LF-keyed `str.replace` silently no-ops here and has already cost several rounds.

---

### Task 1: Source kinds, and what counts as a voice

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Test: `personal_apps/tests/test_radar_config.py`

**Interfaces:**
- Produces: `config.SOURCE_KIND: dict[str, str]`, `config.source_kind(source) -> str`, `config.MIN_DISTINCT_CHANNELS = 2`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_every_configured_source_has_a_kind():
    """A source with no kind still works -- it gets the forum gate -- but the
    map going stale silently is how a broadcast venue would end up judged by
    an author count it can never reach."""
    from features.radar import config

    for source in config.SOURCES:
        assert source in config.SOURCE_KIND, source


def test_an_unknown_source_gets_the_stricter_gate():
    """Forum is the tighter of the two. A source nobody has characterised
    should be judged strictly, not leniently."""
    from features.radar.config import source_kind

    assert source_kind('something-new') == 'forum'
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_config.py -k kind -v`
Expected: FAIL — `ImportError` / `AttributeError: SOURCE_KIND`

- [ ] **Step 3: Add the map**

In `personal_apps/features/radar/config.py`, after `COIN_SYMBOLS_MEAN_STOCKS`:

```python
# What kind of venue each source is, which decides how its independent voices
# are counted.
#
# The author gate is a proxy for one question -- how many independent voices
# are saying this. On a forum that is distinct authors. On a BROADCAST network
# one admin posts and thousands read, so every bucket has exactly one author
# and the author gate can never be cleared no matter how loud the ticker is.
# There the independent unit is the CHANNEL: three channels carrying the same
# symbol is corroboration, one channel posting it forty times is not.
SOURCE_KIND = {
    'stocktwits': 'forum',
    'bluesky': 'forum',
    'fourchan': 'forum',
}


def source_kind(source):
    """'forum' or 'broadcast'. Unknown sources are treated as forums.

    The strict direction: forum is the tighter gate, so a source nobody has
    characterised is judged by the harder standard rather than waved through.
    """
    return SOURCE_KIND.get(source, 'forum')
```

And beside `MIN_DISTINCT_AUTHORS`:

```python
# Distinct CHANNELS a broadcast source needs, against MIN_DISTINCT_AUTHORS for
# a forum. Two rather than three because there are orders of magnitude fewer
# channels than authors, and a symbol reaching two independent channels is
# already the rarer event.
MIN_DISTINCT_CHANNELS = 2
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_radar_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/tests/test_radar_config.py
git commit -m "feat(radar): say what kind of venue each source is"
```

---

### Task 2: Eligibility as a union across kinds

**Files:**
- Modify: `personal_apps/features/radar/scoring.py:133-143`
- Test: `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Consumes: `config.source_kind`, `config.MIN_DISTINCT_CHANNELS` (Task 1).
- Produces:
  - `scoring.Contribution(mentions: int, voices: int, text_ratio: float)` — a dataclass
  - `scoring.is_eligible(contributions: dict[str, Contribution]) -> bool`
  - **The old three-scalar signature is gone.** Its only caller is `leaderboard`, updated in Task 3.

- [ ] **Step 1: Write the failing tests**

Replace the existing eligibility tests in `personal_apps/tests/test_radar_scoring.py`
(the block containing `scoring.is_eligible(mentions=10, authors=6, ...)`) with:

```python
def _forum(mentions=10, voices=6, text_ratio=0.9):
    return {'forum': scoring.Contribution(mentions, voices, text_ratio)}


def _broadcast(mentions=10, voices=2, text_ratio=0.9):
    return {'broadcast': scoring.Contribution(mentions, voices, text_ratio)}


def test_a_forum_ticker_needs_three_voices():
    assert scoring.is_eligible(_forum(voices=6)) is True
    assert scoring.is_eligible(_forum(voices=2)) is False


def test_volume_alone_is_never_enough():
    """One determined account can supply any volume."""
    assert scoring.is_eligible(_forum(mentions=50, voices=1)) is False


def test_copy_paste_is_never_enough():
    """Fifty accounts pasting one message defeat the voice gate completely."""
    assert scoring.is_eligible(_forum(mentions=50, voices=50, text_ratio=0.02)) is False


def test_too_few_mentions_is_never_enough():
    assert scoring.is_eligible(_forum(mentions=2, voices=2)) is False


def test_a_broadcast_ticker_qualifies_on_two_channels():
    """The whole reason this changed. A Telegram channel has one author by
    construction, so under the author gate a broadcast-only ticker could never
    reach the board however loud it got."""
    assert scoring.is_eligible(_broadcast(voices=2)) is True
    assert scoring.is_eligible(_broadcast(voices=1)) is False


def test_a_broadcast_ticker_still_needs_distinct_wording():
    """One channel's forty reposts must not become forty mentions, and two
    channels reposting each other must not become corroboration."""
    assert scoring.is_eligible(_broadcast(voices=2, text_ratio=0.02)) is False


def test_either_kind_can_carry_a_ticker_alone():
    """A union, not an intersection: the ticker qualifies on whichever kind
    can vouch for it, and a kind that cannot does not veto the one that can."""
    mixed = {**_forum(voices=6), **_broadcast(voices=1)}
    assert scoring.is_eligible(mixed) is True

    other = {**_forum(voices=1), **_broadcast(voices=3)}
    assert scoring.is_eligible(other) is True


def test_nothing_at_all_is_not_eligible():
    assert scoring.is_eligible({}) is False


def test_an_unknown_kind_is_judged_as_a_forum():
    unknown = {'something-new': scoring.Contribution(10, 2, 0.9)}
    assert scoring.is_eligible(unknown) is False
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_scoring.py -k eligib -v`
Expected: FAIL — `AttributeError: module 'features.radar.scoring' has no attribute 'Contribution'`

- [ ] **Step 3: Rewrite is_eligible**

In `personal_apps/features/radar/scoring.py`, add `import dataclasses` at the
top, add `MIN_DISTINCT_CHANNELS` to the `.config` import, and replace
`is_eligible` entirely:

```python
@dataclasses.dataclass
class Contribution:
    """What one kind of venue contributed to a ticker in a window.

    `voices` is deliberately not called `authors`. It is whatever counts as an
    independent voice for that kind -- distinct authors on a forum, distinct
    channels on a broadcast network -- and naming it after the forum case is
    what made the gate untranslatable in the first place.
    """
    mentions: int
    voices: int
    text_ratio: float


# Independent voices each kind needs. Unknown kinds get the forum floor, which
# is the stricter of the two.
_VOICE_FLOOR = {
    'forum': MIN_DISTINCT_AUTHORS,
    'broadcast': MIN_DISTINCT_CHANNELS,
}


def is_eligible(contributions):
    """Whether a reading is worth ranking at all.

    `contributions` maps source kind to Contribution. A ticker is eligible if
    ANY kind clears its own gate -- a union, not an intersection. A ticker
    carried by three Bluesky authors qualifies on the forum gate with no
    broadcast traffic at all; one carried by two Telegram channels qualifies
    on the broadcast gate even though its author count is two.

    Three gates per kind, because each is blind to what the others catch: raw
    volume means nothing at low counts, one determined voice can supply any
    volume, and fifty voices pasting one message defeat the voice gate
    completely. Volume and distinct wording are universal; only what counts as
    a voice differs.
    """
    return any(
        part.mentions >= MIN_MENTIONS
        and part.voices >= _VOICE_FLOOR.get(kind, MIN_DISTINCT_AUTHORS)
        and part.text_ratio >= MIN_DISTINCT_TEXT_RATIO
        for kind, part in contributions.items())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_radar_scoring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scoring.py personal_apps/tests/test_radar_scoring.py
git commit -m "feat(radar): let a ticker qualify on whichever kind of venue can vouch for it"
```

---

### Task 3: Counting channels, and wiring the union in

**Files:**
- Modify: `personal_apps/features/radar/leaderboard.py`
- Test: `personal_apps/tests/test_radar_leaderboard.py`

**Interfaces:**
- Consumes: `scoring.Contribution`, `scoring.is_eligible` (Task 2); `config.source_kind` (Task 1).
- Produces: `leaderboard._distinct_channels(tickers, sources, since, now) -> dict[str, int]`; `Row.sources` unchanged in meaning (contributing source names, sorted).

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_leaderboard.py`. The existing
`scored()` helper writes `RadarBucketSource` rows; this needs real posts so
the channel count is real, so add a local helper:

```python
def posted(ticker, external, source, channel, author, minutes_ago=20):
    """A post plus its mention, so author and channel counts are real.

    The bucket helpers above write counts; these write the rows those counts
    are derived from, which is what the channel gate actually reads.
    """
    from models import RadarMention, RadarPost
    when = NOW - dt.timedelta(minutes=minutes_ago)
    row = RadarPost(source=source, external_id=external, channel=channel,
                    author=author, created_utc=when, body='x', score=0,
                    num_comments=0, simhash=abs(hash(external)) % 10 ** 9,
                    first_seen=when, last_seen=when)
    db.session.add(row)
    db.session.flush()
    db.session.add(RadarMention(post_id=row.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=0.0))


def test_a_broadcast_only_ticker_reaches_the_board_on_two_channels(board, monkeypatch):
    """Before this, a Telegram-shaped source could never put a row up: one
    admin posts, every bucket has one author, and the author gate rejects it
    however loud the ticker gets.

    fourchan is borrowed as the broadcast source rather than inventing one,
    because a source not in config.SOURCES has no ingest path and could not
    have written these rows in the first place.
    """
    from features.radar import config

    monkeypatch.setitem(config.SOURCE_KIND, 'fourchan', 'broadcast')

    universe_row('LBB')
    scored('LBB', source='fourchan', mentions=8, authors=1)
    quoted('LBB', '100.00', '100.00')
    for n in range(8):
        posted('LBB', f'LBB{n}', 'fourchan',
               channel='chan-a' if n % 2 else 'chan-b', author='admin')
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['fourchan'], NOW)] == ['LBB']


def test_one_channel_shouting_is_not_two_voices(board, monkeypatch):
    from features.radar import config

    monkeypatch.setitem(config.SOURCE_KIND, 'fourchan', 'broadcast')

    universe_row('LBC')
    scored('LBC', source='fourchan', mentions=8, authors=1)
    quoted('LBC', '100.00', '100.00')
    for n in range(8):
        posted('LBC', f'LBC{n}', 'fourchan', channel='chan-a', author='admin')
    db.session.commit()

    assert leaderboard.build_rows(['fourchan'], NOW) == []


def test_a_forum_ticker_is_unaffected_by_the_new_path(board):
    """The regression guard. Forum sources must behave exactly as before."""
    universe_row('LBD')
    scored('LBD', mentions=10, authors=6)
    quoted('LBD', '100.00', '100.00')
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW)] == ['LBD']
```

The `board` fixture already wipes `RadarMention` by `ticker LIKE 'LB%'` and
`RadarPost` by `external_id LIKE 'LB%'`, which is why the helper above keys
both off the `LB` prefix. Nothing to add.

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_leaderboard.py -k broadcast -v`
Expected: FAIL — the broadcast-only ticker is rejected

- [ ] **Step 3: Add the channel count**

In `personal_apps/features/radar/leaderboard.py`, directly after
`_distinct_authors`:

```python
def _distinct_channels(tickers, sources, since, now):
    """True distinct channels per ticker across the window.

    The broadcast analogue of _distinct_authors. On a broadcast network the
    author is the channel's admin and is therefore always one; the channel is
    what varies, and two channels carrying the same symbol is the corroboration
    the author count cannot express.

    Counted from the mention rows for the same reason authors are: a bucket
    stores a COUNT, and the maximum across buckets systematically undercounts.
    """
    if not tickers:
        return {}

    rows = (db.session.query(RadarMention.ticker,
                             sa.func.count(sa.distinct(RadarPost.channel)))
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.ticker.in_(list(tickers)),
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium')))
            .group_by(RadarMention.ticker).all())
    return {ticker: count for ticker, count in rows}
```

- [ ] **Step 4: Build the per-kind contributions**

Add the import at the top: `from .config import PROVISIONAL_BASELINE_DAYS, source_kind`

In `build_rows`, beside the existing `author_counts` line:

```python
    channel_counts = _distinct_channels(grouped.keys(), sources, since, now)
```

Then replace the eligibility block. The current code computes pooled
`mentions` / `authors` / `text_ratio` and calls `is_eligible` with them;
the pooled figures are still what the ROW reports, so they stay — what changes
is that the gate is fed per kind:

```python
        # The gate is per kind: a forum's independent voices are its authors,
        # a broadcast network's are its channels. The pooled figures below
        # still describe the row; they just no longer decide it.
        by_kind = collections.defaultdict(
            lambda: [0, 1.0])          # [mentions, min text ratio]
        for bucket in buckets:
            kind = source_kind(bucket.source)
            by_kind[kind][0] += bucket.mention_count
            by_kind[kind][1] = min(by_kind[kind][1], bucket.distinct_text_ratio)

        contributions = {
            kind: scoring.Contribution(
                mentions=totals[0],
                voices=(channel_counts.get(ticker, 0) if kind == 'broadcast'
                        else authors),
                text_ratio=totals[1])
            for kind, totals in by_kind.items()
        }

        # Below the floor there is nothing to rank. Showing it low would imply
        # it was measured and found wanting, when it was never measurable.
        if not scoring.is_eligible(contributions):
            continue
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_radar_leaderboard.py tests/test_radar_board.py -v`
Expected: PASS

- [ ] **Step 6: Run the whole radar suite**

Run: `python -m pytest tests/ -q -k radar`
Expected: PASS. Anything failing here is a real regression from the signature
change, not flakiness — `is_eligible` had exactly one production caller but
several test call sites.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/radar/leaderboard.py personal_apps/tests/test_radar_leaderboard.py
git commit -m "feat(radar): count channels where authors cannot tell voices apart"
```

---

### Task 4: The venues filter

**Files:**
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Test: `personal_apps/tests/test_radar_board.py`, `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Produces: `build_rows(..., min_venues=1)`; `board.build(..., min_venues=1)`; query parameter `venues=1|2`; payload key `min_venues`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_board.py`:

```python
def test_the_venue_filter_keeps_only_corroborated_rows(clean):
    """The gold-mine query: not what is loudest, but what more than one venue
    is talking about at the same time."""
    universe(f'{PREFIX}A')
    universe(f'{PREFIX}B')
    bucket(f'{PREFIX}A', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='fourchan')
    db.session.commit()

    built = board.build(['bluesky', 'fourchan'], NOW, min_venues=2)

    assert [e.rank.ticker for e in built.rows] == [f'{PREFIX}B']


def test_venue_counts_are_taken_before_the_venue_filter(clean):
    """Same rule the segment counts follow: the counts label the control, so
    computing them after the filter would report the filtered size in both
    slots."""
    universe(f'{PREFIX}A')
    universe(f'{PREFIX}B')
    bucket(f'{PREFIX}A', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='fourchan')
    db.session.commit()

    built = board.build(['bluesky', 'fourchan'], NOW, min_venues=2)

    assert built.venue_counts['any'] == 2
    assert built.venue_counts['multi'] == 1
```

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_an_unsupported_venue_filter_is_rejected(client):
    assert client.get('/radar/api/board?venues=7').status_code == 400
    assert client.get('/radar/api/board?venues=2').status_code == 200


def test_the_payload_carries_the_venue_filter_and_its_counts(client):
    import json as _json
    payload = _json.loads(client.get('/radar/api/board').data)

    assert payload['min_venues'] == 1
    assert set(payload['venue_counts']) == {'any', 'multi'}
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_board.py -k venue -v`
Expected: FAIL — `build() got an unexpected keyword argument 'min_venues'`

- [ ] **Step 3: Filter in the leaderboard**

In `build_rows`, add `min_venues=1` to the signature, document it, and filter
next to the existing segment filter:

```python
        if segment is not None and row_segment != segment:
            continue
        # Breadth as a filter, not as a score. `sources` is already the list of
        # sources that actually contributed, so this asks how many venues are
        # talking rather than how many the viewer has switched on.
        if len(contributing) < min_venues:
            continue
```

- [ ] **Step 4: Count venues before filtering, in board.build**

`board.build` already calls `build_rows` unfiltered to compute
`segment_counts`, then filters in Python. Do the same for venues so both
counts come from one unfiltered pass:

```python
    counts = collections.Counter(row.segment for row in ranked)
    segment_counts = dict(counts)
    segment_counts['all'] = len(ranked)

    # Both venue counts come from the same unfiltered pass, for the reason
    # segment counts do: they label the control, and counting after the filter
    # would report the filtered size in every slot.
    venue_counts = {
        'any': len(ranked),
        'multi': sum(1 for row in ranked if len(row.sources) > 1),
    }

    if segment is not None:
        ranked = [row for row in ranked if row.segment == segment]
    if min_venues > 1:
        ranked = [row for row in ranked if len(row.sources) >= min_venues]
```

Add `min_venues=1` to `build`'s signature, add `venue_counts: dict` and
`min_venues: int` to the `Board` dataclass, and pass both through.

- [ ] **Step 5: Validate and serialize it**

In `personal_apps/features/radar/routes/api.py`, add to `parse_query` beside
the window check:

```python
    try:
        min_venues = int(args.get('venues', 1))
    except ValueError:
        raise BadQuery('bad venues')
    if min_venues not in (1, 2):
        raise BadQuery('unsupported venues')
```

Return it alongside the rest, pass it into `board_mod.build`, and add to
`serialize`:

```python
        'min_venues': board.min_venues,
        'venue_counts': board.venue_counts,
```

`parse_query` returns a bare 4-tuple today. **Make it return a dataclass**,
not a 5-tuple:

```python
@dataclasses.dataclass
class Query:
    sources: list
    segment: str | None
    window: int
    limit: int
    min_venues: int
```

Five positional fields unpacked identically in two call sites is one
transposition away from silently swapping `limit` and `min_venues`, and both
are ints so nothing would complain. Update `board()` and `build_payload` to
read attributes.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/ -q -k radar`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/radar personal_apps/tests
git commit -m "feat(radar): filter to what more than one venue is talking about"
```

---

### Task 5: Venues on the row and in the controls

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts`
- Create: `personal_apps/static/radar/src/board/Venues.tsx`
- Modify: `personal_apps/static/radar/src/board/ScanRow.tsx`
- Modify: `personal_apps/static/radar/src/board/Controls.tsx`
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Modify: `personal_apps/static/radar/radar.css`
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Produces: `<Venues all={string[]} lit={string[]} />`; `Selection.minVenues: number`; `BoardPayload.min_venues`, `BoardPayload.venue_counts`.

- [ ] **Step 1: Write the failing tests**

Add `min_venues: 1, venue_counts: { any: 4, multi: 2 },` to the `payload()`
fixture defaults, then append:

```tsx
describe('breadth on a row', () => {
  it('shows which venues are talking, not how many', () => {
    // Fixed slots, lit and dim, so the same position means the same source
    // down the whole column. A count cannot be scanned vertically.
    const mixed = payload({
      rows: [row(), row(), row(),
             row({ ticker: 'DDD', sources: ['bluesky', 'fourchan'] })],
    })
    const { container } = render(<BoardPage initial={mixed} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(scan.querySelectorAll('.venue')).toHaveLength(3)
    expect(scan.querySelectorAll('.venue.on')).toHaveLength(2)
  })

  it('names each slot for assistive tech, since the mark is only colour', () => {
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(within(scan).getByLabelText(/Bluesky/)).toBeInTheDocument()
  })
})

describe('the venues filter', () => {
  it('offers the two-or-more query with its count', () => {
    render(<BoardPage initial={payload()} />)

    const group = screen.getByRole('group', { name: 'Venues' })
    expect(within(group).getByRole('button', { name: /2\+/ })).toBeInTheDocument()
    expect(within(group).getByText('2')).toBeInTheDocument()
  })

  it('refetches, because the filter is applied server-side', async () => {
    render(<BoardPage initial={payload()} />)

    await userEvent.click(within(screen.getByRole('group', { name: 'Venues' }))
      .getByRole('button', { name: /2\+/ }))

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toContain('venues=2')
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts BoardPage`
Expected: FAIL — no `.venue` elements

- [ ] **Step 3: Add the types**

In `types.ts`, add to `BoardPayload`:

```ts
  min_venues: number
  venue_counts: Record<string, number>
```

and to `Selection`:

```ts
  /** 1 = any, 2 = only rows more than one venue is talking about. */
  minVenues: number
```

- [ ] **Step 4: Write the component**

Create `personal_apps/static/radar/src/board/Venues.tsx`:

```tsx
import { sourceLabel } from '../format'

/** Which venues are talking about this ticker.
 *
 *  Fixed slots in the payload's source order, lit or dim -- not a count and
 *  not a list. A variable-length list cannot be read down a column, and the
 *  question here is WHICH venues agree, which a number cannot answer.
 *
 *  Each slot carries its own label: the state is conveyed by colour alone,
 *  which is exactly the case that needs a text alternative.
 */
export function Venues({ all, lit }: { all: string[]; lit: string[] }) {
  return (
    <span className="venues">
      {all.map((source) => {
        const on = lit.includes(source)
        return (
          <i key={source} className={on ? 'venue on' : 'venue'}
             aria-label={`${sourceLabel(source)}: ${on ? 'talking' : 'quiet'}`}
             role="img" />
        )
      })}
    </span>
  )
}
```

- [ ] **Step 5: Put it in the row**

`ScanRow` needs the full source list to draw dim slots, so pass it down. In
`BoardPage`, add `allSources={payload.all_sources}` to the `<ScanRow>` call; in
`ScanRow`, take `allSources: string[]` and render inside the counts cell:

```tsx
      <div className="n">
        {row.mentions} / {row.authors}
        <Venues all={allSources} lit={row.sources} />
      </div>
```

Update the heading in `BoardPage` from `Mentions / people` to
`Mentions / people / venues`, and the mobile caption in `ScanRow` to include
the same component.

- [ ] **Step 6: Add the control**

In `Controls`, add props `minVenues: number` and `onVenues: (n: number) => void`,
and a group after Sources:

```tsx
      <div className="group">
        <span className="lbl" id="venues-lbl">Venues</span>
        <div className="seg" role="group" aria-labelledby="venues-lbl">
          <button type="button" aria-pressed={minVenues === 1}
                  onClick={() => onVenues(1)}>
            any <span className="n">{payload.venue_counts.any ?? 0}</span>
          </button>
          <button type="button" aria-pressed={minVenues === 2}
                  onClick={() => onVenues(2)}>
            2+ <span className="n">{payload.venue_counts.multi ?? 0}</span>
          </button>
        </div>
      </div>
```

In `BoardPage`, seed `minVenues: initial.min_venues` into the `Selection`
state and wire `onVenues` to `setSelection`. It belongs in `Selection`, not in
its own state, because unlike the chart span it **does** trigger a refetch.

Add `venues` to `queryFor` in `api.ts`:

```ts
  if (selection.minVenues > 1) params.set('venues', String(selection.minVenues))
```

- [ ] **Step 7: Style it**

Append to `radar.css`, beside the `.mk` rules:

```css
/* Which venues are talking. Slots, not a count: the position of each dot is
   fixed, so the same place always means the same source down the column. */
.venues { display: inline-flex; gap: 3px; margin-left: 7px; vertical-align: 1px; }
.venue {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--rule);
}
.venue.on { background: var(--mark); }
```

- [ ] **Step 8: Run everything**

Run: `npx tsc --noEmit` — no output
Run: `npx vitest run -c vite.radar.config.ts` — PASS
Run: `npm run build` — two "built in" lines
Run: `python -m pytest tests/ -q -k "radar or vite or auth"` — PASS

- [ ] **Step 9: Verify in a browser**

Screenshot `/radar/?window=24` at 1440 and 390 with python-playwright, then
again with `venues=2`. Assert programmatically:

```python
info = page.evaluate("""() => ({
  rows: document.querySelectorAll('.row').length,
  slots: document.querySelectorAll('.row .venue').length,
  lit: document.querySelectorAll('.row .venue.on').length,
  overflow: document.documentElement.scrollWidth > window.innerWidth,
})""")
```

`slots` must be `rows × all_sources.length` — a fixed grid, not a variable
list. `overflow` must be false at both widths. Read the PNGs back and look at
them: five-pixel dots inside a numeric cell is the kind of thing that measures
fine and reads as dirt on the screen.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/static/radar personal_apps/tests
git commit -m "feat(radar): show which venues are talking, and filter to the ones that agree"
```
