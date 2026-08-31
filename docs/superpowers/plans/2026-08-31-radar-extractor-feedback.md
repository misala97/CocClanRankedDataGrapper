# Radar Extractor Feedback and Hygiene — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the two measured deterministic Reddit pollution channels (username-only tickers, AutoModerator posts) without losing parent-thread comments, give extraction one shared provenance-bearing implementation, and ship the read-only sentiment-v2 diagnostic that turns finalized judgments into extraction feedback.

**Architecture:** A canonical `ExtractionInput` (authored text vs thread context, username discarded structurally) feeds a reworked pure extractor that returns provenance-bearing `Match` objects; ingest consumes it and logs intake by reason. The policy change rides a new `EXTRACTION_POLICY_GENERATION` inside `source_config_version()`. The diagnostic reconstructs provenance by calling the same pure function over retained text — no new columns, no mutations, hard readiness gates before any recommendation.

**Tech Stack:** Pure Python in `features/radar/extraction.py` + `config.py`; ingest wiring; one operator script under `scripts/`; pytest against the real dev DB per house convention.

**Spec:** `docs/superpowers/specs/2026-08-31-radar-extractor-feedback-design.md` (reviewed against the repo 2026-08-31 — no contradictions found, no spec adjustments needed).

## Global Constraints

- Branch `dev_personal`; commit per task; only `main` deploys; Michi runs the deploy.
- `cd personal_apps && python -m pytest tests/<file> -q`; real dev MySQL DB, ZZ-sentinel ownership, future-dated fixtures.
- The binding sentiment prompt/schema hashes must NOT change (`test_the_binding_prompt_is_byte_exact` stays green untouched) — spec §12.4.
- Sentiment preparation (`sentiment_input.prepare_sentiment_input`) is NOT modified: body-only for Reddit comments stays exactly as shipped.
- Enum values and reason names verbatim from spec §6: `explicit_cashtag | bare_named | bare_source_high | bare_low`, plus the diagnostic-only `text_changed_or_absent`.
- No new DB columns, no migrations (spec §6). The diagnostic performs zero writes.
- v1 `llm_sentiment` is never used as relevance/origin truth anywhere in this plan.
- Absence-shaped tests must demonstrate teeth against the broken variant first (spec §11 closing rule) — in particular username-only and AutoModerator regressions must fail on the pre-fix extractor.
- `%`-formatting, house comment style, naive UTC.

---

## File Structure

**Modified**

| Path | Change |
|---|---|
| `personal_apps/features/radar/extraction.py` | `ExtractionInput`, `prepare_extraction_input`, `Match`, `extract()` with provenance; `extract_tickers` becomes a thin compatibility wrapper |
| `personal_apps/features/radar/config.py` | `EXTRACTION_POLICY_GENERATION`, `EXTRACTION_INPUT_VERSION` participation, `AUTOMATED_AUTHORS` + `is_automated_author()`, version-payload keys |
| `personal_apps/features/radar/ingest.py` | AutoModerator drop, canonical extraction input, per-cycle intake-by-reason counters in the summary |
| `personal_apps/run_radar_ingest.py` | `tick()` log line gains intake reasons |
| `personal_apps/tests/test_radar_extraction.py` | §11.1 canonical-input and provenance regressions |
| `personal_apps/tests/test_radar_ingest.py` | AutoModerator + intake-counter + parent-context-retention tests |
| `personal_apps/tests/test_radar_config.py` | generation participates in the stamp |

**Created**

| Path | Responsibility |
|---|---|
| `personal_apps/scripts/diagnose_extractor_feedback.py` | Read-only v2 diagnostic: readiness gates, strata, Wilson-ranked ticker/origin feedback |
| `personal_apps/tests/test_diagnose_extractor_feedback.py` | Pure-piece tests: readiness, Wilson, provenance reconstruction, no-mutation guard |
| `personal_apps/scripts/capture_unmatched_reddit.py` | OPTIONAL (§8.2): throwaway-spike capture of unmatched Reddit comments for the alias measurement |
| `personal_apps/scripts/capture_promoted_sample.py` | OPTIONAL (§8.3): promoted-event sample capture for the promotion-precision audit |

**Interface reference**

