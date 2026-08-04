---
target: /admin/monitor
total_score: 19
p0_count: 2
p1_count: 2
timestamp: 2026-08-04T22-10-18Z
slug: templates-admin-admin-monitor-html
---
Method: dual-agent (A: design review · B: detector + browser evidence), isolated, parallel. Parent verified A's six highest-severity code claims directly against source before synthesis.

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | `page.generated` is computed but never printed — the page never says when it was measured. At `?days=14` it reports a green all-clear while 5 of 6 tasks are absent. After a successful "Jetzt" the figures are stale and the toast tells you to reload manually. |
| 2 | Match System / Real World | 3 | German copy is genuinely good. But `?days=1` renders "Für die letzten 1 Tage" from a selector labelled "24 Stunden"; "Alle 1 Tasks"; "1 Läufe". `LÄNGSTE LÜCKE` maxes over all incidents including error bursts, so a figure named "longest silence" can report the length of a failure storm. |
| 3 | User Control and Freedom | 1 | One control on the page. No task filter, sort, per-task deep link, or expand-all. Period change = full reload; every disclosure collapses, scroll lost. Toast cannot be dismissed or recalled. "Jetzt" has no cancel and no undo. |
| 4 | Consistency and Standards | 2 | Third section-header system in the admin suite; second toast system (`.mon-toast` vs the shared `.toast-wrap` used by Roster/Members/Users). `:active` declared only on `.mon-btn`. Worst: the chart legend describes an encoding the chart does not use. |
| 5 | Error Prevention | 1 | `.js-run` synchronously executes a live production task with no confirmation, no statement of what it does, no duration hint. Six of them precede the harmless details toggle in tab order. `admin_users.html` already ships a click-to-arm confirm pattern that this page does not use. |
| 6 | Recognition Rather Than Recall | 2 | Reading a lane requires holding six task→hue mappings that the legend actively contradicts. The `.corr` column has no caption. Reconciling "86 of 139" with the cause table's 94+44+1 and Zone 3's 36×/17× is manual arithmetic across three altitudes with no cross-links. |
| 7 | Flexibility and Efficiency | 2 | Row-click-to-expand is a real accelerator and works. Nothing else: no shortcuts, no filter, no copy-error, no auto-refresh, no "since last visit". Thin for a power-user admin surface. |
| 8 | Aesthetic and Minimalist Design | 3 | Restrained, flat, tonally correct, strong hierarchy in Zone 1. Costs: 80 uppercase micro-labels across five near-duplicate label styles, three mostly-empty disclosure boxes per clean task, Ursachen/Zone-3 duplication. |
| 9 | Error Recovery | 1 | The page's stated first job. There is nowhere to read a full error message: truncated at every width with no `title`, no tooltip, no expand. The one place the full text appears — the failure toast — auto-dismisses at 6s and cannot be recalled. |
| 10 | Help and Documentation | 2 | The one-line hint teaching the lane instrument is genuinely good. Nothing explains what "übersprungen" means per task, what the health thresholds are, what "Jetzt" will actually do, or why every lane is blank after 21.07. |
| **Total** | | **19/40** | **Poor — major UX work required** |

Visually this scores ~3.5 across the board. The four 1s all sit on the page's own stated jobs, which is why the total lands where it does.

## Anti-Patterns Verdict

**Does this look AI-generated? No.** This is the cleanest pass on the DESIGN.md bans in this codebase. A computed DOM scan of every element returned zero hits for side-stripe borders >1px, `background-clip:text` gradients, decorative `backdrop-filter`, card `box-shadow`, gradient backgrounds, and emoji in body text. The three violations the spec named — thick `border-left`, six identical cards, emoji as control icons — are genuinely gone.

Two texture flags rather than slop: `.mon-sec .rule` renders 783px and 860px of purely decorative hairline twice, and `.det` opens three bordered boxes for four of six tasks that contain only "Kein Fehllauf im Zeitraum" — chrome without content.

**Deterministic scan** (`detect.mjs`): exit 2, **19 findings** (1 warning, 18 advisory).

- **Genuine — `design-system-font-size` ×15** (L31, 62, 75, 88, 95, 141, 147, 171, 196, 207, 271, 282, 308). Real literals off the DESIGN.md ramp: 26px, 29px, 20px, 11.5px×4, 21px, 22px, 12px×3, 25px. Genuine drift.
- **Genuine — `design-system-radius` ×2** (L98 `.lane-track`, L135 `.lane-legend .sw`, both `2px`). Deliberate-looking but off-scale.
- **False positive — `em-dash-overuse`** ("139 em-dashes"). The file has **18** real em-dashes; the count is dominated by 138 occurrences of `--` from CSS custom properties. Of the 18, four sit in comments, eight are Jinja null placeholders, and only **four** are in body prose. Matches the known repo pattern.
- **False positive — `numbered-section-markers`** ("Sequence: 05, 10, 11, 12"). Extracted from decimal CSS values (`line-height: 1.05`, `10.5px`, `11.5px`, `12.5px`), not section labels. Zero numbered markers in the markup.

