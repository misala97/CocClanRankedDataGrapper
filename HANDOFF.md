# HANDOFF — Radar B1C local implementation

This worktree is the completed local B1C candidate. Read `radar-design/CLAUDE-B1C.md`,
`radar-design/B1C-IMPLEMENTATION-PLAN.md`, `radar-design/B1C-LEDGER.md`, and
`CODEX-RETURN-B1C.md` before continuing. Git and the return packet are the source
of truth if this text ever differs from an older planning note.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-b1c`
- Branch: `codex/radar-b1c`
- Starting deployed/PERF3 base: `ad531ef6d697eac7c67179a40d7fca56812095fd`
- Carried Claude commits: `020baee`, `df04fcf`
- Final integration SHA is recorded in `CODEX-RETURN-B1C.md` after the local commit.

## Outcome

The candidate now contains Claude’s B1 dark Human Chatter workspace and live gallery,
the ruled descriptive measured-price wording fix, and a B1C opt-in tone extension.
The hub requests `tone=1`, renders a retained-evidence stacked histogram, and keeps
the old `/radar/` detail/area path backward compatible. Tone bars use exact existing
chatter totals, recorded judgments only, and a 48-hour retained evidence horizon.

## Local preview

- URL: `http://127.0.0.1:5021/radar/hub/`
- Account: `b1cadmin` / `b1c-local-only`
- Database: disposable `personal_apps_radar_b1c`, protected by the explicit target
  and independent registry gates in `personal_apps/scratchpad/b1c/`.
- No production or VPS state was changed.

## Verification and review

- `npm test`: general frontend 403 passed; radar suite 737 passed across 45 files.
- `npm run build`: TypeScript, gym build, and radar build passed.
- Backend affected/API/detail gate: 128 passed; tone unit gate: 7 passed.
- Playwright visual/interaction gate: 1440/1920/390/320 screenshots; no 320px
  horizontal overflow; keyboard detail navigation and Escape verified.
- Independent review checked diff scope, protected PERF3 files, old-board compatibility,
  query joins, denominator reconciliation, tone query opt-in, and malformed API input.

## Boundary and next owner decisions

Do not deploy, push, merge main, touch the VPS, alter PERF3 owner scripts, add a capture,
promote the hub, or invent durable historical tone. Remaining product decisions are
whether to promote the hub and when HA should own persistent historical tone.