```python
# extraction.py
EXTRACTION_INPUT_VERSION = 1
REASONS = ('explicit_cashtag', 'bare_named', 'bare_source_high', 'bare_low')

@dataclasses.dataclass(frozen=True)
class ExtractionInput:
    author_text: str        # the commenter's/author's own words (username never included)
    thread_context: str     # reddit comment parent title; '' everywhere else
    source: str
    author: str | None
    channel: str
    is_comment: bool

def prepare_extraction_input(source, title, body, author=None, channel=None) -> ExtractionInput

@dataclasses.dataclass(frozen=True)
class Match:
    ticker: str
    confidence: str                  # 'high' | 'low' (medium stays a rollup award)
    reason: str                      # strongest, from REASONS
    in_author_text: bool
    in_thread_context: bool

def extract(prepared, lookup, allow_bare=True, allow_single_letter=True,
            bare_confidence='low') -> list[Match]        # sorted by ticker
def extract_tickers(title, body, lookup, ...) -> [(symbol, confidence)]
    # thin wrapper over extract() on a non-comment ExtractionInput; the
    # existing test_radar_extraction call shape keeps working unchanged.

# config.py
EXTRACTION_POLICY_GENERATION = 1
AUTOMATED_AUTHORS = frozenset({'automoderator'})   # normalized form
def is_automated_author(source, author) -> bool    # reddit ROOT only

# ingest run_cycle summary gains:
summary['intake_reasons']  # {source: {reason: count}} for THIS cycle
```

---

# Stage 1 — Canonical extraction input and provenance

## Task 1: `ExtractionInput` and `prepare_extraction_input`

**Files:**
- Modify: `personal_apps/features/radar/extraction.py`
- Test: `personal_apps/tests/test_radar_extraction.py` (extend)

**Interfaces:** produces `ExtractionInput`, `prepare_extraction_input`, `EXTRACTION_INPUT_VERSION` per the reference block. Consumes `config.source_root`.

Spec §4 rules verbatim. The comment-shape detector is the SAME predicate `sentiment_input` uses (title starts `/u/`, contains ` on `, reddit root only) — assert that equivalence in a test so the two modules cannot drift. Split ONCE at the FIRST ` on ` (usernames cannot contain spaces, so the first delimiter is always the structural one); the left side is discarded from extraction entirely, the right side becomes `thread_context`. No global `/u/...` stripping anywhere — an authored post MENTIONING a Reddit user keeps its text (spec §4 closing rule).

- [ ] **Step 1: Write the failing tests**

```python
# appended to tests/test_radar_extraction.py
from features.radar.extraction import prepare_extraction_input


def test_a_reddit_comment_splits_into_context_and_authored_text():
    p = prepare_extraction_input(
        'reddit:wallstreetbets', '/u/alice on Here goes everything $SNDK',
        'How is it going now?')
    assert p.is_comment is True
    assert p.thread_context == 'Here goes everything $SNDK'
    assert p.author_text == 'How is it going now?'
    assert '/u/alice' not in p.thread_context


def test_the_split_happens_once_so_on_inside_the_parent_survives():
    p = prepare_extraction_input(
        'reddit:options', '/u/bob on Thoughts on NVDA on Monday', 'sure')
    assert p.thread_context == 'Thoughts on NVDA on Monday'


def test_a_submission_title_is_authored_text_with_no_context():
    p = prepare_extraction_input(
        'reddit:options', 'NVDA to the moon', 'calls')
    assert p.is_comment is False
    assert p.thread_context == ''
    assert 'NVDA to the moon' in p.author_text


def test_a_non_reddit_u_slash_string_is_never_stripped():
    p = prepare_extraction_input(
        'fourchan', '/u/CEO_of_SOXL on life', 'body')
    assert p.is_comment is False
    assert '/u/CEO_of_SOXL on life' in p.author_text


def test_nulls_become_empty_strings():
    p = prepare_extraction_input('bluesky', None, None)
    assert (p.author_text, p.thread_context) == ('', '')


def test_the_comment_detector_matches_sentiment_inputs_detector():
    """The two modules share one structural fact about Reddit's feed; if
    either predicate drifts, extraction and sentiment disagree about what
    a comment even is."""
    from features.radar import sentiment_input
    cases = [('reddit:a', '/u/x on parent', 'b'),
             ('reddit:a', 'plain title', 'b'),
             ('bluesky', '/u/x on parent', 'b'),
             ('reddit:a', '/u/x without delimiter', 'b')]
    for source, title, body in cases:
        ours = prepare_extraction_input(source, title, body).is_comment
        theirs = sentiment_input.prepare_sentiment_input(
            source, title, body, 'ZZX').is_comment
        assert ours == theirs, (source, title)
```

