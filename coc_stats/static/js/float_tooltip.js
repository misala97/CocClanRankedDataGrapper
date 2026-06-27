// Single floating tooltip box reused site-wide — replaces the browser's native
// unstyled title="" tooltip, and every other one-off custom tooltip div, with
// one consistent dark-themed, edge-aware floating box (same look as the CWL/war
// win-probability chart markers this was originally built for).
(function () {
    function getTip() {
        let tip = document.getElementById('floatTip');
        if (!tip) {
            tip = document.createElement('div');
            tip.id = 'floatTip';
            tip.className = 'float-tooltip';
            document.body.appendChild(tip);
        }
        return tip;
    }

    function moveFloatTip(evt) {
        const tip = document.getElementById('floatTip');
        if (!tip || !evt) return;
        const pad = 14;
        const rect = tip.getBoundingClientRect();
        let x = evt.clientX + pad, y = evt.clientY + pad;
        if (x + rect.width  > window.innerWidth)  x = evt.clientX - rect.width  - pad;
        if (y + rect.height > window.innerHeight) y = evt.clientY - rect.height - pad;
        tip.style.left = x + 'px';
        tip.style.top  = y + 'px';
    }

    function showFloatTip(html, evt) {
        const tip = getTip();
        tip.innerHTML = html;
        tip.style.display = 'block';
        moveFloatTip(evt || window.event);
    }

    function hideFloatTip() {
        const tip = document.getElementById('floatTip');
        if (tip) tip.style.display = 'none';
    }

    function escapeForTip(s) {
        return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function partsToHTML(title, line1, line2) {
        return `<div style="font-weight:700;margin-bottom:3px;">${title}</div>` +
               (line1 ? `<div>${line1}</div>` : '') +
               (line2 ? `<div style="color:var(--muted);margin-top:2px;">${line2}</div>` : '');
    }

    // Back-compat entry points for elements carrying data-title/data-line1/data-line2
    // (the CWL/war win-probability chart markers use these directly).
    window.wcTipShow = function (el) { showFloatTip(partsToHTML(el.dataset.title, el.dataset.line1, el.dataset.line2)); };
    window.wcTipMove = moveFloatTip;
    window.wcTipHide = hideFloatTip;

    window.showFloatTip = showFloatTip;
    window.moveFloatTip = moveFloatTip;
    window.hideFloatTip = hideFloatTip;

    // ── Global hijack of native title="" tooltips ──────────────────────────
    // The title is stripped on hover (so the browser never shows its own box)
    // and restored once that element stops being the active one, so anything
    // else reading the attribute still sees it.
    let activeEl = null, activeTitle = null;

    function restoreActive() {
        if (activeEl) activeEl.setAttribute('title', activeTitle);
        activeEl = null;
        activeTitle = null;
    }

    // Switching is handled entirely on mouseover (not mouseout) so that moving
    // from a titled element straight into a titled DESCENDANT (e.g. an outer
    // div with title plus child spans with their own title) still restores the
    // outer element's title before activating the child — mouseout's relatedTarget
    // can't distinguish "leaving to a child" from "leaving to nothing", so relying
    // on it here would permanently strand the outer element's title.
    document.addEventListener('mouseover', e => {
        const el = e.target.closest('[title]');
        if (!el || el === activeEl) return;
        restoreActive();
        const title = el.getAttribute('title');
        if (!title) { hideFloatTip(); return; }
        el.removeAttribute('title');
        activeEl = el;
        activeTitle = title;
        showFloatTip(title.split('\n').map(escapeForTip).join('<br>'), e);
    });
    document.addEventListener('mousemove', e => {
        if (!activeEl) return;
        // If the active element was removed from the DOM by an innerHTML re-render
        // while the mouse never left it, no mouseout ever fires for the detached
        // node — catch that here instead of leaving the tooltip stuck on screen.
        if (!activeEl.isConnected) { restoreActive(); hideFloatTip(); return; }
        moveFloatTip(e);
    });
    document.addEventListener('mouseout', e => {
        if (!activeEl) return;
        // Leaving into a titled descendant is handled by that element's own
        // mouseover (see above) — only treat this as "really left" when the
        // pointer isn't headed into another [title] element inside activeEl.
        const enteringTitled = e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('[title]');
        if (enteringTitled) return;
        if (!activeEl.contains(e.relatedTarget)) {
            restoreActive();
            hideFloatTip();
        }
    });

    // ── Chart.js default tooltip restyle, so built-in chart tooltips match too ──
    if (window.Chart) {
        const t = Chart.defaults.plugins.tooltip;
        t.backgroundColor = '#1c2330';
        t.borderColor = '#30363d';
        t.borderWidth = 1;
        t.padding = 10;
        t.cornerRadius = 6;
        t.titleColor = '#e6edf3';
        t.bodyColor = '#e6edf3';
        t.titleFont = { weight: '700', size: 12 };
        t.bodyFont = { size: 11 };
        t.boxPadding = 4;
    }
})();
