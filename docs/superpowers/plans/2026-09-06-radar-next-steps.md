# Radar — what's next, in plain language

Written 2026-09-06, from a conversation with Michi. Deliberately not
spec-speak: this is the "what are we doing and why" note, and the formal
documents live beside it.

---

## The three parts of radar

Worth being clear about, because it's easy to mix them up.

**1. Extractor** — reads a post and decides which tickers it mentions.
Pure rules: cashtags, capital letters, a stopword list, a company-name
lookup. No model involved. We know 26% of what it finds is junk. We have
**never measured what it misses entirely.**

**2. Judgment** — the encoder. Reads one post about one ticker and answers
five things at once: is it really about that company, is it a human or a
bot, and the tone (positive/negative/mixed/none) plus expected move and
confidence.

**3. Tone** — what colours a post on the board. *This is not a separate
system.* The encoder already produces it. It's switched off because tone is
the encoder's weakest field: it flips positive and negative on about 16% of
directional posts, where Haiku flipped almost none. The board still uses the
old word-list score instead.

Separately from all three: **bot accounts**, which is just deleting garbage
at the door before any of this runs.

---

## The order we agreed

1. **Judgment** — Codex review, fix what it finds, merge, deploy, run the
   trial. This is finished work sitting idle.
2. **Bot blocklist** — cannot happen during the trial (see below).
3. **Extraction** — and measure before building anything.

---

## About the trial

Original design assumed we could fall back to the paid Haiku judge. We
can't — no credits, not paying again, and radar has had **no judge at all
since 3 September**. So the choice is encoder or nothing, not encoder or
Haiku.

That killed half the trial's purpose. **Changed on 2026-09-06** (committed):
the only thing that now shuts the encoder off is *deleting real posts too
often* — it has to be right at least 93% of the time when it deletes
something. Losing to Haiku on other measures is recorded but decides
nothing, because there's no Haiku to go back to.

The Haiku comparison still has a job: deciding later whether to **expand** —
judge every post instead of the 1-in-5 the gate currently allows, and put
tone on the board. Failing that comparison means "keep going, don't expand",
not "switch off".

### The audit — do the small version

The trial was going to need **746 human-labelled rows** between day 3 and
day 7. That number came from wanting a tight confidence interval on the
deletion accuracy.

After the rule change, that's overkill. Two separate things:

- **Automatic monitoring** (deletion rate, memory, backlog) — free, runs
  itself, catches gross failure within a day. Keep it regardless.
- **Human audit** — costs Michi's time, and is the only way to know the real
  deletion accuracy on ordinary traffic. The existing 200-row audit can't
  answer it because half of it was deliberately stacked with deletion cases.

**Decision: do a small audit, roughly 150–200 random rows.** Enough to catch
"it's deleting 20% wrongly", not enough to split hairs. Maybe an hour.
What it needs to rule out is a disaster, not a rounding error.

---

## Bot accounts — found, but not settled

Measured from the four days the paid judge ran:

- Bluesky is 70% junk; Reddit is ~3%. Bluesky is essentially the whole
  problem.
- It concentrates hard: **31 accounts** post 20+ times and are junk 95%+ of
  the time. **45 accounts** cover 69% of all Bluesky junk, and 47% of
  everything the judge was deleting.
- They post things like `Random Stock Ticker: $METCI`, press-release relays,
  SEC-filing feeds, earnings bots, insider-trade feeds. Not people.

The mechanism to block them **already exists** — `is_automated_author()`
runs at ingest and drops the post. It currently contains one name
(`automoderator`) and only looks at Reddit.

**Open question, not yet answered:** are bots actually hurting the signal?

- Steady bots post about everything constantly, get absorbed into the
  baseline, and mostly cancel out.
- **Bursty** bots are the real problem — a filing bot firing 20 times on one
  company in one day looks exactly like a genuine chatter spike, and that
  does move rankings.

**Next step is a measurement, not a change:** check which of the 45 are
steady and which are bursty, and how much the top ticker rankings would
actually move without them. If the answer is "barely", drop the whole idea.

**Timing:** must not happen during the trial. Removing those accounts cuts
deletions by ~47%, and the trial's safety alarm watches exactly that number
— it would fire on our own change and look like the encoder went wrong.
Either before arming (means redoing the baseline measurement) or after the
trial. After is simpler.

---

## More training data — probably not

The curve already flattened:

| rows | relevance | deletion accuracy | tone flips |
|---|---|---|---|
| 5,000 | .703 | .860 | 21.1% |
| 9,000 | .750 | .890 | 17.7% |
| 13,000 | .711 | .880 | 16.5% |

5k→9k bought a lot. 9k→13k bought nothing, and relevance went *down*.
Another 5,000 of the same kind of rows would likely do the same.

**Where labels would help: tone, and only if we want tone on the board.**
Aimed at the known failure — long argumentative posts that criticise on the
way to a positive conclusion.

**Free training data:** whatever gets labelled for the audit is
human-labelled on real traffic, which is better than the Sonnet labels in
every way. Catch: a row can be training data or test data, never both. Fold
them in only after they've done their evaluation job.

---

## Bigger model, bigger machine

Two separate things, and I confused them once already:

- **More speed:** not needed. The encoder does 7 rows/second; demand is
  0.15. We use 2% of what we have. A 400-row pass takes under a minute out
  of every ten.
- **More RAM:** the only thing a bigger box actually buys — the ability to
  hold a **bigger model** resident. DeBERTa-small is 566 MB on disk and ~1 GB
  running; the next size up roughly triples that and will not fit in 2 GB.

Because demand is so low, several encoders could take turns on the current
box — load, run the pass, unload. Two seconds to load. So multiple models
don't automatically mean more hardware.

**Suggestive evidence a bigger model might be worth it:** the data curve
flattened. When more data stops helping, the model is often the limit.

**Test it before spending anything:** train DeBERTa-base on the same 13,000
rows on Michi's PC, score it against the same frozen test sets, compare.
About an hour of GPU, smaller batch than last time so it doesn't fill the
VRAM. If it's clearly better, the hardware spend has a number attached. If
not, money saved.

Not now. After the judgment trial.

---

## Extraction — measure first

Two halves, very different costs:

- **Precision** (junk it wrongly accepts): needs **no new labels**. The 2,669
  already-labelled `irrelevant` rows are the dataset. A chunk of it is just
  a stopword list — FCF, SMA, DTE, IP, API, ARR and friends are trading
  jargon being counted as companies. Nearly free.
- **Recall** (mentions it never finds): **never measured, at all.** Every
  number we have about extraction comes from things it accepted. Measuring
  it needs a deliberately loose extractor run over raw posts, keeping only
  what the current rules rejected, then labelling a sample.

It's entirely possible extraction stays rules-based and just gets better
rules. Don't assume it needs a model until the measurement says so.

---

## Still open from before

- **Per-ticker mute** — asked for on 24 August, still deferred. IA, ICE,
  MAGA, GOP are ~35% of the score and aren't companies.
- **More sources** — Discord, Telegram, YouTube. Telegram discovery work is
  already in the working tree.
- **German market** — still fallback-only; the Xetra entitlement never
  arrived.

---

## One process note

This conversation ran very long and got compacted, and the quality showed it
— including a rule written into the spec that contradicted something Michi
had said weeks earlier. **Start a fresh session for the Codex round.**
Everything needed is on disk: the ledger, the handoff, the runbook and the
review brief exist precisely so a new session can pick it up cold.