- [ ] **Step 2: Run to verify failure** — `cd personal_apps && python -m pytest tests/test_radar_extraction.py -q` → `ImportError: cannot import name 'prepare_extraction_input'`

- [ ] **Step 3: Implement**

```python
# extraction.py additions (below the module docstring / imports)
import dataclasses

from .config import source_root

EXTRACTION_INPUT_VERSION = 1


@dataclasses.dataclass(frozen=True)
class ExtractionInput:
    """What extraction is allowed to read, with the scopes kept apart.

    thread_context can ASSOCIATE a comment with a ticker; author_text is
    the only text that speaks for the author; the synthetic username is
    neither and is discarded structurally here -- never by a global regex,
    because an authored post mentioning a Reddit user is content
    (spec 2026-08-31 extractor-feedback §4).
    """
    author_text: str
    thread_context: str
    source: str
    author: str | None
    channel: str
    is_comment: bool


def prepare_extraction_input(source, title, body, author=None, channel=None):
    title_c = (title or '').strip()
    body_c = (body or '').strip()
    is_comment = (source_root(source or '') == 'reddit'
                  and title_c.startswith('/u/') and ' on ' in title_c)
    if is_comment:
        # Split ONCE at the first delimiter: usernames cannot contain
        # spaces, so the first ' on ' is always the structural one and a
        # parent title containing ' on ' survives intact.
        _username, thread_context = title_c.split(' on ', 1)
        author_text = body_c
    else:
        thread_context = ''
        author_text = ' '.join(part for part in (title_c, body_c) if part)
    return ExtractionInput(author_text=author_text,
                           thread_context=thread_context,
                           source=source or '', author=author,
                           channel=channel or '', is_comment=is_comment)
```

- [ ] **Step 4: Run to verify pass** — same command, all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(radar): canonical extraction input separates context from authored text"`

---

## Task 2: Provenance-bearing `extract()` with the compatibility wrapper

**Files:**
- Modify: `personal_apps/features/radar/extraction.py` (rework lines 43–119)
- Test: `personal_apps/tests/test_radar_extraction.py` (extend)

**Interfaces:** produces `Match`, `REASONS`, `extract(prepared, lookup, ...)`; `extract_tickers` keeps its exact signature and return shape (the whole existing suite in `test_radar_extraction.py` must stay green as-is — that IS the regression harness for "no unrelated source changes behavior", spec §12.6).

Semantics, all from spec §5.1/§6 against the current code at extraction.py:65–117:

- Scan `author_text` and `thread_context` SEPARATELY with the same rules, then merge per ticker: strongest confidence wins (existing `_CONFIDENCE_RANK` behavior), scope flags OR together, and the reason follows the occurrence that carried the strongest confidence (priority: `explicit_cashtag` > `bare_named` > `bare_source_high` > `bare_low`).
- Name corroboration (`named`) uses the lowered words of BOTH scopes combined — a parent title naming the company legitimately corroborates a bare token in the body; they are one conversation. Documented in the docstring as a deliberate choice.
- The username never enters either scope (Task 1 guarantees it), which IS the §5.1 username exclusion: a ticker appearing only there simply has no occurrence to match. A ticker also present in context or body survives with that occurrence's form.
- Stopword-blocked and non-universe candidates yield no Match, exactly as today.
- `extract_tickers(title, body, ...)` wraps: `extract(prepare-like non-comment input)` and returns `sorted((m.ticker, m.confidence))` — byte-compatible with every current caller and test. Its docstring notes it exists for compatibility and the reddit comment path must go through `prepare_extraction_input`.

Key tests (Step 1, all failing first; the two teeth cases run against the OLD `extract_tickers(title, body)` path via a temporary revert during development to prove they bite — record that in the test docstrings):

