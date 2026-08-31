# Radar extractor feedback and hygiene — design

**Status:** approved product direction; ready for an implementation plan

**Decision date:** 2026-08-31

**Depends on:** `2026-08-31-radar-sentiment-v2-final-design.md`

**Reconciles:** `2026-08-25-radar-extraction-rethink.md`

## 1. Decision

Radar continues to associate a Reddit comment with the ticker discussed by its
parent submission. A commenter does **not** have to repeat the ticker for the
comment to count as part of that conversation.

The next extractor release does two things:

1. ship deterministic hygiene whose false-positive mechanism has already been
   measured; and
2. add read-only diagnostics that use finalized sentiment-v2 judgments as
   extraction feedback after v2 has accumulated enough live data.

It does **not** yet add automatic per-ticker demotion, finance-word promotion,
aliases, or new medium-promotion thresholds. Those are candidates, not decided
behavior. Each requires the v2 relevance or content-origin evidence defined in
this document before it may change production extraction.

The central separation is binding:

- **thread context** can associate a comment with a ticker;
- **the commenter's own text** determines that commenter's attitude; and
- a username is neither thread context nor authored post text.

## 2. Product invariant: comments remain relevant

Reddit's Atom comment feed emits a synthetic title shaped like:

```text
/u/<commenter> on <parent submission title>
```

That string contains three different kinds of information and must not be
treated as one authored title:

| part | extraction use | sentiment use |
|---|---|---|
| `/u/<commenter>` | never | trusted author metadata only |
| parent submission title | ticker thread context | never as the commenter's words |
| comment body | ticker evidence and authored text | the commenter's authored text |

For a Reddit comment-shaped row, extraction therefore scans the parent title
plus the comment body after removing only the synthetic username prefix.
Sentiment preparation remains unchanged from sentiment v2: it judges the body
only and receives the already-extracted target ticker separately.

Examples:

```text
title: /u/alice on Here goes everything $SNDK
body:  How is it going now?
```

This remains an `SNDK` comment through parent-thread context. Its body may add
conversation volume without adding a directional sentiment vote.

```text
title: /u/CEO_of_SOXL on Daily Discussion Thread
body:  What movie should I watch tonight?
```

This does not create a `SOXL` mention. The only ticker-shaped text is in the
username, which is metadata rather than the communication being measured.

Generic replies are not forced bullish, bearish, relevant, or irrelevant.
Sentiment v2's existing conservative rule remains authoritative: only a final
explicit `irrelevant` or `broadcast_or_automated` judgment removes a retained
mention from human-chatter counts. Uncertain or unjudged mentions remain
provisional.

## 3. Evidence

### 3.1 Database population

The independent audit and Claude's separate read-only probe agree on the core
dev-database counts:

| source root | high | low |
|---|---:|---:|
| Bluesky | 24,946 | 2,828 |
| Reddit | 13,542 | 9 |
| 4chan | 50 | 36 |
| **total** | **38,538** | **2,873** |

The retained live span is 2026-08-21 09:18 through 2026-08-30 16:59 UTC.
Older fixture rows are less than one percent and do not change the decisions.
There are zero v2 judgments in this restore because sentiment v2 has not yet
been deployed. V1 `unclear` is a tone answer, not a relevance label, and must
not be promoted into relevance ground truth.

### 3.2 Deterministic Reddit pollution

The stored Reddit population contains:

- 133 mentions whose ticker occurs only inside the synthetic username;
- 126 mentions authored by `/u/AutoModerator`;
- 4,502 mentions associated only through the actual parent title; and
- 4,635 title-only mentions when the 133 username leaks are included.

The last two numbers overlap by definition and must never be added together.
The 4,502 parent-context mentions are not presumed false. Manual inspection
found many genuine replies to ticker discussions, so removing parent titles
would trade a narrow hygiene fix for a large recall regression.

A deterministic stored sample of Reddit body matches found 40 of 45 genuinely
referred to the extracted security. The five failures were ordinary finance or
political abbreviations: `TP`, `CIA`, `PCS`, `NATO`, and `CCI`. Across the full
restore, the related candidate collision cluster (`AG`, `CIA`, `NATO`, `TP`,
`PCS`, `CCI`, `NC`) contains 265 rows. This is evidence for a future measured
source-specific rule, not authorization to add a stoplist in this release.

### 3.3 Bluesky is primarily an origin problem

The top ten Bluesky authors account for 40.3% of all 27,774 retained Bluesky
mentions. One author produced 731 mentions from 28 posts with a 0.61 duplicate
ratio and 100% v1 `unclear`. Surviving templates include market alerts,
sentiment/confidence feeds, liquidation reports, SEC summaries, insider-trade
feeds, and bulk watchlists.

Independent manual samples reached the same conclusion:

