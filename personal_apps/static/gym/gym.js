// Gym Tracker shared JS -- chart rendering + small utilities used across
// exercise_detail.html (static Jinja-rendered data) and session_detail.html's
// quick-glance progress modal (dynamically fetched JSON). Kept as one
// implementation so the two never drift into two different chart looks.
window.GymUtils = {
    escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    },
};

window.GymChart = {
    // The 5 custom properties renderProgressChart needs, resolved to concrete
    // strings up front -- canvas cannot resolve var(--token), for fill
    // colours any more than for anything else drawn on it, so every colour
    // that ends up in a Chart.js config has to already be a literal by the
    // time it gets there. Logs loudly (never silently) if gym.css hasn't set
    // a token yet, since a silently-missing colour is exactly the failure
    // mode this exists to catch.
    resolveTokens() {
        const styles = getComputedStyle(document.documentElement);
        const names = ['ink', 'dim', 'edge', 'unlit', 'live', 'record'];
        const tokens = {};
        names.forEach((name) => {
            const value = styles.getPropertyValue(`--${name}`).trim();
            if (!value) {
                console.error(`GymChart.resolveTokens: --${name} resolved empty -- the chart will be missing a colour it needs.`);
            }
            tokens[name] = value;
        });
        return tokens;
    },

    // Mirrors gym.css's --font-mono stack. Canvas text can't resolve var()
    // any more than a fill colour can, so this has to be a literal -- kept
    // in exactly one place rather than repeated at every call site, so
    // there is only one spot to update if gym.css's stack ever changes.
    _FONT_MONO: 'Saira, ui-monospace, "Cascadia Mono", Consolas, monospace',

    // Formats a server-sent RFC 822 date string (what Flask's tojson/jsonify
    // emit for a naive-UTC datetime.datetime -- see werkzeug.http.http_date)
    // as dd.mm.yyyy. UTC getters, not local ones: every other date display
    // in this app (Jinja's strftime calls) shows the naive timestamp exactly
    // as stored, with no timezone conversion -- reading it back here with
    // local getters would shift dates near midnight by the browser's UTC
    // offset. Same reasoning GymClock.start() documents below for its own
    // manual 'Z' suffix.
    _formatDate(rfc822) {
        const d = new Date(rfc822);
        const pad = (n) => String(n).padStart(2, '0');
        return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`;
    },

    // Position-identity palette. Real data tops out at 3 distinct positions
    // for any one exercise (checked against the live DB), and gym.css's
    // token contract permits exactly 3 semantic hues (live/record/stall)
    // with none spare for a 4th "which slot" meaning -- stall means
    // attention/destructive and is deliberately never repurposed here. So:
    // Series identity rides the NEUTRAL ramp, never a semantic hue.
    //
    // This used to be [live, record, ink] -- so a second position drew in
    // gold purely because it was series #2, and the legend read "Position 6"
    // in the exact colour that means REKORD on every other surface. PRODUCT.md
    // 4.3 is explicit that a token may never be repurposed, and 4.3's fourth
    // constraint is that nothing decorative gets a colour. A slot number is
    // decorative here; the record is not.
    //
    // Lightness plus point shape separates the lines instead, which also
    // keeps "colour is never the sole signal" true. --record is now spent
    // where it earns its meaning: on the individual points that set a PR
    // (see renderProgressChart). A 4th+ position cycles the same ramp on a
    // dashed line rather than inventing a colour.
    _seriesStyle(index, tokens) {
        const ramp = [tokens.ink, tokens.dim, tokens.unlit];
        const shapes = ['circle', 'rectRot', 'triangle'];
        const cycle = Math.floor(index / ramp.length);
        return {
            color: ramp[index % ramp.length],
            pointStyle: shapes[index % shapes.length],
            dash: cycle > 0 ? [6, 4] : [],
        };
    },

    // Renders one e1RM line per workout position onto `canvas`. `series` is
    // stats.exercise_progress()'s own `series` field, passed straight
    // through: a list of {position, points: [{started_at, e1rm, best_weight,
    // volume}, ...]}. Position is a series, not a filter -- every position
    // gets its own line, so a slot sitting consistently above another is
    // visible instead of hidden behind a filter. `tokens` is
    // GymChart.resolveTokens()'s output (or an object with the same 5 keys).
    // Returns the Chart instance -- caller owns its lifecycle (call
    // .destroy() before re-rendering onto the same canvas, same as Chart.js
    // always requires). Two consumers: exercise_detail.html (Jinja-rendered
    // series) and _progress_modal.html (fetched JSON) -- kept as one
    // implementation so the two never drift into two different chart looks.
    renderProgressChart(canvas, { series, tokens }) {
        ['ink', 'dim', 'edge', 'unlit', 'live', 'record'].forEach((name) => {
            if (!tokens || !tokens[name]) {
                console.error(`GymChart.renderProgressChart: token "${name}" resolved empty -- the chart would silently lose that colour.`);
            }
        });
        const font = { family: GymChart._FONT_MONO, size: 10 };

        // Shared x-axis: every date any position-series has a point on,
        // chronological and deduplicated. Each dataset below is then built
        // parallel to this array (null where that position has no point on
        // that date) so Chart.js's category scale places every series
        // correctly even though the positions don't share the same sessions.
        const allTimes = [...new Set(
            series.flatMap((s) => s.points.map((p) => new Date(p.started_at).getTime()))
        )].sort((a, b) => a - b);
        const labels = allTimes.map((t) => GymChart._formatDate(new Date(t).toUTCString()));

        // Which points were RECORDS: a point whose e1RM beats every earlier
        // point of this exercise, across all positions, in chronological
        // order. Derived here rather than added to the API because it is
        // fully determined by data the chart already has -- and because a
        // record IS "the best so far", so computing it from the series keeps
        // the definition in one place instead of two.
        //
        // Deload points are excluded from the running-best comparison: a
        // deload is a deliberately light session, not an attempt at a
        // record, so it must never be eligible to set or beat one -- even
        // when its e1RM numerically happens to exceed the prior best. This
        // has to agree with the server side, which excludes deloads from
        // `_pr_weight` / `_pr_e1rm` in features/gym/stats.py for the same
        // reason; the PR cards on this same page already reflect that. The
        // points themselves are still plotted below (spanGaps stays false,
        // nothing is filtered out of `series`) -- only their eligibility to
        // BE a record changes, so the line has no holes.
        const bestByTime = new Map();
        let runningBest = -Infinity;
        allTimes.forEach((t) => {
            const onDate = series
                .flatMap((s) => s.points.filter((p) => new Date(p.started_at).getTime() === t && !p.is_deload))
                .map((p) => p.e1rm);
            const dayBest = onDate.length ? Math.max(...onDate) : null;
            if (dayBest !== null && dayBest > runningBest) {
                runningBest = dayBest;
                bestByTime.set(t, dayBest);
            }
        });

        const datasets = series.map((s, i) => {
            const style = GymChart._seriesStyle(i, tokens);
            const byTime = new Map(s.points.map((p) => [new Date(p.started_at).getTime(), p]));
            const aligned = allTimes.map((t) => byTime.get(t) || null);
            const isRecord = allTimes.map((t, idx) => {
                const p = aligned[idx];
                // p.is_deload is checked again here (not just when building
                // bestByTime above): without it, a deload point whose e1RM
                // happens to numerically match that day's real best -- set
                // by a different position, or by itself before dedup -- would
                // still get flagged, since the value alone can't tell a
                // deload apart from the record it happens to tie.
                return !!(p && !p.is_deload && bestByTime.get(t) === p.e1rm);
            });
            return {
                label: `Position ${s.position}`,
                data: aligned.map((p) => (p ? p.e1rm : null)),
                _points: aligned,   // parallel array; Chart.js ignores unknown keys -- read back in the tooltip callback below for weight/volume detail
                _isRecord: isRecord,
                borderColor: style.color,
                backgroundColor: style.color,
                pointStyle: style.pointStyle,
                borderDash: style.dash,
                // gold, and bigger, exactly on the points that set a new best
                pointBackgroundColor: isRecord.map((r) => (r ? tokens.record : style.color)),
                pointBorderColor: isRecord.map((r) => (r ? tokens.record : style.color)),
                pointRadius: isRecord.map((r) => (r ? 7 : 4)),
                spanGaps: false,
                tension: 0.3,
                pointHoverRadius: 8,
            };
        });

        return new Chart(canvas, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        ticks: { color: tokens.dim, maxRotation: 0, font },
                        grid: { color: tokens.edge },
                    },
                    y: {
                        // No beginAtZero: real progress is often a few kg on
                        // top of a much larger base weight, and forcing the
                        // axis down to 0 would visually flatten exactly the
                        // differences this chart exists to make legible.
                        ticks: { color: tokens.dim, font },
                        grid: { color: tokens.edge },
                        title: { display: true, text: 'e1RM (kg)', color: tokens.dim, font },
                    },
                },
                plugins: {
                    // A single-position exercise (the common case) has
                    // nothing for a legend to disambiguate.
                    legend: { display: series.length > 1, labels: { color: tokens.ink, boxWidth: 12, font } },
                    tooltip: {
                        titleFont: font,
                        bodyFont: font,
                        callbacks: {
                            label(ctx) {
                                const point = ctx.dataset._points[ctx.dataIndex];
                                if (!point) return '';
                                return `${ctx.dataset.label} — e1RM ${point.e1rm} kg · ${point.best_weight} kg · Vol ${point.volume} kg`;
                            },
                        },
                    },
                },
            },
        });
    },
};

window.GymClock = {
    // Ticks HH:MM:SS into `element` from its data-started ISO timestamp.
    // The timestamps the server writes are naive UTC, so 'Z' has to be
    // appended or the browser reads them as local time and the elapsed
    // figure is wrong by the timezone offset.
    start(element) {
        if (!element) return;
        const startedAt = new Date(element.dataset.started + 'Z');
        const pad = (n) => String(n).padStart(2, '0');
        const tick = () => {
            const total = Math.floor(Math.max(0, Date.now() - startedAt.getTime()) / 1000);
            element.textContent = `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
        };
        tick();
        return setInterval(tick, 1000);
    },
};