**Baseline vs `admin_users.html`:** 19 findings / 1 warning here against 25 / 3 there. This page introduces **zero** undocumented colours and **zero** undeclared fonts where the sibling has one and two. Radius drift is much lower (2 vs 7); font-size marginally higher (15 vs 13). On the categories that actually indicate system drift, the rebuild is the cleaner file.

**Visual overlays:** none. No user-visible overlay is available — both assessments used isolated python-playwright processes rather than the browser pane, so no `detect.js` injection was attempted. Fallback signal is the CLI scan plus measured DOM evidence above.

## Overall Impression

The redesign's central bet lands. "EIN FREMDSYSTEM-AUSFALL ERKLÄRT 86 DER 139 FEHLLÄUFE" hands you a causal verdict before you read a number, and pre-empts the wrong reading in the same sentence. That is the thing the old page structurally could not say, and it is said well.

Then the instrument built to prove that claim contradicts it. The lane strip spends colour on task identity and then needs the same channel for state — on the Raid Weekend lane a successful run and a failed run are the same red, differing only by alpha. The legend explains an encoding that matches exactly one of six lanes. Below that, the cause table's own arithmetic (94+44 = 138 of 139) disagrees with the headline's 86. And the register underneath reports all six tasks dead while the headline says the scheduler ran fine.

The single biggest opportunity: the page is right about the rare thing (was there a shared cause) and wrong about the common one (is anything still alive). In this very dataset the actual emergency is total silence, and the page renders it as neutral-white `0/6` beside a green verdict.

## What's Working

**The Befund headline earns its slot.** It commits to a causal claim, names the cause in one hue on one noun, and spells out the negation ("nicht 3 Probleme, sondern eine gemeinsame Ursache"). Even with the chart below it failing, this element alone delivers the redesign's premise.

**The Ursachen rollup is the right structure, and its two-colour count does silent work.** `.cause-n.solo` renders single-task causes in Recon Blue against red for multi-task ones, so systemic vs isolated reads at a glance without a word. It is the actual fix for the old page's problem and the one part of Zone 1 that survives intact at 390px.

**The disclosure is properly engineered, and the accessibility floor is solid.** Real `<button aria-expanded aria-controls>` with a unique visually-hidden label per task; `grid-template-rows: 0fr→1fr` so there is no JS height maths; `:has(.reg-toggle:focus-visible)` lifts the whole row so keyboard focus reads at row scale. Measured: 40 of 40 interactive elements have an accessible name, all six disclosures wire correctly, all six lane SVGs carry substantive `aria-label`s, 37 of 41 SVGs correctly `aria-hidden`, zero console errors, zero horizontal overflow at any width, and **69 of 70 text elements pass WCAG AA** (the one miss is 4.47:1 against 4.5). Reduced motion verified correct in both directions.

## Priority Issues

**[P0] The page reports "all clear" when tasks have disappeared entirely**
`monitor_stats.py:296` filters the registry with `if by_task.get(k)`, directly contradicting the comment three lines above it ("the page shows all six every time… so a missing one reads as missing rather than as a shorter list"). At `?days=14` this yields a green "KEINE ÜBERGREIFENDE STÖRUNG / Alle 1 Tasks liefen im Zeitraum fehlerfrei" while five of six tasks logged nothing. `0/1 IM TAKT` sits in neutral white because the `bad` class is never applied to that figure. *Verified in source by the parent.*
**Why it matters:** the daily-glance job is one of the four the page exists for. This tells the owner everything is fine at the moment the scheduler is dead.
**Fix:** iterate `TASKS` unconditionally; render a missing task as an explicit `down` row reading "keine Läufe im Zeitraum"; colour the `im Takt` figure red whenever `healthy < task_count`; lead the Befund with silence when silence is the dominant finding.
**Suggested command:** `/impeccable harden`

**[P0] The lane strip spends colour on task identity, then needs the same channel for state**
`[data-task="raid_weekend"] { --tc: var(--red) }` and the error marks are both `var(--red)`. Measured resolved fills: successful run `rgb(234,71,71)` @ 0.52 alpha, failed run `rgb(233,70,70)` @ 1.0 — the same colour, differing only by alpha, on a 17px track. A measured 2.53:1 between them. Five of six lanes paint successful runs in a colour the legend never shows; the legend's grey "Lauf" swatch matches exactly one lane.
**Why it matters:** Raid Weekend owns 54 of the 139 errors and its lane reads as one unbroken red band. The admin either panics at a healthy task or stops trusting the strip — and the more carefully they read the legend, the more wrong they get.
**Fix:** take colour off task identity *inside* the chart. One neutral for coverage, skipped differentiated by shape not alpha, errors in red, voids as an outlined hatch. Keep the mode hue on the lane's label icon, where it cannot collide. The legend then becomes true.
**Suggested command:** `/impeccable colorize`