```python
def test_a_ticker_only_in_the_username_is_not_extracted():
    """TEETH: fails on the pre-fix extractor, which scanned the synthetic
    title whole and minted 133 such mentions in the restore."""
    p = prepare_extraction_input('reddit:wallstreetbets',
                                 '/u/CEO_of_SOXL on Daily Discussion Thread',
                                 'What movie should I watch tonight?')
    assert extraction.extract(p, LOOKUP_WITH_SOXL) == []


def test_a_parent_title_ticker_still_counts_without_a_body_repeat():
    p = prepare_extraction_input('reddit:wallstreetbets',
                                 '/u/alice on Here goes everything $SNDK',
                                 'How is it going now?')
    matches = extraction.extract(p, LOOKUP_WITH_SNDK)
    assert [(m.ticker, m.confidence) for m in matches] == [('SNDK', 'high')]
    assert matches[0].in_thread_context and not matches[0].in_author_text
    assert matches[0].reason == 'explicit_cashtag'


def test_a_ticker_in_username_and_body_survives_from_the_body():
    ...  # '/u/GME_hodler on thread' + body 'GME to the moon' (reddit,
        # bare_confidence='high') -> one Match, reason bare_source_high,
        # in_author_text True


def test_an_empty_body_comment_still_inherits_thread_context():
    ...  # body '   ', $SNDK in parent -> extracted


def test_reason_priority_and_scope_merge():
    ...  # $NVDA in context + bare NVDA in body -> one Match, high,
        # reason explicit_cashtag, both scope flags True


def test_the_wrapper_is_byte_compatible():
    ...  # extract_tickers('t $GME', 'b', LOOKUP) == [('GME', 'high')]
```

Commit: `git commit -m "feat(radar): extraction returns provenance and drops username-only tickers"`

---

# Stage 2 — Hygiene in ingest and the version bump

## Task 3: AutoModerator exclusion and canonical input in ingest

**Files:**
- Modify: `personal_apps/features/radar/config.py`, `personal_apps/features/radar/ingest.py` (`_extract_for`, lines 66–88), `personal_apps/run_radar_ingest.py` (`tick` log line)
- Test: `personal_apps/tests/test_radar_ingest.py`, `personal_apps/tests/test_radar_daemon.py` (log shape only if pinned)

**Interfaces:** produces `config.AUTOMATED_AUTHORS`, `config.is_automated_author(source, author)`; `ingest.run_cycle` summary gains `intake_reasons`; consumes Task 1/2.

`config.py`:

```python
# Sentiment/extractor hygiene (spec 2026-08-31 §5.2): posts authored by
# Reddit's automation are not human chatter and are dropped BEFORE
# extraction. Exact normalized comparison only -- '/u/AutoModeratorFan'
# is a person. Reddit root only: an unrelated network's display name may
# legitimately be anything.
AUTOMATED_AUTHORS = frozenset({'automoderator'})


def is_automated_author(source, author):
    if source_root(source) != 'reddit' or not author:
        return False
    normalized = author.strip().lower()
    for prefix in ('/u/', 'u/'):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized in AUTOMATED_AUTHORS
```

`ingest._extract_for` becomes:

```python
def _extract_for(raw, lookup):
    if is_automated_author(raw.source, raw.author):
        return []
    prepared = extraction.prepare_extraction_input(
        raw.source, raw.title, raw.body, author=raw.author,
        channel=raw.channel)
    scan_text = '%s %s' % (prepared.author_text, prepared.thread_context)
    if looks_like_bot_feed(scan_text):
        return []
    matches = extraction.extract(
        prepared, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
    return [(m.ticker, m.confidence, m.reason) for m in matches
            if not coin_collision_dropped(raw.source, m.ticker)]
```

Downstream `_store_mentioning_posts` unpacks the third element into per-cycle counters (`collections.Counter` per source) and otherwise passes `(symbol, confidence)` through unchanged — MentionRow, simhash inputs, and stored title/body are untouched (raw title incl. username still stored; hygiene changes what is COUNTED, never what is retained, spec §5.2). `run_cycle` returns `summary['intake_reasons']`; `tick()` logs it:

```python
    logger.info('radar cycle posts=%d new=%d mentions=%d buckets=%d sources=%s '
                'aggregate=%s catchup_depth=%s intake=%s', ...,
                _format_operational_map(summary['intake_reasons']))
```

Tests (teeth for AutoModerator: assert the fixture produces a mention when `is_automated_author` is monkeypatched to always-False — proving the gate, not the fixture, does the work): all three spellings excluded case-insensitively; `/u/AutoModeratorFan` retained; a bluesky post authored 'AutoModerator' retained (root scoping); the summary's `intake_reasons` counts a cashtag fixture under `explicit_cashtag`; an existing parent-context fixture still produces its mention end-to-end (spec §12.2).

Commit: `git commit -m "feat(radar): drop automation authors and count intake by extraction reason"`

---

## Task 4: `EXTRACTION_POLICY_GENERATION` in the version stamp

**Files:**
- Modify: `personal_apps/features/radar/config.py` (`source_config_version`, payload dict at ~line 661)
- Test: `personal_apps/tests/test_radar_config.py`

