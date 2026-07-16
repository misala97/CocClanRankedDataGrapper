function renderStars(n, opts = {}) {
    n = Math.max(0, Math.min(parseInt(n) || 0, 3));
    const filled = opts.filled || 'var(--yellow)';
    const empty  = opts.empty  || 'var(--muted)';
    const size   = opts.size   || '1.18em';
    return `<span style="font-size:${size};letter-spacing:1px;">`
         + `<span style="color:${filled};">${'★'.repeat(n)}</span>`
         + `<span style="color:${empty};opacity:0.4;">${'☆'.repeat(3 - n)}</span>`
         + `</span>`;
}
