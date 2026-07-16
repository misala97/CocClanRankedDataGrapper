# coc_stats Dashboard (index.html) Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `templates/index.html` (the clan dashboard) as two equal, full-width stacked bands — a personal "You" band and a clan-wide "Clan" band — replacing the old two-column hero, per `docs/superpowers/specs/2026-07-16-coc-stats-dashboard-redesign-design.md`.

**Architecture:** Everything lives in the existing `templates/index.html` (its own `<style>` block continuing `_head.html`'s open tag, exactly like today) plus three new read-only queries in `app.py`'s `index()` view. No new files, no shared-shell changes — the spec's "Ops Evolved" direction refines the page within the already-established `--ops-*` tokens from `_head.html`, it doesn't touch them. Command Deck and the footer are explicitly untouched (they already use the same tokens and need no changes for this spec).

**Tech Stack:** Flask + Jinja2, vanilla CSS (no build step), the existing `--ops-*` custom properties from `_head.html`, Google Fonts already loaded there (Big Shoulders Display / JetBrains Mono / Manrope).

## Global Constraints

- **No automated test suite exists in this repo** (confirmed: no `pytest`, no `conftest.py`, no test files anywhere under `coc_stats/`). This plan does not introduce one. Every verification step is a manual check against the running dev server: `cd coc_stats && python app.py` (boots on `http://127.0.0.1:5000`), then exercise the page in a browser.
- **JS element IDs that must not be renamed:** `pog-shiny-d`, `pog-shiny-m`, `pog-glowy-d`, `pog-glowy-m`, `pog-starry-d`, `pog-starry-m` (targeted by `/static/js/ore_gain.js`'s `OreGain.init`/`applyStarBonus`/`applyWarStats`/`applyCwlStats`, called from the `<script>` block at the bottom of `index.html`). The ore strip markup and that bottom `<script>` block are carried over unchanged.
- **Out of scope, do not touch:** `templates/_head.html`, `templates/_nav.html`, the Command Deck section (`#features` / `.ops-tile-grid`), and the footer (`.ops-footer`). None of these need changes for this spec — the theme they already carry is what "Ops Evolved" refines, and Command Deck/footer markup and CSS are left exactly as-is.
- **Mobile viewport for manual checks:** 390×844 (iPhone 16e), not 375×812. Also check 760px (tablet) and 1200px (desktop) — all three were validated together in the brainstorming mockup and must reflow via the same CSS rules, not device-specific overrides.
- **`CLAN_TAG`** (module-level constant in `app.py`, already imported by `index()`) identifies our clan when a war/CWL war record could have either clan on `clan_tag` or `opp_tag`/`opponent_tag`.

---

## File Structure

**Modified:**
- `coc_stats/app.py` — `index()` view (currently `app.py:146-312`) gains three new queries (`last_war`, `last_raid`, `last_cwl_war`) and passes them to the template.
- `coc_stats/templates/index.html` — the page-specific `<style>` block (lines 5-223) and the hero section markup (lines 230-448, `<!-- Ops Hero -->` through its closing `</section>`) are replaced. Everything else in the file (the `<!-- Command Deck -->` section, the `<!-- Footer -->`, and the bottom `<script>` block) is untouched.

---

### Task 1: Last-completed-event backend queries

**Files:**
- Modify: `coc_stats/app.py:226-227` (insert after the `active_raid_est_medals` block, before the `# ── Player-specific hero data` comment)
- Modify: `coc_stats/app.py:287-312` (the `render_template(...)` call — add 3 new kwargs)

**Interfaces:**
- Produces: `last_war` (`ClanWar` instance or `None`), `last_raid` (`RaidWeekend` instance or `None`), `last_cwl_war` (`CWLWar` instance or `None`) — passed into the `index.html` template context. Task 2 consumes these exact names.
- Consumes: `active_war`, `active_raid`, `active_cwl_season` (already computed earlier in the same function, `app.py:179-189`), `CLAN_TAG` (module constant), `db` (from `from extensions import db`, already imported at the top of `app.py`).

- [ ] **Step 1: Add the three queries**

In `coc_stats/app.py`, find this existing block (around line 202-226):

```python
    active_raid_est_medals = None
    if active_raid:
        from services.helpers import raid_district_medal_value
        destroyed = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == active_raid.id,
                    RaidWeekendLog.percentage_total >= 100)
            .with_entities(RaidWeekendLog.defender_tag, RaidWeekendLog.district_name, RaidWeekendLog.district_level)
            .distinct()
            .all()
        )
        total_medals  = sum(raid_district_medal_value(r.district_name, r.district_level) for r in destroyed)
        total_attacks = RaidWeekendLog.query.filter_by(raid_weekend_id=active_raid.id).count()
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensive_reward > 0)
            .order_by(RaidWeekend.start_time.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensive_reward)
            .all()
        )
        avg_def = round(sum(r.defensive_reward for r in past_def) / len(past_def)) if past_def else 0
        if total_medals > 0 and total_attacks > 0:
            baseline = total_medals / total_attacks
            active_raid_est_medals = max(0, min(round(baseline * 6), 1620)) + avg_def
```

Immediately after this block, and before the `# ── Player-specific hero data ────` comment, insert:

```python
    last_war = None
    if not active_war:
        last_war = ClanWar.query.filter(
            ClanWar.state == 'warEnded'
        ).order_by(ClanWar.start_time.desc()).first()

    last_raid = None
    if not active_raid:
        last_raid = RaidWeekend.query.filter(
            RaidWeekend.state == 'ended'
        ).order_by(RaidWeekend.start_time.desc()).first()

    last_cwl_war = None
    if not active_cwl_season:
        last_cwl_war = CWLWar.query.filter(
            CWLWar.state == 'warEnded',
            db.or_(CWLWar.clan_tag == CLAN_TAG, CWLWar.opp_tag == CLAN_TAG)
        ).order_by(CWLWar.id.desc()).first()
```

- [ ] **Step 2: Pass the new variables to the template**

In the same function, find the `render_template(...)` call:

```python
    return render_template(
        'index.html',
        clan_name=clan_name,
        clan_badge_url=clan_badge_url,
        total_members=total_members,
        battle_logs_this_week=battle_logs_this_week,
        ranked_battles_this_week=ranked_battles_this_week,
        week_start_name=week_start_name,
        active_war=active_war,
        active_raid=active_raid,
        active_raid_est_medals=active_raid_est_medals,
        active_cwl_season=active_cwl_season,
        active_cwl_war=active_cwl_war,
        cwl_win_status=cwl_win_status,
        CLAN_TAG=CLAN_TAG,
```

Add three lines right after `cwl_win_status=cwl_win_status,`:

```python
        cwl_win_status=cwl_win_status,
        last_war=last_war,
        last_raid=last_raid,
        last_cwl_war=last_cwl_war,
        CLAN_TAG=CLAN_TAG,
```

- [ ] **Step 3: Verify the queries manually**

Run:

```bash
cd coc_stats && python -c "
from app import app
from models import ClanWar, RaidWeekend, CWLWar
with app.app_context():
    lw = ClanWar.query.filter(ClanWar.state == 'warEnded').order_by(ClanWar.start_time.desc()).first()
    lr = RaidWeekend.query.filter(RaidWeekend.state == 'ended').order_by(RaidWeekend.start_time.desc()).first()
    lc = CWLWar.query.filter(CWLWar.state == 'warEnded').order_by(CWLWar.id.desc()).first()
    print('last_war:', lw.clan_name if lw else None, lw.clan_stars if lw else None, '-', lw.opponent_stars if lw else None, lw.end_time if lw else None)
    print('last_raid medals:', ((lr.offensive_reward or 0) + (lr.defensive_reward or 0)) if lr else None)
    print('last_cwl_war:', lc.clan_name if lc else None, lc.clan_stars if lc else None, '-', lc.opp_stars if lc else None)
"
```

Expected: no traceback, and each line prints either real data or `None` (both are valid — `None` just means this clan has no completed record of that type yet, which Task 2's template guards handle). This requires the same local `.env`/DB connectivity that running `python app.py` already needs.

Then boot the full app and confirm the route itself still works (the template doesn't reference these new variables yet, so this just proves the view function has no runtime error):

Run: `cd coc_stats && python app.py`
Expected: server boots with no traceback; visiting `http://127.0.0.1:5000/` in a browser still renders the current (unchanged) page.

- [ ] **Step 4: Commit**

```bash
git add coc_stats/app.py
git commit -m "feat(dashboard): add last-completed war/raid/CWL queries"
```

---

### Task 2: Rewrite the hero section — You band + Clan band

**Files:**
- Modify: `coc_stats/templates/index.html:5-223` (the page-specific `<style>` content)
- Modify: `coc_stats/templates/index.html:230-448` (the `<!-- Ops Hero -->` section)

**Interfaces:**
- Consumes: `last_war`, `last_raid`, `last_cwl_war` (Task 1); all pre-existing `index()` context variables (`clan_name`, `total_members`, `battle_logs_this_week`, `ranked_battles_this_week`, `week_start_name`, `active_war`, `active_raid`, `active_raid_est_medals`, `active_cwl_season`, `active_cwl_war`, `cwl_win_status`, `CLAN_TAG`, `player_ranked_left`, `player_th`, `player_league`, `player_ore`, `player_attacks_this_week`, `player_war_stats`, `player_cwl_stats`, and the sitewide `current_user` from `inject_auth`).
- Produces: nothing consumed by later tasks (Command Deck/footer are untouched and don't reference anything new here).

- [ ] **Step 1: Replace the page-specific `<style>` content**

In `coc_stats/templates/index.html`, replace **lines 5-223** (everything between `{% include '_head.html' %}` and the closing `</style>` tag) with:

```css
    html { scroll-behavior: smooth; }

    /* ── OPS HERO ── */
    .ops-hero {
        background: var(--ops-bg);
        padding: 48px 32px 44px;
        position: relative;
        overflow: hidden;
    }
    .ops-hero::before {
        content: ''; position: absolute; inset: 0; pointer-events: none;
        background:
            linear-gradient(180deg, rgba(217,164,65,.05) 0%, transparent 40%),
            radial-gradient(ellipse 50% 60% at 100% 0%, rgba(144,102,232,.06) 0%, transparent 65%);
    }
    .ops-hero-stack {
        max-width: 1400px; margin: 0 auto; position: relative; z-index: 1;
        display: flex; flex-direction: column; gap: 36px;
    }

    /* ── YOU BAND ── */
    .you-identity { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }
    .you-name {
        font-family: 'Big Shoulders Display', sans-serif; font-weight: 800; font-size: 24px;
        letter-spacing: .3px; text-transform: uppercase; color: var(--ops-ink);
    }
    .you-th-badge {
        font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: var(--ops-gold);
        background: var(--ops-surface); border: 1px solid var(--ops-line); border-radius: 5px; padding: 3px 9px;
    }
    .you-league { font-family: 'Manrope', sans-serif; font-size: 13px; color: var(--ops-ink-dim); }

    .you-chip-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 18px; }
    .you-chip {
        background: var(--ops-surface); border: 1px solid var(--ops-line); border-radius: 8px;
        padding: 11px 14px; text-decoration: none; display: block; transition: border-color .15s;
    }
    .you-chip:hover { border-color: var(--tick, var(--ops-ink-dim)); }
    .you-chip .k {
        font-family: 'Manrope', sans-serif; font-size: 10px; text-transform: uppercase;
        letter-spacing: .5px; color: var(--ops-ink-dim); margin-bottom: 5px;
    }
    .you-chip .v { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 18px; }

    .you-guest {
        font-family: 'Manrope', sans-serif; font-size: 13.5px; color: var(--ops-ink-dim);
        padding: 14px 0;
    }
    .you-guest a { color: var(--ops-gold); font-weight: 600; }

    /* ore strip */
    .ops-ore-strip {
        display: flex; border: 1px solid var(--ops-line); border-radius: 8px;
        overflow: hidden; text-decoration: none; max-width: 420px;
        transition: border-color .15s;
    }
    .ops-ore-strip:hover { border-color: rgba(217,164,65,.4); }
    .ops-ore-cell { flex: 1; padding: 12px 10px; text-align: center; border-right: 1px solid var(--ops-line); }
    .ops-ore-cell:last-child { border-right: none; }
    .ops-ore-icon { width: 15px; height: 15px; object-fit: contain; margin-bottom: 6px; }
    .ops-ore-val { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 15px; line-height: 1; }
    .ops-ore-sub { font-family: 'Manrope', sans-serif; font-size: 10px; color: var(--ops-ink-dim); margin-top: 5px; }

    /* ── CLAN BAND ── */
    .ops-status-lbl {
        font-family: 'Manrope', sans-serif; font-size: 10px; font-weight: 700;
        letter-spacing: 1.6px; text-transform: uppercase; color: var(--ops-ink-dim);
        margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
    }
    .ops-status-lbl::after { content: ''; flex: 1; height: 1px; background: var(--ops-line); }

    .clan-ticket-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 18px; }

    .clan-empty {
        background: var(--ops-surface); border: 1px solid var(--ops-line); border-radius: 8px;
        padding: 16px 20px; text-align: center; font-family: 'Manrope', sans-serif;
        font-size: 13px; color: var(--ops-ink-dim); margin-bottom: 18px;
    }
    .clan-empty a { color: var(--ops-gold); font-weight: 600; }

    .ops-ticket {
        background: var(--ops-surface); border: 1px solid var(--ops-line);
        border-left: 3px solid var(--mode); border-radius: 8px;
        padding: 16px 18px; text-decoration: none; display: block;
        transition: border-color .15s, transform .15s;
    }
    .ops-ticket:hover { transform: translateX(2px); }
    .ops-ticket.idle-result { border-left-color: var(--ops-ink-dim); }
    .ops-ticket.idle-result .ops-ticket-state { background: transparent; border-color: var(--ops-line); color: var(--ops-ink-dim); }
    .ops-ticket-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .ops-ticket-mode {
        font-family: 'Manrope', sans-serif; font-size: 10.5px; font-weight: 700;
        letter-spacing: 1.3px; text-transform: uppercase; color: var(--mode);
        display: flex; align-items: center; gap: 7px;
    }
    .ops-live-dot {
        width: 6px; height: 6px; border-radius: 50%; background: var(--mode); flex-shrink: 0;
    }
    @media (prefers-reduced-motion: no-preference) {
        .ops-live-dot.on { animation: ops-pulse 1.8s ease-in-out infinite; }
    }
    @keyframes ops-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
    .ops-ticket-state {
        font-family: 'Manrope', sans-serif; font-size: 10px; font-weight: 700;
        padding: 2px 9px; border-radius: 3px; text-transform: uppercase; letter-spacing: .4px;
        background: color-mix(in srgb, var(--mode) 14%, transparent);
        color: var(--mode); border: 1px solid color-mix(in srgb, var(--mode) 32%, transparent);
    }
    .ops-score-row { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 4px; }
    .ops-score-side { text-align: center; flex: 1; }
    .ops-score-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 30px; line-height: 1; }
    .ops-score-atk { font-family: 'Manrope', sans-serif; font-size: 10.5px; color: var(--ops-ink-dim); margin-top: 3px; }
    .ops-score-lbl { font-family: 'Manrope', sans-serif; font-size: 11px; color: var(--ops-ink-dim); margin-top: 2px; }
    .ops-score-sep { font-family: 'Manrope', sans-serif; font-size: 11px; font-weight: 700; color: var(--ops-ink-dim); }
    .ops-win-txt  { color: var(--ops-win) !important; }
    .ops-loss-txt { color: var(--ops-raid) !important; }
    .ops-idle-msg { text-align: center; padding: 10px 0 14px; color: var(--ops-ink-dim); font-family: 'Manrope', sans-serif; font-size: 12.5px; }
    .ops-big-stat { text-align: center; margin-bottom: 4px; }
    .ops-big-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 32px; color: var(--mode); line-height: 1; }
    .ops-big-lbl { font-family: 'Manrope', sans-serif; font-size: 11px; color: var(--ops-ink-dim); margin-top: 4px; }
    .ops-ticket-meta {
        display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
        font-family: 'Manrope', sans-serif; font-size: 11.5px; color: var(--ops-ink-dim);
        margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--ops-line);
    }
    .ops-ticket-meta strong { color: var(--ops-ink); font-weight: 600; }
    .ops-goto { font-weight: 700; text-transform: uppercase; font-size: 10px; letter-spacing: .5px; color: var(--ops-ink-dim); }
    .ops-ticket:hover .ops-goto { color: var(--mode); }

    /* pulse strip (always shown, not just when idle) */
    .ops-pulse { background: var(--ops-surface); border: 1px solid var(--ops-line); border-radius: 8px; padding: 22px 18px; }
    .ops-pulse-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); }
    .ops-pulse-item { text-align: center; padding: 0 8px; border-left: 1px solid var(--ops-line); text-decoration: none; }
    .ops-pulse-item:first-child { border-left: none; }
    .ops-pulse-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 26px; color: var(--ops-ink); }
    .ops-pulse-lbl { font-family: 'Manrope', sans-serif; font-size: 10.5px; color: var(--ops-ink-dim); margin-top: 8px; line-height: 1.4; }

    /* ── COMMAND DECK (features) ── */
    .ops-board { padding: 68px 32px; border-top: 1px solid var(--ops-line); background: var(--ops-bg); }
    .ops-board-head { max-width: 1400px; margin: 0 auto 40px; }
    .ops-board-eyebrow {
        font-family: 'Manrope', sans-serif; font-weight: 700; font-size: 11px;
        letter-spacing: 1.6px; text-transform: uppercase; color: var(--ops-gold); margin-bottom: 10px;
    }
    .ops-board-head h2 {
        font-family: 'Big Shoulders Display', sans-serif; font-weight: 800; text-transform: uppercase;
        font-size: clamp(26px, 3vw, 34px); letter-spacing: .5px; color: var(--ops-ink); margin-bottom: 8px;
    }
    .ops-board-head p { font-family: 'Manrope', sans-serif; font-size: 14px; color: var(--ops-ink-dim); }

    .ops-tile-grid { max-width: 1400px; margin: 0 auto; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .ops-tile {
        background: var(--ops-surface); border: 1px solid var(--ops-line); border-left: 3px solid var(--mode, var(--ops-line));
        border-radius: 8px; padding: 22px 24px; display: block; text-decoration: none;
        transition: border-color .15s, transform .15s, background .15s;
    }
    .ops-tile.active:hover { transform: translateY(-2px); background: var(--ops-surface-2); }
    .ops-tile.disabled { opacity: .4; cursor: not-allowed; }
    .ops-tile-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
    .ops-tile-icon {
        width: 40px; height: 40px; border-radius: 8px; background: var(--ops-surface-2);
        border: 1px solid var(--ops-line); display: flex; align-items: center; justify-content: center; font-size: 19px;
        position: relative;
    }
    .ops-tile-icon img { width: 21px; height: 21px; object-fit: contain; }
    .ops-tile-tag {
        font-family: 'Manrope', sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 1px;
        text-transform: uppercase; color: var(--mode, var(--ops-ink-dim)); padding-top: 3px;
    }
    .ops-tile h3 { font-family: 'Big Shoulders Display', sans-serif; font-weight: 700; font-size: 19px; color: var(--ops-ink); margin-bottom: 7px; }
    .ops-tile p { font-family: 'Manrope', sans-serif; font-size: 12.5px; color: var(--ops-ink-dim); line-height: 1.6; }
    .ops-tile-alert {
        position: absolute; top: -6px; right: -6px; min-width: 16px; height: 16px; padding: 0 4px;
        border-radius: 8px; background: var(--ops-raid); color: #fff; font-size: 10px; font-weight: 700;
        font-family: 'JetBrains Mono', monospace; line-height: 16px; text-align: center;
    }

    /* ── FOOTER ── */
    .ops-footer { background: var(--ops-surface); border-top: 1px solid var(--ops-line); padding: 40px 32px 24px; }
    .ops-footer-inner { max-width: 1400px; margin: 0 auto; }
    .ops-footer-top { display: flex; justify-content: space-between; gap: 40px; flex-wrap: wrap; padding-bottom: 26px; border-bottom: 1px solid var(--ops-line); }
    .ops-footer-brand h4 { font-family: 'Big Shoulders Display', sans-serif; font-weight: 800; font-size: 18px; letter-spacing: .4px; color: var(--ops-ink); margin-bottom: 8px; text-transform: uppercase; }
    .ops-footer-brand p { font-family: 'Manrope', sans-serif; font-size: 13px; color: var(--ops-ink-dim); line-height: 1.6; max-width: 420px; }
    .ops-status-dot { display: inline-flex; align-items: center; gap: 7px; font-family: 'Manrope', sans-serif; font-size: 12.5px; color: var(--ops-ink-dim); margin-top: 14px; }
    .ops-status-dot::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--ops-win); box-shadow: 0 0 6px rgba(62,192,106,.55); flex-shrink: 0; }
    .ops-footer-links { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
    .ops-footer-links a { font-family: 'Manrope', sans-serif; font-size: 12.5px; font-weight: 600; color: var(--ops-ink-dim); transition: color .15s; }
    .ops-footer-links a:hover { color: var(--ops-ink); }
    .ops-footer-stats { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--ops-ink-dim); text-align: right; margin-top: 8px; line-height: 1.8; }
    .ops-footer-bottom { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; padding-top: 18px; font-family: 'Manrope', sans-serif; font-size: 11.5px; color: var(--ops-ink-dim); }

    /* ── FOCUS / RESPONSIVE ── */
    .ops-hero a:focus-visible, .ops-tile:focus-visible, .ops-ticket:focus-visible, .ops-ore-strip:focus-visible {
        outline: 2px solid var(--ops-gold); outline-offset: 2px; border-radius: 6px;
    }
    @media (max-width: 1100px) {
        .ops-tile-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 900px) {
        .ops-hero { padding: 40px 20px 36px; }
        .ops-board { padding: 52px 20px; }
        .ops-footer { padding: 32px 20px 20px; }
    }
    @media (max-width: 640px) {
        .ops-tile-grid { grid-template-columns: 1fr; }
        .ops-footer-top { flex-direction: column; }
        .ops-footer-links { align-items: flex-start; }
        .ops-footer-stats { text-align: left; }
    }
```

Note what changed from the old block: the two-column `.ops-hero-grid` became the single-column flex `.ops-hero-stack`; `.ops-badge-row`/`.hex-badge`/`.ops-eyebrow` (duplicate clan badge — already shown in `_nav.html`) and `.ops-h1`/`.ops-rank`/`.ops-lede`/`.ops-stat-list`/`.ops-stat-row`/`.ops-stat-num`/`.ops-stat-lbl` (old headline + link-row stats) are gone, replaced by `.you-identity`/`.you-chip-row`/`.you-chip`/`.you-guest`; new `.clan-ticket-grid`/`.clan-empty`/`.idle-result` support the always-graded ticket row; `.ops-pulse-row` changed from `display:flex` to a fluid grid; the old `@media (max-width:900px)` override that reset `.ops-hero-grid` to `1fr` is gone since the stack is single-column at every width already (nothing to override). `.ops-fd`/`.ops-mono` (unused utility classes — grep confirms nothing in the file ever applied them) are also dropped.

- [ ] **Step 2: Replace the hero markup**

Replace **lines 230-448** (from `<!-- Ops Hero -->` through its closing `</section>`) with:

```html
<!-- Ops Hero -->
<section class="ops-hero">
    <div class="ops-hero-stack">

        {% if current_user and current_user.linked_player %}
        <div>
            <div class="you-identity">
                <span class="you-name">{{ current_user.linked_player.name }}</span>
                {% if player_th %}<span class="you-th-badge">TH{{ player_th }}</span>{% endif %}
                <span class="you-league">{{ player_league or 'Unranked' }}</span>
            </div>

            <div class="you-chip-row">
                {% if player_ranked_left is not none %}
                {% set rl_color = 'var(--ops-win)' if player_ranked_left == 0 else ('var(--ops-gold)' if player_ranked_left <= 3 else 'var(--ops-raid)') %}
                <a href="/ranked" class="you-chip" style="--tick:{{ rl_color }};">
                    <div class="k">Ranked left</div>
                    <div class="v" style="color:{{ rl_color }};">{{ player_ranked_left }}</div>
                </a>
                {% endif %}
                <a href="/battles" class="you-chip" style="--tick:var(--ops-ink-dim);">
                    <div class="k">Since {{ week_start_name }}</div>
                    <div class="v" style="color:{{ 'var(--ops-win)' if player_attacks_this_week > 0 else 'var(--ops-ink-dim)' }};">{{ player_attacks_this_week }} atk</div>
                </a>
                {% if player_war_stats.attacks > 0 %}
                <a href="/war" class="you-chip" style="--tick:var(--ops-gold);">
                    <div class="k">War · {{ player_war_stats.wars }} war{{ 's' if player_war_stats.wars != 1 else '' }} · 30d</div>
                    <div class="v" style="color:var(--ops-gold);">{{ player_war_stats.attacks }} atk</div>
                </a>
                {% endif %}
                {% if player_cwl_stats.attacks > 0 %}
                <a href="/cwl" class="you-chip" style="--tick:var(--ops-elixir);">
                    <div class="k">CWL · {{ player_cwl_stats.wars }} round{{ 's' if player_cwl_stats.wars != 1 else '' }}</div>
                    <div class="v" style="color:var(--ops-elixir);">{{ player_cwl_stats.attacks }} atk</div>
                </a>
                {% endif %}
            </div>

            <a href="/tools/equipment" class="ops-ore-strip" title="Ore balance — open the equipment planner">
                <div class="ops-ore-cell">
                    <img src="/static/img/shiny.png" class="ops-ore-icon">
                    <div class="ops-ore-val" style="color:var(--ops-gold);">{{ "{:,}".format(player_ore.shiny) }}</div>
                    <div class="ops-ore-sub"><span id="pog-shiny-d">—</span>/d · <span id="pog-shiny-m">—</span>/mo</div>
                </div>
                <div class="ops-ore-cell">
                    <img src="/static/img/glowy.png" class="ops-ore-icon">
                    <div class="ops-ore-val" style="color:var(--ops-win);">{{ "{:,}".format(player_ore.glowy) }}</div>
                    <div class="ops-ore-sub"><span id="pog-glowy-d">—</span>/d · <span id="pog-glowy-m">—</span>/mo</div>
                </div>
                <div class="ops-ore-cell">
                    <img src="/static/img/starry.png" class="ops-ore-icon">
                    <div class="ops-ore-val" style="color:var(--ops-elixir);">{{ player_ore.starry }}</div>
                    <div class="ops-ore-sub"><span id="pog-starry-d">—</span>/d · <span id="pog-starry-m">—</span>/mo</div>
                </div>
            </a>
        </div>
        {% elif current_user %}
        <div class="you-guest">Your account isn't linked to a player yet — see <a href="/profile">your profile</a> for details.</div>
        {% else %}
        <div class="you-guest"><a href="/login">Log in</a> to see your personal stats.</div>
        {% endif %}

        <div>
            <div class="ops-status-lbl">Clan</div>

            {% set any_war = active_war or last_war %}
            {% set any_cwl = active_cwl_season or last_cwl_war %}
            {% set any_raid = active_raid or last_raid %}

            {% if any_war or any_cwl or any_raid %}
            <div class="clan-ticket-grid">

                {% if active_war %}
                <a href="/war" class="ops-ticket" style="--mode:var(--ops-gold);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode"><span class="ops-live-dot {{ 'on' if active_war.state == 'inWar' }}"></span>War</span>
                        <span class="ops-ticket-state">{% if active_war.state == 'inWar' %}In War{% else %}Preparation{% endif %}</span>
                    </div>
                    {% if active_war.state == 'inWar' %}
                    <div class="ops-score-row">
                        <div class="ops-score-side">
                            <div class="ops-score-num ops-win-txt">{{ active_war.clan_stars or 0 }}★</div>
                            <div class="ops-score-atk">{{ active_war.clan_attacks or 0 }}/{{ (active_war.team_size or 0) * 2 }} atk</div>
                            <div class="ops-score-lbl">{{ active_war.clan_name or 'Us' }}</div>
                        </div>
                        <div class="ops-score-sep">VS</div>
                        <div class="ops-score-side">
                            <div class="ops-score-num ops-loss-txt">{{ active_war.opponent_stars or 0 }}★</div>
                            <div class="ops-score-atk">{{ active_war.opponent_attacks or 0 }}/{{ (active_war.team_size or 0) * 2 }} atk</div>
                            <div class="ops-score-lbl">{{ active_war.opponent_name or 'Them' }}</div>
                        </div>
                    </div>
                    {% else %}
                    <div class="ops-idle-msg">War starts {{ active_war.start_time | local_dt('%d.%m · %H:%M') if active_war.start_time else 'soon' }}</div>
                    {% endif %}
                    <div class="ops-ticket-meta">
                        <span>vs <strong>{{ active_war.opponent_name or '?' }}</strong>{% if active_war.team_size %} · {{ active_war.team_size }}v{{ active_war.team_size }}{% endif %}</span>
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                            {% if active_war.end_time %}<span>Ends {{ active_war.end_time | local_dt('%d.%m · %H:%M') }}</span>{% endif %}
                            <span class="ops-goto">Go to →</span>
                        </div>
                    </div>
                </a>
                {% elif last_war %}
                {% set lw_result = 'Won' if last_war.clan_stars > last_war.opponent_stars else ('Lost' if last_war.clan_stars < last_war.opponent_stars else 'Tied') %}
                <a href="/war" class="ops-ticket idle-result" style="--mode:var(--ops-ink-dim);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode">War</span>
                        <span class="ops-ticket-state">Last War</span>
                    </div>
                    <div class="ops-score-row">
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if lw_result == 'Won' else ('ops-loss-txt' if lw_result == 'Lost' else '') }}">{{ last_war.clan_stars or 0 }}★</div>
                            <div class="ops-score-lbl">{{ last_war.clan_name or 'Us' }}</div>
                        </div>
                        <div class="ops-score-sep">{{ lw_result }}</div>
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if lw_result == 'Lost' else ('ops-loss-txt' if lw_result == 'Won' else '') }}">{{ last_war.opponent_stars or 0 }}★</div>
                            <div class="ops-score-lbl">{{ last_war.opponent_name or 'Them' }}</div>
                        </div>
                    </div>
                    <div class="ops-ticket-meta">
                        <span>vs <strong>{{ last_war.opponent_name or '?' }}</strong></span>
                        <span>Ended {{ last_war.end_time | local_dt('%d.%m · %H:%M') }}</span>
                    </div>
                </a>
                {% endif %}

                {% if active_cwl_season %}
                <a href="/cwl" class="ops-ticket" style="--mode:var(--ops-elixir);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode"><span class="ops-live-dot {{ 'on' if active_cwl_war and active_cwl_war.state == 'inWar' }}"></span>War League</span>
                        <span class="ops-ticket-state">{% if active_cwl_war and active_cwl_war.state == 'inWar' %}In War{% else %}Preparation{% endif %}</span>
                    </div>

                    {% if active_cwl_war and active_cwl_war.state == 'inWar' %}
                    {% set our_side = active_cwl_war.clan_tag == CLAN_TAG %}
                    {% set our_stars  = active_cwl_war.clan_stars   if our_side else active_cwl_war.opp_stars %}
                    {% set our_atk    = active_cwl_war.clan_attacks  if our_side else active_cwl_war.opp_attacks %}
                    {% set our_name   = active_cwl_war.clan_name    if our_side else active_cwl_war.opp_name %}
                    {% set opp_stars  = active_cwl_war.opp_stars    if our_side else active_cwl_war.clan_stars %}
                    {% set opp_atk    = active_cwl_war.opp_attacks   if our_side else active_cwl_war.clan_attacks %}
                    {% set opp_name   = active_cwl_war.opp_name     if our_side else active_cwl_war.clan_name %}
                    {% set our_s = our_stars or 0 %}
                    {% set opp_s = opp_stars or 0 %}
                    <div class="ops-score-row">
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if our_s > opp_s else ('ops-loss-txt' if our_s < opp_s else '') }}">{{ our_s }}★</div>
                            <div class="ops-score-atk">{{ our_atk or 0 }}/{{ active_cwl_war.team_size or 0 }} atk</div>
                            <div class="ops-score-lbl">{{ our_name or clan_name }}</div>
                        </div>
                        <div class="ops-score-sep">{% if our_s > opp_s %}WINNING{% elif our_s < opp_s %}LOSING{% else %}TIED{% endif %}</div>
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if opp_s > our_s else ('ops-loss-txt' if opp_s < our_s else '') }}">{{ opp_s }}★</div>
                            <div class="ops-score-atk">{{ opp_atk or 0 }}/{{ active_cwl_war.team_size or 0 }} atk</div>
                            <div class="ops-score-lbl">{{ opp_name or 'Opponent' }}</div>
                        </div>
                    </div>
                    {% if cwl_win_status %}
                    <div style="text-align:center;margin-bottom:2px;">
                        {% if cwl_win_status == 'safe_win' %}<span class="ops-ticket-state" style="--mode:var(--ops-win);color:var(--ops-win);border-color:rgba(62,192,106,.35);background:rgba(62,192,106,.12);">Safe Win</span>
                        {% elif cwl_win_status == 'cant_win' %}<span class="ops-ticket-state" style="color:var(--ops-raid);border-color:rgba(226,72,63,.35);background:rgba(226,72,63,.12);">Out of Reach</span>
                        {% elif cwl_win_status == 'contested' %}<span class="ops-ticket-state" style="color:var(--ops-gold);border-color:rgba(217,164,65,.35);background:rgba(217,164,65,.12);">Undecided</span>
                        {% endif %}
                    </div>
                    {% endif %}
                    {% else %}
                    <div class="ops-idle-msg">
                        {% if active_cwl_war and active_cwl_war.start_time %}War starts {{ active_cwl_war.start_time | local_dt('%d.%m · %H:%M') }}
                        {% else %}Season {{ active_cwl_season.season }} · {{ active_cwl_season.league_name or 'CWL' }}{% endif %}
                    </div>
                    {% endif %}

                    <div class="ops-ticket-meta">
                        <span>{{ active_cwl_season.season }}{% if active_cwl_season.league_name %} · {{ active_cwl_season.league_name }}{% endif %}{% if active_cwl_war %} · Round {{ active_cwl_war.round_number }}{% endif %}</span>
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                            {% if active_cwl_war and active_cwl_war.end_time %}<span>Ends {{ active_cwl_war.end_time | local_dt('%d.%m · %H:%M') }}</span>{% endif %}
                            <span class="ops-goto">Go to →</span>
                        </div>
                    </div>
                </a>
                {% elif last_cwl_war %}
                {% set lc_side = last_cwl_war.clan_tag == CLAN_TAG %}
                {% set lc_our_s = (last_cwl_war.clan_stars if lc_side else last_cwl_war.opp_stars) or 0 %}
                {% set lc_opp_s = (last_cwl_war.opp_stars if lc_side else last_cwl_war.clan_stars) or 0 %}
                {% set lc_our_name = last_cwl_war.clan_name if lc_side else last_cwl_war.opp_name %}
                {% set lc_opp_name = last_cwl_war.opp_name if lc_side else last_cwl_war.clan_name %}
                {% set lc_result = 'Won' if lc_our_s > lc_opp_s else ('Lost' if lc_our_s < lc_opp_s else 'Tied') %}
                <a href="/cwl" class="ops-ticket idle-result" style="--mode:var(--ops-ink-dim);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode">War League</span>
                        <span class="ops-ticket-state">Last Round</span>
                    </div>
                    <div class="ops-score-row">
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if lc_result == 'Won' else ('ops-loss-txt' if lc_result == 'Lost' else '') }}">{{ lc_our_s }}★</div>
                            <div class="ops-score-lbl">{{ lc_our_name or clan_name }}</div>
                        </div>
                        <div class="ops-score-sep">{{ lc_result }}</div>
                        <div class="ops-score-side">
                            <div class="ops-score-num {{ 'ops-win-txt' if lc_result == 'Lost' else ('ops-loss-txt' if lc_result == 'Won' else '') }}">{{ lc_opp_s }}★</div>
                            <div class="ops-score-lbl">{{ lc_opp_name or 'Opponent' }}</div>
                        </div>
                    </div>
                    <div class="ops-ticket-meta">
                        <span>Round {{ last_cwl_war.round_number }}</span>
                        <span>Ended {{ last_cwl_war.end_time | local_dt('%d.%m · %H:%M') }}</span>
                    </div>
                </a>
                {% endif %}

                {% if active_raid %}
                <a href="/raid" class="ops-ticket" style="--mode:var(--ops-raid);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode"><span class="ops-live-dot on"></span>Raid Weekend</span>
                        <span class="ops-ticket-state">Ongoing</span>
                    </div>
                    <div class="ops-big-stat">
                        {% if active_raid_est_medals %}
                        <div class="ops-big-num">≈{{ active_raid_est_medals }}</div>
                        <div class="ops-big-lbl">Est. medals (off. + avg def.)</div>
                        {% else %}
                        <div class="ops-big-num" style="color:var(--ops-ink-dim);">—</div>
                        <div class="ops-big-lbl">Est. medals</div>
                        {% endif %}
                    </div>
                    <div class="ops-ticket-meta">
                        <span>Started {{ active_raid.start_time.strftime('%d.%m') if active_raid.start_time else '—' }}</span>
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                            {% if active_raid.end_time %}<span>Ends {{ active_raid.end_time | local_dt('%d.%m · %H:%M') }}</span>{% endif %}
                            <span class="ops-goto">Go to →</span>
                        </div>
                    </div>
                </a>
                {% elif last_raid %}
                <a href="/raid" class="ops-ticket idle-result" style="--mode:var(--ops-ink-dim);">
                    <div class="ops-ticket-head">
                        <span class="ops-ticket-mode">Raid Weekend</span>
                        <span class="ops-ticket-state">Last Raid</span>
                    </div>
                    <div class="ops-big-stat">
                        <div class="ops-big-num">{{ "{:,}".format((last_raid.offensive_reward or 0) + (last_raid.defensive_reward or 0)) }}</div>
                        <div class="ops-big-lbl">Medals earned</div>
                    </div>
                    <div class="ops-ticket-meta">
                        <span>{{ last_raid.start_time.strftime('%d.%m') if last_raid.start_time else '—' }}</span>
                        <span>Ended {{ last_raid.end_time | local_dt('%d.%m · %H:%M') }}</span>
                    </div>
                </a>
                {% endif %}

            </div>
            {% else %}
            <div class="clan-empty">No activity yet — <a href="/war">War</a> · <a href="/cwl">CWL</a> · <a href="/raid">Raid</a></div>
            {% endif %}

            <div class="ops-pulse">
                <div class="ops-pulse-row">
                    <a href="/clan" class="ops-pulse-item">
                        <div class="ops-pulse-num">{{ total_members }}</div>
                        <div class="ops-pulse-lbl">Active<br>members</div>
                    </a>
                    <a href="/battles" class="ops-pulse-item">
                        <div class="ops-pulse-num" style="color:var(--ops-gold);">{{ battle_logs_this_week }}</div>
                        <div class="ops-pulse-lbl">Attacks tracked<br>since {{ week_start_name }}</div>
                    </a>
                    <a href="/ranked" class="ops-pulse-item">
                        <div class="ops-pulse-num" style="color:var(--ops-ranked);">{{ ranked_battles_this_week }}</div>
                        <div class="ops-pulse-lbl">Ranked attacks<br>this week</div>
                    </a>
                </div>
            </div>
        </div>

    </div>
</section>
```

Note what's preserved verbatim from the old markup: every active-event branch (`active_war`, the `active_cwl_season`/`active_cwl_war` block including the `our_side`/`cwl_win_status` logic, `active_raid`) is copied unchanged — only the `{% elif last_* %}` branches and the outer `.clan-ticket-grid`/`.clan-empty` wrapping are new. The ore strip and its `pog-*` IDs are copied unchanged.

- [ ] **Step 3: Verify — no active events (or whatever your current DB state is)**

Run: `cd coc_stats && python app.py`, then visit `http://127.0.0.1:5000/` in a browser. Confirm:
- The page renders with no server error and no visibly broken layout.
- The You band shows either your identity+chips+ore-strip (if logged in with a linked player), or the correct one-line guest/unlinked message.
- The Clan band shows a ticket for each event that's active *or* has a completed record, in a grid that wraps naturally; if literally none of War/CWL/Raid have ever run, it shows the single "No activity yet" line instead.
- The pulse strip (members / attacks tracked / ranked attacks) always shows below the tickets, regardless of event state.
- Command Deck and the footer look unchanged.

- [ ] **Step 4: Verify at all three widths**

Using the browser's device toolbar, check the same page at **390×844** (iPhone 16e), **760px** width, and **1200px** width. At each width confirm:
- The chip row, ticket grid, and pulse strip each reflow to however many columns fit (1-4 for chips, 1-3 for tickets, 1-3 for the pulse strip) without any text truncation or overlap — this is the same `auto-fit`/`minmax` behavior validated in the brainstorming mockup, so no separate mobile-specific markup should be needed.
- The identity line (name/TH badge/league) wraps onto a second line at 390px if needed, without breaking the layout.

- [ ] **Step 5: Commit**

```bash
git add coc_stats/templates/index.html
git commit -m "feat(dashboard): rewrite hero as stacked You/Clan bands"
```

---

### Task 3: Full manual verification pass

**Files:** none (verification only).

**Interfaces:**
- Consumes: everything from Tasks 1-2.
- Produces: nothing.

- [ ] **Step 1: Verify every data-state combination**

Run: `cd coc_stats && python app.py`. Using real or temporarily-adjusted DB state (or by reasoning through what each branch renders given your current data), confirm each of the following at least once, at **390×844**, **760px**, and **1200px**:

- Logged in with a linked player, at least one of `player_war_stats.attacks`/`player_cwl_stats.attacks` is 0 (its chip should not render) and at least one is > 0 (its chip should render).
- Logged in without a linked player → single guest-style line pointing to `/profile`.
- Not logged in → single guest-style line pointing to `/login`.
- An event is currently active (whichever of War/CWL/Raid your DB currently has) → its ticket shows the live/in-progress markup, unchanged from before this redesign.
- An event is not active but has a completed record → its ticket shows the muted `idle-result` styling with the correct Won/Lost/Tied color and the real score/medals.
- If you can find or simulate a state where none of War/CWL/Raid have ever run (unlikely on a real clan's DB — skip this one if there's no way to test it without faking data), the ticket area collapses to the single "No activity yet" line.
- Pulse strip numbers match `total_members` / `battle_logs_this_week` / `ranked_battles_this_week` regardless of the above.
- Command Deck tiles and the footer are pixel-identical to before this redesign (nothing here was touched).

- [ ] **Step 2: Report results**

If everything above checks out, the redesign is complete. If anything fails, fix it in Task 1 or Task 2's files and re-run this checklist before considering the plan done.