Constants beside `ROLLUP_GENERATION`:

```python
# Extractor policy generation (spec 2026-08-31 §5.3). Bumped when WHAT
# extraction counts changes: generation 1 = canonical input (username
# discarded, thread context split out) + the automated-author drop.
# A ROLLBACK also increments this -- it must never restore an older stamp
# and mix post-rollback observations into the pre-release baseline.
EXTRACTION_POLICY_GENERATION = 1
```

Payload gains three explicit, stable keys (no function hashes, spec §5.3):

```python
        'extraction_policy_generation': EXTRACTION_POLICY_GENERATION,
        'extraction_input_version': extraction_input_version,
        'automated_authors': sorted(AUTOMATED_AUTHORS),
```

(`extraction_input_version` imported lazily inside the function from `extraction` to respect the existing import direction: extraction imports config, so config must not import extraction at module level — mirror of the documented cycle-avoidance pattern.)

Tests: bumping `EXTRACTION_POLICY_GENERATION` changes the stamp (patch-object, mirroring `test_the_promotion_ceiling_is_hashed_into_the_config_version`); adding an automated author changes it; reordering `AUTOMATED_AUTHORS` does not.

Commit: `git commit -m "feat(radar): extraction policy generation rides the config stamp"`

---

# Stage 3 — The read-only v2 diagnostic

## Task 5: Diagnostic core — readiness, strata, reconciliation

**Files:**
- Create: `personal_apps/scripts/diagnose_extractor_feedback.py`
- Test: `personal_apps/tests/test_diagnose_extractor_feedback.py`

**Interfaces:** pure helpers importable for tests: `readiness(judgment_days, slice_n)`, `wilson_low(k, n)` (95% lower bound), `provenance_for(mention, post, lookup) -> (reason, scopes) | 'text_changed_or_absent'`, `strata(rows) -> tables`. CLI: `python -m scripts.diagnose_extractor_feedback [--combine-prompt-versions]`.

Binding behaviors, spec §7:

- Always prints population + coverage; recommendations are marked **NOT ACTIONABLE** until ≥7 consecutive live days of finalized judgments (distinct UTC days of `RadarSentimentJudgment.created_utc` with no gap > 1 day) AND the compared slice has ≥50 finalized judgments. With the current restore (zero v2 judgments) it must print a zero-coverage, zero-recommendation report and exit 0 — that exact run is acceptance §12.7.
- Provenance via `prepare_extraction_input` + `extract` over the RETAINED text with the source's live policy args — the same pure functions, never a second regex (spec §11.3). A judged mention whose ticker no longer matches classifies as `text_changed_or_absent`.
- Strata exactly per §7.2; rates NEVER merge `irrelevant` with relevance-`uncertain` or `broadcast_or_automated` with origin-`uncertain`; unjudged/missing rows are their own row. Prompt versions separate by default; `--combine-prompt-versions` merges with a loud label.
- Primary-vs-reviewed split from `RadarSentimentJudgment` history (latest primary row vs materialized final).
- Zero writes: the script never calls `commit`; the no-mutation test asserts `db.session.new/dirty/deleted` are all empty after a full run AND row counts of every radar table are unchanged. Teeth: temporarily add a mutation in the test's own patched copy and watch the guard fail.

`wilson_low`:

```python
def wilson_low(successes, n, z=1.96):
    """95% lower bound; the ranking key, so one bad answer on a tiny
    ticker cannot outrank a measured failure (spec §7.3)."""
    if not n:
        return 0.0
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * ((phat * (1 - phat) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, (center - margin) / denom)
```

Tests: readiness gates (6 days → not actionable; 7 with a gap → not actionable; 7 consecutive + n=50 → actionable), Wilson reproducibility against hand-computed values, provenance on synthetic post/mention pairs incl. `text_changed_or_absent`, uncertainty-never-merged assertions on the strata output, and the no-mutation guard.

Commit: `git commit -m "feat(radar): read-only extractor diagnostic over finalized v2 judgments"`

---

## Task 6: Diagnostic rankings — per-ticker and Bluesky origin

**Files:**
- Modify: `personal_apps/scripts/diagnose_extractor_feedback.py`
- Test: `personal_apps/tests/test_diagnose_extractor_feedback.py` (extend)

Per spec §7.3/§7.4:

