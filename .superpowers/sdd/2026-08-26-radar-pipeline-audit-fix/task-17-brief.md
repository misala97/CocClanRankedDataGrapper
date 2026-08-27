## Task 17: Correct the cost record

**Files:**
- Modify: `personal_apps/features/radar/llm_sentiment.py:1-30`

**Interfaces:**
- Consumes: nothing.
- Produces: no new names.

The module docstring estimates "about 1335 scored mentions a day" and "roughly twenty cents a day". Measured 2026-08-25: 344 calls, 798,198 input tokens, 89,281 output tokens, **$1.2446** — 5x the volume and 6x the cost.

- [ ] **Step 1: Correct the docstring**

Replace the `COST.` paragraph in `personal_apps/features/radar/llm_sentiment.py`:

```
COST. Measured, not estimated, on 2026-08-25: 344 calls, 798,198 input tokens,
89,281 output, $1.2446 for the day. The earlier figure in this docstring --
"about 1335 scored mentions a day ... roughly twenty cents" -- was 5x low on
volume and 6x low on cost, because it counted the mentions a day's BUCKETS
carry rather than the mentions the pass is handed. spec 6.11's own estimate
("order of 150k input tokens/day, cents") is wrong by the same factor.

No daily ceiling. PASS_LIMIT caps one pass at 400 and the pass runs every ten
minutes, so the theoretical maximum is 57,600 mentions a day against an
observed 6,880 -- the ceiling that matters is how many mentions ingest
produces, and a spend cap would silently stop reading tone rather than
signalling that something upstream had changed. The figure is on the board;
watch it there.
```

- [ ] **Step 2: Verify nothing else asserts the old numbers**

```bash
grep -rn "twenty cents\|1335" personal_apps/
```

Expected: no remaining hits outside the corrected docstring.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/features/radar/llm_sentiment.py
git commit -m "docs(radar): the tone pass costs six times what the docstring claimed"
```

---

# Stage 5 — Operational

