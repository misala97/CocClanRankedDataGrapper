// The one piece of shared JS the gym pages still load. Everything else moved
// into the React islands under static/gym/src/; this stays because _nav.html
// is on every page, is still Jinja, and its resume strip ticks a clock.
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
