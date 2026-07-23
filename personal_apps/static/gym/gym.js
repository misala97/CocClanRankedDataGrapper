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
    // Renders the best/worst-weight band + a volume reference line onto
    // `canvas`. `data` = { labels, weights, minWeights, volumes }. Returns
    // the Chart instance -- caller owns its lifecycle (call .destroy()
    // before re-rendering onto the same canvas, same as Chart.js always
    // requires).
    renderProgressChart(canvas, data) {
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        // Drawn first (order:2) so the fill on the dataset
                        // below it (order:1, fill:'-1') has this as its
                        // "previous" dataset to band against.
                        label: 'Leichtestes Gewicht (kg)',
                        data: data.minWeights,
                        borderColor: 'rgba(232,232,236,0.25)',
                        backgroundColor: 'transparent',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y',
                        order: 2,
                    },
                    {
                        label: 'Bestes Gewicht (kg)',
                        data: data.weights,
                        borderColor: '#d4ff3f',
                        backgroundColor: 'rgba(212,255,63,0.18)',
                        tension: 0.3,
                        fill: '-1',
                        yAxisID: 'y',
                        order: 1,
                    },
                    {
                        label: 'Volumen (kg)',
                        data: data.volumes,
                        borderColor: '#8a8a92',
                        backgroundColor: 'transparent',
                        borderDash: [2, 3],
                        pointRadius: 0,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y1',
                        order: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#8a8a92', maxRotation: 0 }, grid: { color: '#272727' } },
                    y: { position: 'left', ticks: { color: '#8a8a92' }, grid: { color: '#272727' } },
                    y1: { position: 'right', ticks: { color: '#8a8a92' }, grid: { display: false } },
                },
                plugins: {
                    legend: { labels: { color: '#e8e8ec', boxWidth: 12, font: { size: 10 } } },
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