- 36 of 40 explicit cashtag matches referred to the security, but only 4 of
  40 were clearly ordinary human conversation;
- 25 of 35 name-corroborated bare matches referred to the company, but 0 of
  35 were clearly ordinary human conversation; and
- a 180-second live slice saw 1,062 posts, correctly discarded all 35 low
  candidate mentions, and retained one automated `$MOVE` price alert.

Ticker notation is therefore not the largest Bluesky failure. Broadcast and
automation origin is. Sentiment v2's `content_origin` judgment is the correct
future label for this population.

### 3.4 Recall candidates are source-specific

Broad company-name matching is unsafe on a general network. In a raw Bluesky
slice, 434 of 1,255 unmatched posts contained a token considered distinctive
in some registered company name. The first 80 manually inspected candidates
were ordinary-language or entity collisions rather than missed equity
conversation.

Finance-native Reddit differs. One current 25-comment WSB feed contained 21
unmatched comments, including three genuine missed references: `Tesla`,
`Google`, and lowercase `spy`. This is small but direct evidence that curated
aliases or carefully scoped case-insensitive forms may recover real Reddit
conversation. It is not evidence for enabling every registered name token.

### 3.5 Medium promotion and finance context

The earlier statement that medium promotion "essentially never fires" is
wrong. Current bucket totals contain 6,749 promoted counts out of 37,579 scored
counts (17.96%), and the retained journal contains 2,257 `promoted=True`
events. The next question is promotion precision, not activation frequency.

Finance words correlate with v1 directional tone on Reddit bare matches:
mentions containing a document-level finance word had 24.8% v1 `unclear`,
versus 39.1% without one. This does **not** establish extraction relevance:
the label is v1 tone, the probe scans the whole synthetic title plus body, and
the word need not be near the ticker. Finance-context corroboration remains an
untested extraction hypothesis.

## 4. Canonical extraction input

Add one source-aware preparation function used by live ingest, measurement,
and tests. Its conceptual result is:

```text
ExtractionInput(
    author_text,
    thread_context,
    source,
    author,
    channel,
    is_comment,
)
```

Rules, in order:

1. Convert null title and body to empty strings.
2. Use `config.source_root(source)` so every `reddit:<subreddit>` source gets
   the same policy.
3. A Reddit row is comment-shaped when its cleaned title starts `/u/` and
   contains the literal delimiter ` on `.
4. For a comment-shaped row, split the title once at the first ` on `.
   Discard the left username portion from extraction text. Store the right
   portion as `thread_context`; store the body as `author_text`.
5. For every other row, title and body are authored text and
   `thread_context` is empty.
6. Extraction scans `author_text` plus `thread_context` while keeping the two
   scopes distinguishable for diagnostics.
7. Sentiment input does not consume `thread_context`. Its existing canonical
   body-only Reddit comment behavior remains unchanged.

Do not implement this with a global regex that removes `/u/...` from arbitrary
text. Only the leading synthetic Reddit title shape is structural. A normal
post mentioning a Reddit user is authored content and must stay intact.

## 5. Immediate hygiene behavior

### 5.1 Username exclusion

No ticker candidate may originate solely from the discarded username portion
of a synthetic Reddit comment title.

If the same ticker also appears in the parent title or comment body, the
mention remains and its surviving occurrence determines its extraction form.
This prevents the username fix from deleting a genuine ticker-thread comment.

### 5.2 AutoModerator exclusion

Reddit posts whose normalized author is AutoModerator are not human chatter
and are dropped before extraction. Normalize only for this exact comparison:
trim whitespace, compare case-insensitively, and accept the upstream forms
`AutoModerator`, `u/AutoModerator`, and `/u/AutoModerator`.

Do not use substring matching. An ordinary user such as
`/u/AutoModeratorFan` is not AutoModerator.

This is prospective extraction behavior. Do not rewrite historical judgment
provenance or invent an LLM answer for existing rows. Existing board-window
rows age out normally or are excluded by the sentiment-v2 backfill when it
produces a valid `broadcast_or_automated` judgment.

### 5.3 Versioning

The canonical extraction-input version, automated-author rule, and a monotonic
`EXTRACTION_POLICY_GENERATION` participate in `source_config_version()`.
Shipping either change increments the generation and starts a fresh baseline
population rather than mixing the old and new Reddit populations.

The version payload must contain stable policy data or explicit version
constants, not an incidental function hash whose value changes on comments or
formatting. A rollback increments the policy generation again; it must not
restore an older stamp and mix post-rollback observations into the original
pre-release baseline.

## 6. Extraction provenance for diagnostics

The extractor's internal result must expose enough provenance for its live
caller and read-only diagnostic to agree without duplicating regular
expressions. A match has at least:

- ticker;
- resulting confidence;
- strongest notation/reason:
  `explicit_cashtag | bare_named | bare_source_high | bare_low`;