- Ticker/source/form slices ranked by Wilson-lower-bound of irrelevant share and (separately) broadcast share; every row prints `numerator/denominator` beside the interval. Minimum slice n=50 to appear in the RANKED list; smaller slices appear in an unranked appendix.
- Bluesky origin table: authors and template fingerprints (exact simhash groups over retained posts) with post count, mention count, duplicate ratio, finalized origin distribution. No block proposals — the report body carries the spec's own sentence that any future suppression rule needs a new design.
- Output ends with the §7.3 checklist of what a future demotion design must include, verbatim-condensed, so the report itself carries its non-authorization.

Tests: ranking respects Wilson (a 1/1 ticker ranks below a 40/80 one), n<50 lands in the appendix, fingerprint grouping is exact-simhash.

Commit: `git commit -m "feat(radar): wilson-ranked ticker and origin feedback in the diagnostic"`

---

# Stage 4 — Optional offline measurement protocols (spec §8; build if time permits, skippable without affecting acceptance)

## Task 7 (optional): `capture_unmatched_reddit.py`

Throwaway-spike style (house `measure_*` pattern, aggregate-conscious): polls the configured subreddits' comment feeds within the existing budget discipline (reuse `sources.reddit.fetch_one` with generous pauses), stores comments where `extract()` finds nothing — raw text, timestamp, subreddit — into `scratchpad/unmatched_reddit/capture.jsonl` for ≥1 day of operator-run capture. A `--summarize` mode reports candidate alias hits (`Tesla`, `Google`, case-insensitive scoped forms) with counts, WITHOUT grading — grading is the §8.2 blind protocol, done by a human on a frozen sample. Pure-piece test: the unmatched filter uses the production `extract()`.

## Task 8 (optional): `capture_promoted_sample.py`

Samples ≥100 `promoted=True` journal events across contributing sources (48h retention window — run it while promotion is warm), joins retained post text where the post survives, marks `text_unavailable` honestly where a low-only post was never stored (spec §8.3's own caveat), and writes a blind grading sheet (no promotion flag visible in the grading columns) plus a same-size unpromoted-low control sample. No thresholds change from this script — it produces the audit sheet only.

---

# Rollout checkpoints (spec §10 order)

1. Tasks 1–4 deploy together (hygiene release): independently deployable before sentiment v2 produces judgments. On deploy day, compare `intake=` log lines before/after: an expected Reddit drop matching the username-only + AutoModerator rates (133 + 126 over ~9 days in the restore ≈ a few dozen/day); **any drop in parent-context comment intake is the rollback condition** (spec §10).
2. The generation bump means Reddit baselines re-warm (14 provisional days) — expected, visible, not a regression.
3. Task 5–6 (diagnostic) is safe any time; before v2 judgments exist it must print zero coverage and recommend nothing (acceptance §12.7 — run it once against the restore as part of the release).
4. After sentiment v2 has ≥7 consecutive live days: run the diagnostic for the evidence-phase acceptance (§12 second block). Its output — not this plan — decides whether demotion/alias/promotion designs get written.
5. Rollback: revert the hygiene commits AND bump `EXTRACTION_POLICY_GENERATION` to 2 in the same commit (never restore the old stamp); judgments and history stay untouched.

# Acceptance mapping

| Spec item | Where |
|---|---|
| §12.1 suites | full pytest at the end of Stage 2 and Stage 3 |
| §12.2 parent-context fixtures keep tickers | Task 2 + Task 3 ingest test |
| §12.3 username/AutoModerator produce nothing | Task 2/3 teeth-checked regressions |
| §12.4 sentiment hashes unchanged | untouched test `test_the_binding_prompt_is_byte_exact` |
| §12.5 stamp changes intentionally | Task 4 tests |
| §12.6 no unrelated source changes | wrapper byte-compatibility + existing extraction suite green |
| §12.7 zero-coverage dry run | Task 5 + checkpoint 3 |
| §11 teeth rule | Task 2/3/5 broken-variant steps |

# Plan self-review notes

- Spec reviewed against the repo before planning: comment detector parity with `sentiment_input` (now pinned by a test), author storage form `/u/...` (covered by the three normalized spellings), reason enum ↔ code paths at extraction.py:65–117 one-to-one, `source_config_version` payload mechanics, `tick()` as the intake-log seam. No spec changes were needed.
- Cross-scope name corroboration (parent title naming the company vouches for a body bare token) is a plan-level decision the spec leaves open; documented in Task 2 with rationale.
- The diagnostic reconstructs provenance from RETAINED text; upstream deletions blank bodies, which is exactly what `text_changed_or_absent` exists for — expected nonzero on real data.