**[P1] There is nowhere on the page to read a full error message**
`.cause-m code` and `.det-line .m code` both ellipsis with no `title`, no expand, no copy — and the page has zero `float_tooltip` hooks. Measured: the `.det-line` copy shows at most **37%** of the string, and gets *worse* as the viewport widens from 1200 to 1024 (73% → 80% cut) because the three detail columns divide the container. The one place the full text appears — the failure toast — auto-dismisses at 6000ms and cannot be recalled. Only text selection recovers it, and nothing signals that.
**Why it matters:** "investigate an incident — what broke, when, how long, **why**" is job one. The page delivers what/when/how-long and structurally withholds why.
**Fix:** make the raw message the disclosable thing — a native popover on the cause row with the full text in a wrapping mono block plus a copy button (this codebase's a11y note already prefers native Popover over `title`). Remove auto-dismiss from the error toast tone and give it a close control.
**Suggested command:** `/impeccable clarify`

**[P1] "Jetzt" fires a real production task with no confirmation, and leads the tab order six times**
`POST /admin/trigger-task` synchronously imports and calls the live task. No confirm, no description, no duration hint. All six buttons carry the accessible name "Jetzt" with no task association, and each precedes the harmless details toggle in DOM and tab order (stops 18, 20, 22, 24, 26, 28). The first thing the keyboard puts under a user's finger on this page is an unlabelled live task execution. `admin_users.html` already ships the right pattern — click-to-arm with disarm-on-Escape and a double-click guard.
**Note:** Assessment B measured "40 of 40 interactive elements have an accessible name" — not a contradiction. B asked whether a name exists; A asked whether it distinguishes. Both are right: the name is present and useless.
**Fix:** reuse the sibling's arm pattern; add `aria-label="{{ t.label }} jetzt ausführen"`; put the details toggle before the run button in DOM order.
**Suggested command:** `/impeccable harden`

**[P2] The headline's number and the headline's story come from different incidents**
`lead_incident = shared[0]` is the *most recent* upstream incident; `explained_by_shared = max(failures)` is the *largest*. Two upstream incidents exist at `?days=30` (two `.corr` columns render), so the sentence and the number can describe different events — and every cause row beneath is stamped with a third timestamp. Meanwhile the cause table's own arithmetic says 94+44 = **138 of 139**, i.e. the upstream share is 99%, not 62%. *Verified in source by the parent.*
**Why it matters:** the one claim this redesign exists to make is contradicted by the table directly beneath it, in the first three seconds.
**Fix:** derive the lead from the same selection as the number, and let the copy pluralise: "Zwei Fremdsystem-Ausfälle erklären 138 der 139 Fehlläufe."
**Suggested command:** `/impeccable clarify`

**[P2] The signature moment is a 4.8px sliver drawn equally across innocent lanes**
Both `.corr` elements measure **5.2 × 116px** — a 58-minute window on a 30-day axis, collapsed to `min-width: 2px` plus two hairlines. The 13% red fill measures **1.12:1** against the track, i.e. invisible; only the borders read. The column spans all six lanes including the three with zero errors in that window, so implicated and innocent tasks get identical emphasis — and on the Raid Weekend lane it vanishes into the red.
**Why it matters:** this is the element the whole arrangement was chosen for.
**Fix:** floor the column at 6–8px; invert the treatment (dim the non-implicated segments rather than highlighting all six); caption it with a small "3 Tasks · 58 min" tab so the instrument states its own claim.
**Suggested command:** `/impeccable bolder`

## Persona Red Flags

**Alex (impatient power user)** — Reads the Befund in one second, then hits six red STILL pills and stops trusting the page; spends 30 seconds deciding which of two contradictory statements is real, and nothing resolves it. Wants the raw 503 body for a ticket: gets `HTTP Error: 503 - {"reason":"…` with no tooltip, no copy, no widen. Wants only the failing tasks: no filter, no sort, no collapse. Switches 30d→7d to compare: full reload, every disclosure collapses, scroll lost, and lands on a dead-end empty card that recommends a longer window without giving him one. Clicks "Jetzt", sees "Fertig", then reads that numbers update *beim Neuladen* — he must reload manually to learn whether his own action worked.

**Sam (screen reader + keyboard only)** — Tab stop 18 is a button whose entire accessible name is "Jetzt". So are 20, 22, 24, 26, 28: six identical unlabelled production triggers, each *before* the correctly-named "Details zu Battle Logs" in its row. The lane strip gives him six `role="img"` summaries, but the one fact the chart exists to convey — that three lanes failed in the *same window* — lives in two `<div class="corr">` elements with no text and no ARIA (the Befund paragraph does state it in prose, so he is not locked out; the instrument itself is mute). Heading tree jumps **h2 "TASKS" → h5**, skipping two levels, yielding 18 h5s with three labels repeated six times and no task name — useless for navigating the register. **No `<main>` landmark**; both `<section>`s unnamed, so neither is exposed as a region, and "skip to content" has nothing to target. The failure toast shares the polite region with success and self-destructs after 6s, so a failure announcement can be dropped and never recovered.

**Riley (stress tester)** — `?days=1`: "Für die letzten **1 Tage**" from a selector labelled "24 Stunden". `?days=14`: "Alle **1** Tasks liefen fehlerfrei", "**1** Läufe", "0/1 im Takt" — three plural bugs wrapped in a green all-clear over a dead system. Same state: one run → `infer_cadence` returns `None` → health falls to `warn` at ≥120 min, so a task last seen **11 days ago** renders yellow "VERZÖGERT", not red — the health rule inverts under sparse data, a distinct defect from the `clan_war` threshold issue the spec deliberately deferred. **The empty state has no exit and no actions**: the copy recommends a longer window and gives no control to take one, and every "Jetzt" button disappears with the register — the state where you most need to kick a task manually is the only one where you cannot. `LÄNGSTE LÜCKE` ranges over all incidents including failure bursts, so a figure labelled "longest silence" can report an error storm. **Trailing silence is invisible**: `find_gaps` only measures run-to-run intervals, so a task that simply stopped produces no void — every lane goes blank after 21.07 unmarked, and blank is also what "outside the data" looks like. **Mobile axis is mislabelled by four days**: `nth-child(even)` on eight ticks drops the *last* one, so at 390px the axis reads "…31.07." while the window runs to 04.08.

## Minor Observations

- `.mon-btn` measures **41×79px** under `pointer: coarse` — 3px under the 44px floor `.reg-toggle` correctly reaches.
- `.mon-pill.down` text measures **4.47:1**, missing AA by 0.03. The only failure in 70 measured elements.
- The inline `laneData` JSON is **48 KiB — 33% of the document** — encoding 1,407 points as full ISO-8601 strings (~35 B/point), rendering to 1,422 SVG rects and driving a 2,134-node DOM. A compact epoch-offset encoding would cut most of it.
- `float_tooltip.js` and `render_stars.js` load on every request; neither is used by this page (`[data-tip]` count: 0).
- `<html lang="en">` on an all-German page (WCAG 3.1.1) — pre-existing convention across all 20 templates, not introduced here.
- `.reg-fig small` wraps to two lines for Clan War and CWL only, breaking the table baseline.
- `.det` boxes stretch to the tallest sibling: Clan War's 7-row gap list leaves ~350px dead space beside it.
- Between 780px and 1080px the register is already in divided-row mode with ~600px of empty row, and `max` duration is dropped — the runtime-watching job loses a dimension across a 300px band where the desktop table would have fitted.
- Zone 3 restates Zone 1's causes at per-task granularity with no link and no shared ordering.
- The toast shrink-wraps to 195px at 390px despite its `max-width`, overlaying the CWL row.
- **Not this page, but found while measuring:** the sticky stack puts `nav` and `nav.admin-tabs` at the same offset, and admin-tabs wins on DOM order. Hit-tested at `scrollY=900`, **all 9 top-nav links are unreachable** — `elementFromPoint` returns `.atab`. Reproduces identically on `admin_users.html`, so it lives in `admin/_admin_tabs.html` and affects every admin sub-page. Worth its own fix.

## Questions to Consider

1. If the lane strip's job is to prove co-occurrence, why is it six independent series at all? A single row — time on x, a stacked count of *how many tasks failed in this bucket* — states "three at once" in one glyph, and the per-task detail already lives in Zone 2.
2. The page must be right about two different things — "was there a shared cause?" and "is anything still alive?" — and spent its entire instrument on the first. What does Zone 1 look like if *silence* is the primary axis and correlation the second movement?
3. Zone 1 rolls causes up across tasks; Zone 3 splits them back down per task. If the rollup is the right altitude, why does the per-task split exist — and if it does, why is it reached by clicking the *task* rather than the *cause*?
4. "Jetzt" is the only write action on a page otherwise devoted to reading. Does it belong beside four healthy tasks, or is it a consequence of investigation — something reached after reading a cause?
5. The period selector reloads and destroys every expansion, though the payload is already bounded. What stops all four windows shipping at once and switching client-side, exactly as `/cwl`'s day-switch already does in this codebase?