- whether it appeared in authored text;
- whether it appeared in thread context.

When one ticker has several occurrences, existing extraction semantics remain
unchanged: the strongest confidence wins. Provenance retains both scope flags,
so a body mention is not hidden merely because the parent also cashtags it.

This release does not require a new database column. The diagnostic may
reconstruct provenance over retained text by calling the same pure extraction
function. If the ticker is no longer present because an upstream edit or
deletion refreshed the stored text, classify it as `text_changed_or_absent`.
Do not call that a company-name match: the current extractor cannot extract a
ticker from a company name alone.

## 7. Sentiment-v2 extraction diagnostic

Add a read-only operator script for finalized v2 judgments. It makes no model
calls and performs no inserts, updates, deletes, bucket rebuilds, configuration
changes, or artifact promotions.

### 7.1 Readiness

The script always prints population and coverage, but it marks recommendations
as **not actionable** until both conditions hold:

1. v2 has covered at least seven consecutive live days; and
2. the relevant comparison slice has at least 50 finalized judgments.

The report states model and prompt versions. Results from different semantic
prompt versions are separate by default; combining them requires an explicit
flag and is visibly labeled.

### 7.2 Required strata

Report counts and rates by:

- source root and concrete source;
- ticker;
- extraction reason;
- authored-text versus thread-context occurrence;
- confidence;
- final model and prompt version; and
- primary-only versus reviewed final result where history permits.

For each slice, report separate rates for:

- `relevant`, `irrelevant`, and relevance `uncertain`;
- `human_chatter`, `broadcast_or_automated`, and origin `uncertain`;
- attitude classes;
- judgment confidence; and
- missing/unjudged rows.

Never combine `irrelevant` with `uncertain`, or
`broadcast_or_automated` with origin `uncertain`. Only explicit final answers
support exclusion.

### 7.3 Per-ticker feedback

Rank ticker/source/form slices by irrelevant share and broadcast share. Show
raw numerator and denominator and a 95% Wilson interval so a tiny ticker cannot
outrank a measured one on one bad answer.

This report is diagnostic only. It does not demote or mute a ticker. Any later
automatic demotion requires a new approved design and must, at minimum:

- scope a learned decision by source and extraction form;
- protect explicit cashtags from a bare-token failure rate;
- use a minimum sample and conservative interval rather than a raw percentage;
- expire or re-evaluate decisions;
- retain a small exploration path so a demoted ticker can recover;
- bump extraction/source configuration version; and
- provide an immediate rollback.

### 7.4 Bluesky origin feedback

The report also ranks authors and stable template fingerprints by finalized
content origin. It shows post count, mention count, duplicate ratio, and origin
distribution. It proposes no automatic author block in this release.

A future pre-LLM suppression rule must be conservative enough that one human
judgment prevents silent permanent blocking, and it must expire or preserve an
exploration sample. Static DIDs alone are not a durable classifier.

## 8. Measurement protocols for deferred candidates

These protocols may be implemented as read-only/offline scripts in the plan.
They do not change live extraction.

### 8.1 Finance-context corroboration

Measure finance context in the canonical authored text, separately from thread
context. Record whether a finance term occurs within a fixed local window
around the target occurrence; do not treat a word anywhere in a long parent
title or post as local corroboration.

Compare v2 relevance and human-origin precision for:

- bare mentions with local finance context;
- bare mentions with only document-level context; and
- bare mentions without finance context.

Report by source. Reddit's existing `bare_source_high` policy means a positive
Reddit result does not automatically justify promoting Bluesky bare tokens.

### 8.2 Aliases and case-insensitive names

Capture unmatched raw Reddit comments for at least one complete day, with two
days preferred when the feed budget permits. Build a blind reference sample
before evaluating aliases.

Candidate aliases are explicit per-ticker entries, source-scoped, and matched
on word boundaries. They may include brands or common issuer names such as
`Tesla` and `Google`; they are not generated from every "distinctive" universe
token. Ambiguous share classes require one explicit primary-security mapping
rather than duplicating one comment across every class.

No alias ships unless its measured relevance precision is at least 95% and
its human-chatter precision is at least 90% on fresh data. Report incremental
relevant mentions per day so a technically precise rule with negligible yield
is visible as such.

### 8.3 Medium-promotion precision

Sample at least 100 currently promoted events across every source that
contributes them. Because low-only post text is not durably stored, capture the
raw text at measurement time rather than pretending the retained mention table
is complete.

Grade relevance and human origin blind to the promotion result. Report
precision by source and compare promoted events with an unpromoted-low control
sample. The current thresholds do not change merely because promotion volume
is larger than previously believed.

## 9. Explicitly separate manual mute

