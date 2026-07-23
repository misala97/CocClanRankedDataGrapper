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
        const names = ['ink', 'dim', 'edge', 'live', 'record'];
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
    _FONT_MONO: '"IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace',

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
    // 3 solid-hue slots (live amber / record cyan / ink near-white), each
    // with its own point shape so colour is never the only thing telling
    // two series apart -- gym.css's "colour is never the sole signal" rule
    // for state, extended here to series identity. A 4th+ position -- never
    // seen in real data, but not impossible -- cycles back through the same
    // 3 hues on a dashed line rather than inventing a new colour.
    _seriesStyle(index, tokens) {
        const hues = [tokens.live, tokens.record, tokens.ink];
        const shapes = ['circle', 'rectRot', 'triangle'];
        const cycle = Math.floor(index / hues.length);
        return {
            color: hues[index % hues.length],
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
        ['ink', 'dim', 'edge', 'live', 'record'].forEach((name) => {
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

        const datasets = series.map((s, i) => {
            const style = GymChart._seriesStyle(i, tokens);
            const byTime = new Map(s.points.map((p) => [new Date(p.started_at).getTime(), p]));
            const aligned = allTimes.map((t) => byTime.get(t) || null);
            return {
                label: `Position ${s.position}`,
                data: aligned.map((p) => (p ? p.e1rm : null)),
                _points: aligned,   // parallel array; Chart.js ignores unknown keys -- read back in the tooltip callback below for weight/volume detail
                borderColor: style.color,
                backgroundColor: style.color,
                pointStyle: style.pointStyle,
                borderDash: style.dash,
                spanGaps: false,
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 6,
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