A per-ticker board mute is a useful reversible user control, but it is not an
extraction verdict and is outside this implementation plan. It may hide a
ticker without claiming that its underlying mentions are irrelevant.

If implemented later, it gets its own small design covering persistence,
scope, UI, API behavior, and rollback. It must not overwrite extraction
confidence, v2 judgments, journal eligibility, or diagnostic evidence.

## 10. Deployment and rollback

Deploy in this order:

1. canonical extraction input and provenance;
2. Reddit username and AutoModerator hygiene;
3. the source-configuration version bump;
4. focused extraction regressions;
5. the read-only v2 diagnostic;
6. optional offline measurement commands for deferred candidates.

The hygiene release is independently deployable before v2. The diagnostic is
also safe before v2, but must report zero coverage and no actionable ranking
instead of falling back to v1 labels.

Rollback restores the previous extraction-input policy and automated-author
rule while advancing `EXTRACTION_POLICY_GENERATION`. It does not delete
judgments or rewrite history. The new generation starts another baseline
warm-up rather than relabeling post-rollback rows as the original population.

Operational reporting must show mention intake by source and extraction reason
before and after deployment. A Reddit drop corresponding to username-only and
AutoModerator rows is expected. Losing parent-context comments is a rollback
condition.

## 11. Required tests

### 11.1 Canonical input and Reddit behavior

- a ticker found only in `/u/CEO_of_SOXL` is not extracted;
- a ticker in the parent title is still extracted when the body omits it;
- cashtag and bare parent-title matches both remain supported;
- a body ticker remains extracted;
- a ticker in both username and parent/body survives from the non-username
  occurrence;
- splitting occurs only once, so ` on ` inside the parent title is preserved;
- malformed or non-comment Reddit titles are treated as authored titles;
- a non-Reddit authored `/u/... on ...` string is never stripped;
- empty comment bodies may still inherit ticker thread context;
- sentiment preparation remains body-only for Reddit comments;
- a generic parent-context reply produces no forced directional attitude.

### 11.2 Automated author

- all three exact AutoModerator spellings are excluded case-insensitively;
- `/u/AutoModeratorFan` is retained;
- the rule applies to Reddit source roots, not an unrelated author's display
  name on another source.

### 11.3 Versioning and diagnostics

- the extraction policy changes `source_config_version`;
- diagnostic provenance uses the production extraction helper rather than a
  second regex implementation;
- `text_changed_or_absent` is distinct from every extraction reason;
- zero v2 judgments produces a non-actionable report without error;
- uncertainty is never counted as irrelevance or broadcast;
- source, form, scope, model, and prompt strata remain separate;
- Wilson intervals and minimum samples are reproducible;
- running the diagnostic leaves every tracked table unchanged;
- no diagnostic code path mutates confidence, journal eligibility, buckets,
  configuration, or active artifacts.

Tests whose success is an absence must demonstrate teeth against the broken
variant first. In particular, the username-only and AutoModerator tests must
fail on the pre-fix implementation before they are accepted as regressions.

## 12. Acceptance criteria

The immediate release is accepted when:

1. all focused and full backend suites pass;
2. existing parent-context comment fixtures retain their ticker;
3. username-only and AutoModerator fixtures produce no mention;
4. sentiment input and the binding v2 prompt/schema hashes are unchanged;
5. the source configuration version changes intentionally;
6. no unrelated source's extraction behavior changes; and
7. a dry-run diagnostic against the current restore reports zero v2 coverage
   and makes no recommendation.

After v2 deployment, the evidence phase is accepted when:

1. at least seven consecutive days of final judgments exist;
2. the diagnostic reproduces totals from stored final fields and judgment
   history;
3. source/form/scope slices reconcile to the reported population;
4. the report identifies broadcast concentration and ticker relevance without
   using v1 `unclear` as truth; and
5. no live behavior changes as a side effect of producing the report.

## 13. Non-goals

- No removal of genuine comments merely because the commenter omits the
  ticker.
- No parent submission title passed as the commenter's sentiment text.
- No model call whose only job is ticker adjudication.
- No v1 `unclear`-share demotion.
- No automatic per-ticker or per-author suppression in this release.
- No finance-context confidence promotion before the v2 measurement.
- No broad company-name or universe-token extraction.
- No alias table in live extraction before its locked measurement passes.
- No medium threshold change before a blind precision audit.
- No per-ticker board mute in this implementation plan.
- No reinterpretation or deletion of historical judgment provenance.

## 14. Definition of done

This design is complete when deterministic Reddit metadata pollution is
stopped without losing parent-thread comments, extraction provenance has one
shared implementation, and a read-only v2 diagnostic can measure relevance and
human origin without mutating production state.

The broader extractor redesign is **not** complete at that point. It proceeds
only through separately approved, evidence-backed decisions produced by the
diagnostic and measurement protocols above.
