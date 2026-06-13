// ── Shared war/CWL probability engine ────────────────────────────────────────
// Included by clanwar.html and cwl.html. Do not add page-specific code here.

// Fallback star distributions by TH diff (attacker - defender), clamped [-4, +4]
// Base prior — recalibrated to ~67% 3★ at even matchup (observed DB average).
// Overwritten at page load by initDiffFallback() once real data is available.
let _DIFF_FALLBACK = {
     4: [0.00, 0.01, 0.05, 0.94],
     3: [0.00, 0.02, 0.11, 0.87],
     2: [0.01, 0.03, 0.17, 0.79],
     1: [0.02, 0.05, 0.20, 0.73],
     0: [0.03, 0.07, 0.23, 0.67],
    '-1': [0.05, 0.13, 0.28, 0.54],
    '-2': [0.09, 0.19, 0.33, 0.39],
    '-3': [0.15, 0.28, 0.35, 0.22],
    '-4': [0.23, 0.37, 0.28, 0.12],
};

// Return [p0,p1,p2,p3] for an attacker TH vs defender TH from the given rates dict.
// Falls back to _DIFF_FALLBACK when the matchup has <5 recorded attacks.
function atkDist(rates, atkTH, defTH) {
    const d = rates[atkTH + '_' + defTH];
    if (d) return d;
    const diff = Math.max(-4, Math.min(4, atkTH - defTH));
    return _DIFF_FALLBACK[String(diff)] || _DIFF_FALLBACK['0'];
}

// Aggregate all recorded attacks by TH diff, weighted by sample count, and use
// those empirical distributions as the per-diff fallback. For diffs with no recorded
// data at all (e.g. brand-new TH pairings), the base constants above remain.
function buildDiffFallback(rates, counts) {
    const totals = {}, weighted = {};
    for (const [key, d] of Object.entries(rates)) {
        const [atkTH, defTH] = key.split('_').map(Number);
        const diff = String(Math.max(-4, Math.min(4, atkTH - defTH)));
        const n = counts[key] || 0;
        if (!totals[diff]) { totals[diff] = 0; weighted[diff] = [0, 0, 0, 0]; }
        totals[diff] += n;
        d.forEach((p, i) => { weighted[diff][i] += p * n; });
    }
    const out = { ..._DIFF_FALLBACK };
    for (const [diff, n] of Object.entries(totals))
        if (n > 0) out[diff] = weighted[diff].map(w => w / n);
    return out;
}

function initDiffFallback(rates, counts) {
    _DIFF_FALLBACK = buildDiffFallback(rates, counts);
}

// Convolve independent per-attack probability distributions via DP.
function convolve(dists) {
    let dp = [1.0];
    for (const dist of dists) {
        const next = new Array(dp.length + 3).fill(0);
        for (let k = 0; k < dp.length; k++) {
            if (!dp[k]) continue;
            for (let s = 0; s <= 3; s++) next[k + s] += dp[k] * dist[s];
        }
        dp = next;
    }
    return dp;
}

// Resolve star distribution + source label for one attacker vs defender.
// playerInfoFn(tag, atkTH, defTH, histK) → {dist, count} | null
// matchupCounts optional — enables "DB avg · N fights" vs "Fallback" distinction.
function resolveAtkDist(playerInfoFn, atkDistFn, tag, atkTH, defTH, matchupCounts) {
    const info = playerInfoFn(tag, atkTH, defTH, 5);
    if (info) {
        const pct = Math.round(info.count / (info.count + 5) * 100);
        return { dist: info.dist, srcLabel: `${info.count} fights · ${pct}% own` };
    }
    const dist = atkDistFn(atkTH, defTH);
    if (matchupCounts) {
        const gc = matchupCounts[atkTH + '_' + defTH] || 0;
        return { dist, srcLabel: gc >= 5 ? `DB avg · ${gc} fights · 0% own` : `Fallback · 0% own` };
    }
    return { dist, srcLabel: 'DB avg · 0% own' };
}

// Adjust a raw [p0,p1,p2,p3] star distribution to account for a base that is already starred.
// Only the incremental stars above the current best count toward the war total.
// E.g. attacking a 2-starred base: getting 3★ adds 1, getting ≤2★ adds 0.
function adjustDistForStarred(dist, best) {
    if (!best) return dist;
    const adj = [0, 0, 0, 0];
    for (let k = 0; k <= 3; k++) adj[Math.max(0, k - best)] += dist[k];
    return adj;
}

// Full win-probability calculation given pre-built attacker→defender pair lists.
// Each pair: { tag, atkTH, name, pos, defTH, defName, defPos?, defBestStars? }
// defBestStars: current best stars on the target base — limits the incremental contribution.
// The attack→defender mapping is the only thing callers differ on — everything else is shared.
function calcWinProb(ourPairs, oppPairs, ourStars, oppStars, maxPossible, playerInfoFn, atkDistFn, matchupCounts) {
    function buildSide(pairs) {
        const dists = [], breakdown = [];
        for (const p of pairs) {
            const { dist: rawDist, srcLabel } = resolveAtkDist(playerInfoFn, atkDistFn, p.tag, p.atkTH, p.defTH, matchupCounts);
            const adjustedDist = adjustDistForStarred(rawDist, p.defBestStars || 0);
            dists.push(adjustedDist);  // incremental — used for convolution only
            const entry = { name: p.name, th: p.atkTH, pos: p.pos, defTH: p.defTH, defName: p.defName,
                            dist: rawDist, expStars: rawDist.reduce((s, q, k) => s + q * k, 0), srcLabel };
            if (p.defPos !== undefined) entry.defPos = p.defPos;
            if (p.defBestStars) entry.defBestStars = p.defBestStars;
            breakdown.push(entry);
        }
        return { dists, breakdown };
    }
    const { dists: ourDists, breakdown: ourBreakdown } = buildSide(ourPairs);
    const { dists: oppDists, breakdown: oppBreakdown } = buildSide(oppPairs);
    const dpOur = convolve(ourDists), dpOpp = convolve(oppDists);
    let pWin = 0, pDraw = 0, pLoss = 0;
    for (let i = 0; i < dpOur.length; i++) {
        if (!dpOur[i]) continue;
        for (let j = 0; j < dpOpp.length; j++) {
            if (!dpOpp[j]) continue;
            const fo = Math.min(ourStars + i, maxPossible);
            const fe = Math.min(oppStars + j, maxPossible);
            const p  = dpOur[i] * dpOpp[j];
            if (fo > fe) pWin += p; else if (fo === fe) pDraw += p; else pLoss += p;
        }
    }
    const avgTHfn   = arr => arr.length ? (arr.reduce((s, a) => s + a.th, 0) / arr.length).toFixed(1) : '—';
    // True expected final: integrate over the convolution so the cap is applied per-outcome, not to the mean.
    // E[min(X, cap)] != min(E[X], cap) when the distribution spreads across the cap boundary.
    const expOurFinal = dpOur.reduce((s, p, i) => s + p * Math.min(ourStars + i, maxPossible), 0);
    const expOppFinal = dpOpp.reduce((s, p, i) => s + p * Math.min(oppStars + i, maxPossible), 0);
    return {
        pWin, pDraw, pLoss,
        ourStars, oppStars,
        ourRem: ourPairs.length, oppRem: oppPairs.length,
        ourMax: Math.min(ourStars + ourPairs.length * 3, maxPossible),
        oppMax: Math.min(oppStars + oppPairs.length * 3, maxPossible),
        expOurFinal, expOppFinal,
        teamSize: Math.round(maxPossible / 3), maxPossible,
        avgOurRemTH: avgTHfn(ourBreakdown),
        avgOppRemTH: avgTHfn(oppBreakdown),
        dpOur, dpOpp, ourBreakdown, oppBreakdown,
    };
}

// Bayesian blend of personal history with the global TH matchup distribution.
// counts: [c0,c1,c2,c3] absolute, total: sum(counts), histK: prior strength.
// The page-specific lookup of counts/total is handled by the caller.
function blendPlayerDist(counts, total, globalDist, histK) {
    const personal = counts.map(c => c / total);
    const w = total / (total + histK);
    return { dist: personal.map((p, i) => w * p + (1 - w) * globalDist[i]), count: total };
}

// Look up a player's star history for one matchup, blended with global rates.
// history shape: { tag: { "atkTH_defTH": { counts: [c0,c1,c2,c3], total: N } } }
// Same structure for both WAR_PLAYER_HISTORY and PLAYER_ALL_TIME.
function playerInfo(history, rates, tag, atkTH, defTH, histK) {
    const pp = history[tag];
    if (!pp) return null;
    const ph = pp[atkTH + '_' + defTH];
    if (!ph || ph.total < 1) return null;
    return blendPlayerDist(ph.counts, ph.total, atkDist(rates, atkTH, defTH), histK);
}

// SVG final-star-distribution histogram used in win-probability panels.
function buildStarDistChart(wc, ourName, oppName) {
    const { ourStars, oppStars, dpOur, dpOpp, maxPossible } = wc;
    const minStar = Math.min(ourStars, oppStars);
    const range = maxPossible - minStar + 1;
    if (range <= 0) return '';

    const ourFinal = new Array(range).fill(0);
    const oppFinal = new Array(range).fill(0);
    for (let i = 0; i < dpOur.length; i++) {
        const idx = Math.min(ourStars + i, maxPossible) - minStar;
        if (idx >= 0 && idx < range) ourFinal[idx] += dpOur[i];
    }
    for (let j = 0; j < dpOpp.length; j++) {
        const idx = Math.min(oppStars + j, maxPossible) - minStar;
        if (idx >= 0 && idx < range) oppFinal[idx] += dpOpp[j];
    }

    const maxProb = Math.max(...ourFinal, ...oppFinal, 0.001);
    const svgH = 72, barAreaH = svgH - 16;
    const barW = Math.max(5, Math.min(24, Math.floor(560 / range)));
    const svgW = range * barW;

    let elems = '';
    for (let i = 0; i < range; i++) {
        const x = i * barW, star = minStar + i;
        const oH = Math.round((oppFinal[i] / maxProb) * barAreaH);
        const uH = Math.round((ourFinal[i] / maxProb) * barAreaH);
        if (oH > 0) elems += `<rect x="${x}" y="${barAreaH-oH}" width="${barW-1}" height="${oH}" fill="rgba(248,81,73,.55)" rx="1"/>`;
        if (uH > 0) elems += `<rect x="${x}" y="${barAreaH-uH}" width="${barW-1}" height="${uH}" fill="rgba(63,185,80,.55)" rx="1"/>`;
        if (range <= 20 || star % 3 === 0)
            elems += `<text x="${x+barW/2}" y="${svgH-2}" text-anchor="middle" font-size="8" fill="#8b949e">${star}</text>`;
    }
    const expUidx = Math.round(wc.expOurFinal) - minStar;
    const expOidx = Math.round(wc.expOppFinal) - minStar;
    if (expUidx >= 0 && expUidx < range) {
        const x = expUidx * barW + barW / 2;
        elems += `<line x1="${x}" y1="0" x2="${x}" y2="${barAreaH}" stroke="rgba(63,185,80,.8)" stroke-width="1.5" stroke-dasharray="3,2"/>`;
    }
    if (expOidx >= 0 && expOidx < range) {
        const x = expOidx * barW + barW / 2;
        elems += `<line x1="${x}" y1="0" x2="${x}" y2="${barAreaH}" stroke="rgba(248,81,73,.8)" stroke-width="1.5" stroke-dasharray="3,2"/>`;
    }

    return `<div style="border-top:1px solid var(--bord2);padding:12px 20px 8px;">
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
            <span style="font-weight:600;">Final star distribution</span>
            <span><span style="color:rgba(63,185,80,.9);">&#9632;</span> ${escapeHTML(ourName)}</span>
            <span><span style="color:rgba(248,81,73,.9);">&#9632;</span> ${escapeHTML(oppName)}</span>
            <span style="font-style:italic;margin-left:auto;">dashed = expected</span>
        </div>
        <div style="overflow-x:auto;">
            <svg viewBox="0 0 ${svgW} ${svgH}" style="width:100%;max-width:${svgW}px;height:${svgH}px;display:block;">${elems}</svg>
        </div>
    </div>`;
}

// Attacker breakdown table — shared between war and CWL win-probability panels.
function buildAttackerTable(breakdown, side) {
    if (!breakdown.length) return '<div style="padding:8px 20px 12px;font-size:12px;color:var(--muted);">No remaining attacks.</div>';
    const clr = side === 'our' ? 'var(--green)' : 'var(--red)';
    const sorted = [...breakdown].sort((a, b) => a.pos - b.pos);
    const rows = sorted.map(p => {
        const [p0, p1, p2, p3] = p.dist;
        const seg = `<div style="display:flex;height:8px;border-radius:2px;overflow:hidden;width:72px;">
            <div style="flex:${p0||0.001};background:rgba(248,81,73,.8);"></div>
            <div style="flex:${p1||0.001};background:rgba(230,140,30,.8);"></div>
            <div style="flex:${p2||0.001};background:rgba(210,185,40,.8);"></div>
            <div style="flex:${p3||0.001};background:rgba(63,185,80,.8);"></div>
        </div>
        <div style="font-size:9px;color:var(--muted);display:flex;gap:3px;margin-top:2px;width:72px;justify-content:space-between;">
            <span title="0★">${(p0*100).toFixed(0)}%</span>
            <span title="1★">${(p1*100).toFixed(0)}%</span>
            <span title="2★">${(p2*100).toFixed(0)}%</span>
            <span title="3★">${(p3*100).toFixed(0)}%</span>
        </div>`;
        const defStarBadge = p.defBestStars ? ` <span style="color:#f0a500;font-size:9px;" title="${p.defBestStars}★ already scored">${'★'.repeat(p.defBestStars)}</span>` : '';
        return `<tr style="border-bottom:1px solid var(--bord2);">
            <td style="padding:7px 8px 7px 16px;font-weight:600;font-size:12px;white-space:nowrap;max-width:110px;overflow:hidden;text-overflow:ellipsis;">${escapeHTML(p.name)}</td>
            <td style="padding:7px 8px;text-align:center;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:13px;color:var(--blue);">TH${p.th}</td>
            <td style="padding:7px 8px;text-align:center;font-size:11px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHTML(p.defName)} (TH${p.defTH})">
                <span style="color:var(--fg);font-weight:600;">${escapeHTML(p.defName)}</span>
                <span style="color:var(--muted);font-size:10px;"> TH${p.defTH}</span>${defStarBadge}
            </td>
            <td style="padding:7px 12px;">${seg}</td>
            <td style="padding:7px 16px 7px 8px;text-align:right;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:15px;color:${clr};">${p.expStars.toFixed(1)}★</td>
            <td style="padding:7px 12px 7px 4px;font-size:10px;color:var(--muted);white-space:nowrap;">${escapeHTML(p.srcLabel)}</td>
        </tr>`;
    }).join('');
    return `<table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:var(--surf2);">
            <th style="padding:5px 8px 5px 16px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Player</th>
            <th style="padding:5px 8px;text-align:center;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">TH</th>
            <th style="padding:5px 8px;text-align:center;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Defender</th>
            <th style="padding:5px 12px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">0★ · 1★ · 2★ · 3★</th>
            <th style="padding:5px 16px 5px 8px;text-align:right;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Exp.★</th>
            <th style="padding:5px 12px 5px 4px;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Source</th>
        </tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// TH Matchup Rates modal — renders into any page's matchup modal elements.
// rates:  {"atkTH_defTH": [p0,p1,p2,p3]}
// counts: {"atkTH_defTH": n}  (includes sub-5-sample matchups)
// totalAtks: total attack count for the summary line
// contentId / backdropId / modalId: DOM element IDs that vary per page
function openMatchupRatesModal(rates, counts, totalAtks, contentId, backdropId, modalId) {
    const el = document.getElementById(contentId);
    if (!el) return;
    if (!el.innerHTML.trim()) {
        const allKeys = Object.keys(counts);
        const atkTHs = [...new Set(allKeys.map(k => +k.split('_')[0]))].sort((a,b) => b-a);
        const defTHs = [...new Set(allKeys.map(k => +k.split('_')[1]))].sort((a,b) => b-a);

        const _ts = new Date().toLocaleTimeString();
        let html = `<div style="font-size:12px;color:var(--muted);margin-bottom:18px;">
            Total attacks in DB: <strong style="color:var(--accent);font-family:'Rajdhani',sans-serif;font-size:15px;">${totalAtks.toLocaleString()}</strong>
            &nbsp;&#183;&nbsp; ${allKeys.length} matchup combinations
            &nbsp;&#183;&nbsp; <span style="color:var(--muted);font-size:11px;">&#9733; distribution shown for &#8805;5 attacks</span>
            &nbsp;&#183;&nbsp; <span style="color:var(--muted);font-size:10px;">snapshotted ${_ts}</span>
        </div><div style="overflow-x:auto;">`;

        for (const atkTH of atkTHs) {
            const rows = defTHs.map(defTH => {
                const key = `${atkTH}_${defTH}`;
                const cnt = counts[key] || 0;
                if (!cnt) return null;
                const d = rates[key];
                const lowSample = !d;
                let avgCell, barCell;
                if (d) {
                    const [p0,p1,p2,p3] = d;
                    const avgS = (p1+p2*2+p3*3).toFixed(2);
                    avgCell = `<td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:16px;color:${avgS>=2.5?'var(--green)':avgS>=1.8?'var(--yellow)':avgS>=1.2?'var(--accent)':'var(--red)'};">&#216; ${avgS}&#9733;</td>`;
                    barCell = `<td style="padding:8px 20px 8px 4px;">
                        <div style="display:flex;height:8px;border-radius:2px;overflow:hidden;min-width:80px;">
                            <div style="flex:${p0||0.001};background:rgba(248,81,73,.8);"></div>
                            <div style="flex:${p1||0.001};background:rgba(230,140,30,.8);"></div>
                            <div style="flex:${p2||0.001};background:rgba(210,185,40,.8);"></div>
                            <div style="flex:${p3||0.001};background:rgba(63,185,80,.8);"></div>
                        </div>
                        <div style="font-size:9px;color:var(--muted);display:flex;gap:2px;margin-top:2px;">
                            <span style="color:rgba(248,81,73,.9);">${(p0*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(230,140,30,.9);">${(p1*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(210,185,40,.9);">${(p2*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(63,185,80,.9);">${(p3*100).toFixed(0)}%</span>
                        </div></td>`;
                } else {
                    const fdiff = Math.max(-4, Math.min(4, atkTH - defTH));
                    const [fp0,fp1,fp2,fp3] = _DIFF_FALLBACK[String(fdiff)] || _DIFF_FALLBACK['0'];
                    const favg = (fp1 + fp2*2 + fp3*3).toFixed(2);
                    avgCell = `<td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:16px;color:var(--muted);">&#216; ${favg}&#9733; <span style="font-size:10px;font-weight:400;">(fallback)</span></td>`;
                    barCell = `<td style="padding:8px 20px 8px 4px;">
                        <div style="display:flex;height:8px;border-radius:2px;overflow:hidden;min-width:80px;opacity:.45;">
                            <div style="flex:${fp0||0.001};background:rgba(248,81,73,.8);"></div>
                            <div style="flex:${fp1||0.001};background:rgba(230,140,30,.8);"></div>
                            <div style="flex:${fp2||0.001};background:rgba(210,185,40,.8);"></div>
                            <div style="flex:${fp3||0.001};background:rgba(63,185,80,.8);"></div>
                        </div>
                        <div style="font-size:9px;color:var(--muted);display:flex;gap:2px;margin-top:2px;opacity:.6;">
                            <span>${(fp0*100).toFixed(0)}%</span>&#183;
                            <span>${(fp1*100).toFixed(0)}%</span>&#183;
                            <span>${(fp2*100).toFixed(0)}%</span>&#183;
                            <span>${(fp3*100).toFixed(0)}%</span>
                        </div></td>`;
                }
                const rowOpacity = lowSample ? 'opacity:.5;' : '';
                return `<tr style="${rowOpacity}">
                    <td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:14px;color:var(--accent);">TH${atkTH}</td>
                    <td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:14px;color:var(--muted);">vs TH${defTH}</td>
                    ${avgCell}
                    <td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-size:12px;color:var(--muted);">${cnt.toLocaleString()} atks</td>
                    ${barCell}
                </tr>`;
            }).filter(Boolean);
            if (!rows.length) continue;
            const groupTotal = defTHs.reduce((s, defTH) => s + (counts[`${atkTH}_${defTH}`] || 0), 0);
            html += `
            <div style="margin-bottom:20px;">
                <div style="font-family:'Rajdhani',sans-serif;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--bord2);display:flex;justify-content:space-between;">
                    <span>TH${atkTH} Attacking</span>
                    <span style="font-weight:400;">${groupTotal.toLocaleString()} attacks</span>
                </div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead><tr style="background:var(--surf2);">
                        <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Attacker</th>
                        <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Defender</th>
                        <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Avg &#9733;</th>
                        <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Attacks</th>
                        <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">0&#9733; &#183; 1&#9733; &#183; 2&#9733; &#183; 3&#9733;</th>
                    </tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>`;
        }
        html += `</div>`;

        const fallbackRows = Object.entries(_DIFF_FALLBACK)
            .sort((a, b) => +b[0] - +a[0])
            .map(([diff, d]) => {
                const [p0,p1,p2,p3] = d;
                const avg = (p1 + p2*2 + p3*3).toFixed(2);
                const diffN = +diff;
                const diffLabel = diffN > 0 ? `+${diffN}` : String(diffN);
                const eg = diffN === 0 ? 'e.g. TH18 vs TH18' : diffN > 0 ? `e.g. TH${18} vs TH${18-diffN}` : `e.g. TH${18+diffN} vs TH${18}`;
                return `<tr style="border-bottom:1px solid var(--bord2);">
                    <td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:15px;color:${diffN>=0?'var(--green)':'var(--red)'};">${diffLabel}</td>
                    <td style="padding:8px 14px;font-size:11px;color:var(--muted);">${eg}</td>
                    <td style="padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:16px;color:${avg>=2.5?'var(--green)':avg>=1.8?'var(--yellow)':avg>=1.2?'var(--accent)':'var(--red)'};">&#216; ${avg}&#9733;</td>
                    <td style="padding:8px 20px 8px 4px;">
                        <div style="display:flex;height:8px;border-radius:2px;overflow:hidden;min-width:80px;">
                            <div style="flex:${p0||0.001};background:rgba(248,81,73,.8);"></div>
                            <div style="flex:${p1||0.001};background:rgba(230,140,30,.8);"></div>
                            <div style="flex:${p2||0.001};background:rgba(210,185,40,.8);"></div>
                            <div style="flex:${p3||0.001};background:rgba(63,185,80,.8);"></div>
                        </div>
                        <div style="font-size:9px;color:var(--muted);display:flex;gap:2px;margin-top:2px;">
                            <span style="color:rgba(248,81,73,.9);">${(p0*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(230,140,30,.9);">${(p1*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(210,185,40,.9);">${(p2*100).toFixed(0)}%</span>&#183;
                            <span style="color:rgba(63,185,80,.9);">${(p3*100).toFixed(0)}%</span>
                        </div>
                    </td>
                </tr>`;
            }).join('');
        html += `
        <div style="margin-top:8px;padding-top:20px;border-top:2px solid var(--bord2);">
            <div style="font-family:'Rajdhani',sans-serif;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:8px;">
                Fallback Distribution (used when &lt;5 attacks on record)
            </div>
            <table style="width:100%;border-collapse:collapse;">
                <thead><tr style="background:var(--surf2);">
                    <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">TH Diff</th>
                    <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Example</th>
                    <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">Avg &#9733;</th>
                    <th style="padding:6px 14px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border);">0&#9733; &#183; 1&#9733; &#183; 2&#9733; &#183; 3&#9733;</th>
                </tr></thead>
                <tbody>${fallbackRows}</tbody>
            </table>
        </div>`;

        el.innerHTML = html;
    }
    document.getElementById(backdropId).style.display = 'block';
    document.getElementById(modalId).style.display    = 'block';
}

// Live win-probability panel renderer — shared between war and CWL.
// Returns { barHtml, bodyHtml, winAdjPct }.
// barHtml  → names + adjusted prob bar for the always-visible preview element.
// bodyHtml → full panel: guarantee banner, stats, details, chart, breakdown toggles.
function buildWinCalcHTML(wc, ourName, oppName, ourPct, oppPct, ourAtkId, oppAtkId, toggleFn) {
    const maxPerAtk = wc.teamSize > 0 ? 100 / wc.teamSize : 6.67;
    const oppMaxFinalPct = oppPct + wc.oppRem * maxPerAtk;
    const ourMaxFinalPct = ourPct + wc.ourRem * maxPerAtk;
    let drawSplitOur;
    if      (oppMaxFinalPct < ourPct) drawSplitOur = 1.0;
    else if (ourMaxFinalPct < oppPct) drawSplitOur = 0.0;
    else drawSplitOur = ourPct > oppPct ? 1.0 : ourPct < oppPct ? 0.0 : 0.5;

    const pWinAdj    = wc.pWin  + wc.pDraw * drawSplitOur;
    const winPct     = Math.round(wc.pWin  * 100);
    const drawPct    = Math.round(wc.pDraw * 100);
    const lossPct    = Math.max(0, 100 - winPct - drawPct);
    const winAdjPct  = Math.round(pWinAdj * 100);
    const lossAdjPct = 100 - winAdjPct;

    const drawBg = drawSplitOur >= 1.0
        ? 'linear-gradient(90deg,rgba(63,185,80,.35) 0%,rgba(63,185,80,.15) 100%)'
        : drawSplitOur <= 0.0
        ? 'linear-gradient(270deg,rgba(248,81,73,.35) 0%,rgba(248,81,73,.15) 100%)'
        : 'rgba(139,148,158,.15)';
    const drawTextColor = drawSplitOur >= 1.0 ? 'var(--green)' : drawSplitOur <= 0.0 ? 'var(--red)' : 'var(--muted)';
    const drawStatLabel = drawSplitOur >= 1.0 ? 'Via dest. (us)' : drawSplitOur <= 0.0 ? 'Via dest. (them)' : 'Via dest.';
    const barCols = drawPct > 0
        ? `${Math.max(winPct,5)}fr ${Math.max(drawPct,2)}fr ${Math.max(lossPct,5)}fr`
        : `${Math.max(winAdjPct,5)}fr 0fr ${Math.max(lossAdjPct,5)}fr`;
    const drawSpan = drawPct >= 6 ? `<span class="wc-prob-pct" style="color:${drawTextColor};font-size:12px;">${drawPct}%</span>` : '';
    const barHtml = `
        <div style="display:flex;justify-content:space-between;padding:0 4px 6px;">
            <span style="font-size:12px;font-weight:600;color:var(--green);">${escapeHTML(ourName)}</span>
            <span style="font-size:12px;font-weight:600;color:var(--red);">${escapeHTML(oppName)}</span>
        </div>
        <div class="wc-prob-bar" style="margin:0;height:40px;grid-template-columns:${barCols};">
            <div class="wc-half-win"><span class="wc-prob-pct">${winAdjPct}%</span></div>
            <div class="wc-half-draw" style="background:${drawBg};">${drawSpan}</div>
            <div class="wc-half-loss"><span class="wc-prob-pct">${lossAdjPct}%</span></div>
        </div>`;

    let guaranteeHtml = '';
    if (wc.ourStars > wc.oppMax) {
        guaranteeHtml = `<div class="wc-guarantee" style="color:var(--green);">✓ Win guaranteed — opponent cannot bridge the ${wc.ourStars - wc.oppMax}★ gap even with all 3★</div>`;
    } else if (wc.oppStars > wc.ourMax) {
        guaranteeHtml = `<div class="wc-guarantee" style="color:var(--red);">✗ Win impossible — even with all remaining 3★ you still trail by ${wc.oppStars - wc.ourMax}★</div>`;
    } else if (winAdjPct >= 100) {
        guaranteeHtml = `<div class="wc-guarantee" style="color:var(--green);">✓ Win guaranteed — opponent cannot reach your destruction% even with ${wc.oppRem} perfect attack${wc.oppRem !== 1 ? 's' : ''}</div>`;
    } else if (lossAdjPct >= 100) {
        if (ourMaxFinalPct < oppPct)
            guaranteeHtml = `<div class="wc-guarantee" style="color:var(--red);">✗ Win impossible — you cannot reach their destruction% even with ${wc.ourRem} perfect attack${wc.ourRem !== 1 ? 's' : ''}</div>`;
        else if (drawSplitOur <= 0.0)
            guaranteeHtml = `<div class="wc-guarantee" style="color:var(--red);">⚠ &lt;1% win chance — trailing on destruction% (all ties go to them) · unfavorable star matchup</div>`;
        else
            guaranteeHtml = `<div class="wc-guarantee" style="color:var(--red);">⚠ &lt;1% win chance — very unfavorable matchup</div>`;
    } else {
        const ourNeeded = Math.max(0, wc.oppMax - wc.ourStars + 1);
        const oppNeeded = Math.max(0, wc.ourMax - wc.oppStars + 1);
        guaranteeHtml = `<div class="wc-guarantee" style="color:var(--muted);">Need <strong style="color:var(--green)">${ourNeeded}★</strong> more to lock win · Opp needs <strong style="color:var(--red)">${oppNeeded}★</strong> more to lock win</div>`;
    }

    const ourExpAdd = wc.ourBreakdown.reduce((s, a) => s + a.expStars, 0);
    const oppExpAdd = wc.oppBreakdown.reduce((s, a) => s + a.expStars, 0);
    const bodyHtml = `
        ${guaranteeHtml}
        <div class="wc-stats-row">
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:var(--green);">${winAdjPct}%</div><div class="wc-stat-lbl">Win</div></div>
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:${drawTextColor};">${drawPct}%</div><div class="wc-stat-lbl">${drawStatLabel}</div></div>
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:var(--red);">${lossAdjPct}%</div><div class="wc-stat-lbl">Loss</div></div>
        </div>
        <div class="wc-details">
            <div class="wc-detail-box">
                <div class="wc-detail-title">Current Score</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val" style="color:var(--green);">${wc.ourStars}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val" style="color:var(--red);">${wc.oppStars}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Lead</span><span class="wc-detail-val" style="color:${wc.ourStars >= wc.oppStars ? 'var(--green)' : 'var(--red)'};">${wc.ourStars > wc.oppStars ? '+' : ''}${wc.ourStars - wc.oppStars}★</span></div>
            </div>
            <div class="wc-detail-box">
                <div class="wc-detail-title">Remaining Attacks</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val" style="color:var(--green);">${wc.ourRem}</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val" style="color:var(--red);">${wc.oppRem}</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Avg TH (rem.)</span><span class="wc-detail-val"><span style="color:var(--green);">${wc.avgOurRemTH}</span><span style="color:var(--muted);"> vs </span><span style="color:var(--red);">${wc.avgOppRemTH}</span></span></div>
            </div>
            <div class="wc-detail-box">
                <div class="wc-detail-title">Star Range</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val">${wc.ourStars}→<span style="color:var(--green);">${wc.ourMax}</span>★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val">${wc.oppStars}→<span style="color:var(--red);">${wc.oppMax}</span>★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Max possible</span><span class="wc-detail-val" style="color:var(--muted);">${wc.maxPossible}★</span></div>
            </div>
            <div class="wc-detail-box">
                <div class="wc-detail-title">Expected Final</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val" style="color:var(--green);">${wc.expOurFinal.toFixed(1)}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val" style="color:var(--red);">${wc.expOppFinal.toFixed(1)}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Exp. lead</span><span class="wc-detail-val" style="color:${wc.expOurFinal >= wc.expOppFinal ? 'var(--green)' : 'var(--red)'};">${wc.expOurFinal > wc.expOppFinal ? '+' : ''}${(wc.expOurFinal - wc.expOppFinal).toFixed(1)}★</span></div>
            </div>
        </div>
        ${buildStarDistChart(wc, ourName, oppName)}
        <div style="border-top:1px solid var(--bord2);">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px 10px 20px;cursor:pointer;user-select:none;" onclick="${toggleFn}('${ourAtkId}', this)">
                <span style="font-size:12px;font-weight:600;color:var(--green);">▸ Our ${wc.ourRem} remaining attack${wc.ourRem !== 1 ? 's' : ''}</span>
                <span style="font-size:10px;color:var(--muted);">Exp. +${ourExpAdd.toFixed(1)}★ → ${wc.expOurFinal.toFixed(1)}★ total</span>
            </div>
            <div id="${ourAtkId}" style="display:none;">${buildAttackerTable(wc.ourBreakdown, 'our')}</div>
        </div>
        <div style="border-top:1px solid var(--bord2);border-bottom:1px solid var(--bord2);">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px 10px 20px;cursor:pointer;user-select:none;" onclick="${toggleFn}('${oppAtkId}', this)">
                <span style="font-size:12px;font-weight:600;color:var(--red);">▸ Their ${wc.oppRem} remaining attack${wc.oppRem !== 1 ? 's' : ''}</span>
                <span style="font-size:10px;color:var(--muted);">Exp. +${oppExpAdd.toFixed(1)}★ → ${wc.expOppFinal.toFixed(1)}★ total</span>
            </div>
            <div id="${oppAtkId}" style="display:none;">${buildAttackerTable(wc.oppBreakdown, 'opp')}</div>
        </div>`;
    return { barHtml, bodyHtml, winAdjPct };
}

// Pre-war prediction panel renderer — shared between war and CWL compare modals.
// Returns { probBarHtml, bodyHtml, winPct }.
// probBarHtml → names + raw prob bar (callers prepend their own page-specific header to barEl).
// bodyHtml    → stats, details, chart, breakdown toggles.
function buildPredictionBodyHTML(wc, ourName, oppName, ourAtkId, oppAtkId, toggleFn) {
    const winPct  = Math.round(wc.pWin  * 100);
    const drawPct = Math.round(wc.pDraw * 100);
    const lossPct = Math.max(0, 100 - winPct - drawPct);
    const expOurAdd = wc.ourBreakdown.reduce((s, p) => s + p.expStars, 0);
    const expOppAdd = wc.oppBreakdown.reduce((s, p) => s + p.expStars, 0);
    const drawSpan = drawPct >= 8 ? `<span class="wc-prob-pct">${drawPct}%</span>` : '';

    const probBarHtml = `
        <div style="display:flex;justify-content:space-between;padding:0 4px 6px;">
            <span style="font-size:12px;font-weight:600;color:var(--green);">${escapeHTML(ourName)}</span>
            <span style="font-size:12px;font-weight:600;color:var(--red);">${escapeHTML(oppName)}</span>
        </div>
        <div class="wc-prob-bar" style="margin:0;height:40px;grid-template-columns:${Math.max(winPct,5)}fr ${Math.max(drawPct,2)}fr ${Math.max(lossPct,5)}fr;">
            <div class="wc-half-win"><span class="wc-prob-pct">${winPct}%</span></div>
            <div class="wc-half-draw">${drawSpan}</div>
            <div class="wc-half-loss"><span class="wc-prob-pct">${lossPct}%</span></div>
        </div>`;

    const drawNote = drawPct > 1 ? `<div style="text-align:center;font-size:11px;color:var(--muted);margin:10px 0 4px;">Draw: ${drawPct}% · destruction tiebreaker not modeled</div>` : '';
    const bodyHtml = `
        ${drawNote}
        <div class="wc-stats-row">
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:var(--green);">${winPct}%</div><div class="wc-stat-lbl">Win</div></div>
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:var(--muted);">${drawPct}%</div><div class="wc-stat-lbl">Draw</div></div>
            <div class="wc-stat-box"><div class="wc-stat-val" style="color:var(--red);">${lossPct}%</div><div class="wc-stat-lbl">Loss</div></div>
        </div>
        <div class="wc-details">
            <div class="wc-detail-box">
                <div class="wc-detail-title">Expected Final</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val" style="color:var(--green);">${wc.expOurFinal.toFixed(1)}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val" style="color:var(--red);">${wc.expOppFinal.toFixed(1)}★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Exp. lead</span><span class="wc-detail-val" style="color:${wc.expOurFinal >= wc.expOppFinal ? 'var(--green)' : 'var(--red)'};">${wc.expOurFinal > wc.expOppFinal ? '+' : ''}${(wc.expOurFinal - wc.expOppFinal).toFixed(1)}★</span></div>
            </div>
            <div class="wc-detail-box">
                <div class="wc-detail-title">Star Range</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val">0→<span style="color:var(--green);">${wc.ourMax}</span>★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val">0→<span style="color:var(--red);">${wc.oppMax}</span>★</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">Max possible</span><span class="wc-detail-val" style="color:var(--muted);">${wc.maxPossible}★</span></div>
            </div>
            <div class="wc-detail-box">
                <div class="wc-detail-title">Avg TH</div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(ourName)}</span><span class="wc-detail-val" style="color:var(--green);">${wc.avgOurRemTH}</span></div>
                <div class="wc-detail-row"><span class="wc-detail-key">${escapeHTML(oppName)}</span><span class="wc-detail-val" style="color:var(--red);">${wc.avgOppRemTH}</span></div>
            </div>
        </div>
        ${buildStarDistChart(wc, ourName, oppName)}
        <div style="border-top:1px solid var(--bord2);">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px 10px 20px;cursor:pointer;user-select:none;" onclick="${toggleFn}('${ourAtkId}', this)">
                <span style="font-size:12px;font-weight:600;color:var(--green);">▸ Our ${wc.ourRem} attack${wc.ourRem !== 1 ? 's' : ''}</span>
                <span style="font-size:10px;color:var(--muted);">Exp. ${expOurAdd.toFixed(1)}★ total</span>
            </div>
            <div id="${ourAtkId}" style="display:none;">${buildAttackerTable(wc.ourBreakdown, 'our')}</div>
        </div>
        <div style="border-top:1px solid var(--bord2);border-bottom:1px solid var(--bord2);">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px 10px 20px;cursor:pointer;user-select:none;" onclick="${toggleFn}('${oppAtkId}', this)">
                <span style="font-size:12px;font-weight:600;color:var(--red);">▸ Their ${wc.oppRem} attack${wc.oppRem !== 1 ? 's' : ''}</span>
                <span style="font-size:10px;color:var(--muted);">Exp. ${expOppAdd.toFixed(1)}★ total</span>
            </div>
            <div id="${oppAtkId}" style="display:none;">${buildAttackerTable(wc.oppBreakdown, 'opp')}</div>
        </div>`;
    return { probBarHtml, bodyHtml, winPct };
}

function escapeHTML(s) {
    return String(s || '').replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function avg(arr) { return arr.length ? arr.reduce((a,b) => a+b,0) / arr.length : 0; }
function clamp(v,lo,hi) { return Math.max(lo, Math.min(hi, v)); }
function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }

function renderStars(n, big) {
    n = parseInt(n) || 0;
    const sz = big ? '1.18em' : '1.0em';
    return `<span style="font-size:${sz};letter-spacing:1px;color:var(--yellow)">${'★'.repeat(n)}</span>`
         + `<span style="font-size:${sz};letter-spacing:1px;color:var(--muted);opacity:.4">${'☆'.repeat(3-n)}</span>`;
}

const ATTACK_LABEL_MAP = {
    'clear':           ['Clear',          'ap-clear'],
    'failed_clear':    ['Failed Clear',    'ap-failed-clear'],
    'high_clear':      ['High Clear',      'ap-high-clear'],
    'farm':            ['Farm',            'ap-farm'],
    'failed_farm':     ['Failed Farm',     'ap-failed-farm'],
    'low_clear':       ['Low Clear',       'ap-low-clear'],
    'low_clear_fail':  ['Low Clear Fail',  'ap-low-clear-fail'],
    'clean_up':        ['Clean Up',        'ap-clean-up'],
    'failed_clean_up': ['Failed Clean Up', 'ap-failed-clean-up'],
    'wasted':          ['Wasted',          'ap-wasted'],
    'no_attack':       ['No Attack',       'ap-no-attack'],
};
function renderAttackLabel(label) {
    const e = ATTACK_LABEL_MAP[label];
    return e ? `<span class="atk-pill ${e[1]}">${e[0]}</span>` : `<span class="atk-pill ap-wasted">${label}</span>`;
}

// Toggle a collapsible breakdown section; replaces the leading arrow in the first span.
function toggleBreakdown(id, hdr) {
    const el = document.getElementById(id);
    if (!el) return;
    const opening = el.style.display !== 'block';
    el.style.display = opening ? 'block' : 'none';
    const span = hdr ? hdr.querySelector('span:first-child') : null;
    if (span) span.textContent = span.textContent.replace(/^[▸▾]\s*/, opening ? '▾ ' : '▸ ');
}

// Equalize heights of paired member rows between left/right roster cards in a grid element.
function equalizeRoster(gridEl) {
    if (!gridEl) return;
    const cards = gridEl.querySelectorAll('.roster-card');
    if (cards.length < 2) return;
    const L = cards[0].querySelectorAll('.member-row');
    const R = cards[1].querySelectorAll('.member-row');
    L.forEach(r => r.style.height = '');
    R.forEach(r => r.style.height = '');
    const n = Math.min(L.length, R.length);
    for (let i = 0; i < n; i++) {
        const h = Math.max(L[i].offsetHeight, R[i].offsetHeight);
        L[i].style.height = R[i].style.height = h + 'px';
    }
}

// ── Shared war-card registry (attack data per round/war) ─────────────────────
const warCardData = {};
function registerWarCard(n, data) { warCardData[n] = data; }

// ── Toggle win-probability section (shared, calls page-defined buildWinCalc) ─
function toggleWinCalc(n) {
    const body = document.getElementById('wcBody-' + n);
    const chev = document.getElementById('wcChev-' + n);
    if (!body) return;
    const opening = body.style.display !== 'block';
    body.style.display = opening ? 'block' : 'none';
    if (chev) chev.classList.toggle('open', opening);
    if (opening && !document.getElementById('winCalc-' + n)?.innerHTML.trim()) buildWinCalc(n);
}

// ── Toggle attack log section ─────────────────────────────────────────────────
function toggleLog(n) {
    const body    = document.getElementById('logBody-' + n);
    const chevron = document.getElementById('logChevron-' + n);
    if (!body || !chevron) return;
    const opening = body.style.display === 'none' || !body.style.display;
    body.style.display = opening ? 'block' : 'none';
    chevron.classList.toggle('open', opening);
    if (opening && !body.innerHTML.trim())
        body.innerHTML = buildAttackLogHTML((warCardData[n] || {}).attacks || []);
}

// ── Roster grid (connection lines + row selection) ────────────────────────────
const rosterState = {};
const _rosterRebuild = {};

// Single document-level click handler — clears every active roster selection.
document.addEventListener('click', () => {
    Object.keys(_rosterRebuild).forEach(k => {
        const key = Number(k);
        if (rosterState[key]?.size) { rosterState[key].clear(); _rosterRebuild[key](); }
    });
});

// Top-level so it doesn't get overwritten on each initRoster call.
function toggleAllSide(btn, event, rn) {
    event.stopPropagation();
    const card = btn.closest('.roster-card');
    const tags = [...card.querySelectorAll('.member-row[data-tag]')].map(r => r.dataset.tag);
    const allSel = tags.every(t => rosterState[rn].has(t));
    if (allSel) tags.forEach(t => rosterState[rn].delete(t));
    else tags.forEach(t => rosterState[rn].add(t));
    if (_rosterRebuild[rn]) _rosterRebuild[rn]();
}

function initRoster(n) {
    const grid = document.getElementById('rosterGrid-' + n); if (!grid) return;
    const svg  = document.getElementById('warConnections-' + n);
    const atkPer = parseInt(grid.dataset.atkPer || '1');
    rosterState[n] = new Set();
    const TGT = ['row-tgt-3','row-tgt-2','row-tgt-1','row-tgt-0','row-tgt-open'];

    function getPos(row) {
        const gr = grid.getBoundingClientRect(), rr = row.getBoundingClientRect();
        return { left: rr.left-gr.left, right: rr.right-gr.left, y: rr.top-gr.top+rr.height/2 };
    }
    function syncButtons() {
        grid.querySelectorAll('.toggle-all-btn').forEach(btn => {
            const card = btn.closest('.roster-card');
            const tags = [...card.querySelectorAll('.member-row[data-tag]')].map(r => r.dataset.tag);
            const allSel = tags.length > 0 && tags.every(t => rosterState[n].has(t));
            btn.textContent = allSel ? 'Deselect All' : 'Select All';
            btn.classList.toggle('active', tags.some(t => rosterState[n].has(t)));
        });
    }
    function rebuild() {
        if (svg) svg.innerHTML = '';
        grid.querySelectorAll('.member-row').forEach(r => r.classList.remove('row-sel', 'row-dim', ...TGT));
        syncButtons();
        if (!rosterState[n].size) return;
        const cards = grid.querySelectorAll('.roster-card');
        rosterState[n].forEach(tag => {
            const row = grid.querySelector(`.member-row[data-tag="${CSS.escape(tag)}"]`); if (!row) return;
            row.classList.add('row-sel');
            const isLeft = cards[0] && cards[0].contains(row);
            const srcPos = getPos(row);
            JSON.parse(row.dataset.attacks || '[]').forEach(atk => {
                const defRow = grid.querySelector(`.member-row[data-tag="${CSS.escape(atk.tag)}"]`); if (!defRow) return;
                defRow.classList.add('row-tgt-' + atk.stars);
                const dstPos = getPos(defRow);
                if (svg) drawSVGCurve(svg, isLeft?srcPos.right+2:srcPos.left-2, srcPos.y, isLeft?dstPos.left-2:dstPos.right+2, dstPos.y, atk.stars, false);
            });
            JSON.parse(row.dataset.defendedBy || '[]').forEach(atk => {
                const atkRow = grid.querySelector(`.member-row[data-tag="${CSS.escape(atk.tag)}"]`); if (!atkRow) return;
                atkRow.classList.add('row-tgt-' + atk.stars);
                const atkPos = getPos(atkRow);
                if (svg) drawSVGCurve(svg, isLeft?atkPos.left-2:atkPos.right+2, atkPos.y, isLeft?srcPos.right+2:srcPos.left-2, srcPos.y, atk.stars, true);
            });
            if (JSON.parse(row.dataset.attacks || '[]').length < atkPer) {
                const oppCard = isLeft ? cards[1] : cards[0];
                if (oppCard) oppCard.querySelectorAll('.member-row[data-tag]').forEach(oppRow => {
                    if (TGT.some(c => oppRow.classList.contains(c))) return;
                    const recv = JSON.parse(oppRow.dataset.defendedBy || '[]');
                    if (Math.max(...recv.map(a => a.stars), 0) < 3) {
                        oppRow.classList.add('row-tgt-open');
                        const dstPos = getPos(oppRow);
                        if (svg) drawSVGPotential(svg, isLeft?srcPos.right+2:srcPos.left-2, srcPos.y, isLeft?dstPos.left-2:dstPos.right+2, dstPos.y);
                    }
                });
            }
        });
        grid.querySelectorAll('.member-row').forEach(r => {
            if (!r.classList.contains('row-sel') && !TGT.some(c => r.classList.contains(c))) r.classList.add('row-dim');
        });
    }

    _rosterRebuild[n] = rebuild;

    grid.querySelectorAll('.member-row[data-tag]').forEach(r => {
        r.addEventListener('click', e => {
            e.stopPropagation();
            const tag = r.dataset.tag;
            if (rosterState[n].has(tag)) rosterState[n].delete(tag); else rosterState[n].add(tag);
            rebuild();
        });
    });
}

// Build attack log table HTML from an attacks array.
function buildAttackLogHTML(attacks) {
    if (!attacks.length) return '<div style="padding:16px;color:var(--muted);font-size:13px;">No attacks recorded yet.</div>';
    const rows = [...attacks].reverse().map(a => {
        const nc = a.attacker_side === 'our' ? 'var(--green)' : 'var(--red)';
        const sc = a.stars===3?'var(--green)':a.stars===2?'var(--yellow)':a.stars===1?'var(--accent)':'var(--muted)';
        return `<tr>
            <td style="color:var(--muted);font-family:'Rajdhani',sans-serif;font-weight:700;text-align:center">${a.attacker_pos}</td>
            <td style="font-weight:600;color:${nc}">${escapeHTML(a.attacker_name)}</td>
            <td style="color:var(--muted);font-size:11px;text-align:center">TH${a.attacker_th}</td>
            <td style="color:var(--muted);text-align:center;font-size:13px">→</td>
            <td style="color:var(--muted);font-family:'Rajdhani',sans-serif;font-weight:700;text-align:center">${a.defender_pos}</td>
            <td style="font-weight:600">${escapeHTML(a.defender_name)}</td>
            <td style="color:var(--muted);font-size:11px;text-align:center">TH${a.defender_th}</td>
            <td>${renderStars(a.stars)}</td>
            <td style="font-family:'Rajdhani',sans-serif;font-weight:700;color:${sc}">${a.pct}%</td>
            <td>${renderAttackLabel(a.label)}</td>
        </tr>`;
    }).join('');
    return `<div class="log-scroll"><div class="table-scroll"><table class="detail-table">
        <thead><tr><th>#</th><th>Attacker</th><th>TH</th><th></th><th>#</th><th>Defender</th><th>TH</th><th>Stars</th><th>Dest%</th><th>Verdict</th></tr></thead>
        <tbody>${rows}</tbody>
    </table></div></div>`;
}

// SVG roster connection drawing helpers — used by both war IIFE and CWL initRoster.
function starColor(s) { return s===3?'#3fb950':s===2?'#e3b341':s===1?'#f0a500':'#8b949e'; }

function drawSVGCurve(svg, x1, y1, x2, y2, stars, dashed) {
    const color = starColor(stars), cx = (x1+x2)/2;
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
    path.setAttribute('stroke',color); path.setAttribute('stroke-width',dashed?'1.5':'2');
    path.setAttribute('fill','none'); path.setAttribute('stroke-opacity',dashed?'0.5':'0.9');
    if (dashed) path.setAttribute('stroke-dasharray','6 4');
    if (!dashed) {
        const len = 200;
        path.style.strokeDasharray = len; path.style.strokeDashoffset = len;
        svg.appendChild(path);
        requestAnimationFrame(()=>{ path.style.transition='stroke-dashoffset 0.4s ease'; path.style.strokeDashoffset='0'; });
    } else {
        path.style.opacity='0'; path.style.transition='opacity 0.3s ease';
        svg.appendChild(path);
        requestAnimationFrame(()=>{ path.style.opacity='1'; });
    }
    const dot = document.createElementNS('http://www.w3.org/2000/svg','circle');
    dot.setAttribute('cx',x2); dot.setAttribute('cy',y2); dot.setAttribute('r',dashed?'4':'5');
    dot.setAttribute('fill',dashed?'none':color);
    if (dashed) { dot.setAttribute('stroke',color); dot.setAttribute('stroke-width','1.5'); }
    dot.style.opacity='0'; dot.style.transition='opacity 0.2s ease 0.38s';
    svg.appendChild(dot);
    requestAnimationFrame(()=>{ dot.style.opacity=dashed?'0.7':'0.9'; });
}

function drawSVGPotential(svg, x1, y1, x2, y2) {
    const cx = (x1+x2)/2;
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
    path.setAttribute('stroke','#58a6ff'); path.setAttribute('stroke-width','1.5');
    path.setAttribute('fill','none'); path.setAttribute('stroke-opacity','0.35');
    path.setAttribute('stroke-dasharray','4 5');
    path.style.opacity='0'; path.style.transition='opacity 0.3s ease';
    svg.appendChild(path);
    requestAnimationFrame(()=>{ path.style.opacity='1'; });
}

function closeMatchupRatesModal() {
    document.getElementById('mrBackdrop').style.display = 'none';
    document.getElementById('mrModal').style.display    = 'none';
}

function closePlayerMatchupRatesModal() {
    document.getElementById('pmrBackdrop').style.display = 'none';
    document.getElementById('pmrModal').style.display    = 'none';
}

// Open the player matchup history modal.
// history: {tag: {"atkTH_defTH": {counts:[c0,c1,c2,c3], total:N}}}
// nameMap: {tag: {name, th}}  — used for display; tags absent from nameMap show raw tag.
function openPlayerMatchupRatesModal(history, nameMap) {
    const bd = document.getElementById('pmrBackdrop');
    const modal = document.getElementById('pmrModal');
    if (!bd || !modal) return;
    const el = document.getElementById('pmrContent');
    if (el && !el.innerHTML.trim()) {
        const pct = v => `${Math.round(v * 100)}%`;
        const bar = d => {
            const s = d.reduce((a, b) => a + b, 0) || 1;
            return `<div style="display:flex;height:8px;width:110px;border-radius:3px;overflow:hidden;gap:1px;">
                <div style="flex:${d[0]/s||0.001};background:#8b949e;" title="0★: ${pct(d[0]/s)}"></div>
                <div style="flex:${d[1]/s||0.001};background:#f0a500;" title="1★: ${pct(d[1]/s)}"></div>
                <div style="flex:${d[2]/s||0.001};background:#e3b341;" title="2★: ${pct(d[2]/s)}"></div>
                <div style="flex:${d[3]/s||0.001};background:#3fb950;" title="3★: ${pct(d[3]/s)}"></div>
            </div>`;
        };

        // Only show players in the nameMap (our clan members), sorted by total attacks desc.
        const players = Object.entries(history)
            .filter(([tag]) => nameMap[tag])
            .map(([tag, matchups]) => {
                const info = nameMap[tag];
                const rows = Object.entries(matchups)
                    .map(([key, {counts, total}]) => {
                        if (!total) return null;
                        const [atkTH, defTH] = key.split('_').map(Number);
                        const avg = counts.reduce((s, c, k) => s + c * k, 0) / total;
                        return { atkTH, defTH, counts, total, avg };
                    })
                    .filter(Boolean)
                    .sort((a, b) => b.atkTH - a.atkTH || b.defTH - a.defTH);
                const totalAtks = rows.reduce((s, r) => s + r.total, 0);
                return { tag, name: info.name, th: info.th, rows, totalAtks };
            })
            .filter(p => p.totalAtks > 0)
            .sort((a, b) => b.totalAtks - a.totalAtks);

        if (!players.length) {
            el.innerHTML = '<div style="padding:20px;color:var(--muted);">No player history recorded yet.</div>';
        } else {
            const grandTotal = players.reduce((s, p) => s + p.totalAtks, 0);
            const _ts = new Date().toLocaleTimeString();
            let html = `<div style="font-size:12px;color:var(--muted);margin-bottom:18px;">
                ${players.length} players &nbsp;&#183;&nbsp;
                <strong style="color:var(--accent);font-family:'Rajdhani',sans-serif;font-size:15px;">${grandTotal.toLocaleString()}</strong> total attacks recorded
                &nbsp;&#183;&nbsp; <span style="font-size:10px;">snapshotted ${_ts}</span>
            </div><div style="overflow-x:auto;"><table class="detail-table" style="width:100%;">
            <thead><tr>
                <th style="text-align:center;">ATK TH</th>
                <th style="text-align:center;">DEF TH</th>
                <th>★ DISTRIBUTION</th>
                <th style="text-align:center;color:#8b949e;">0★</th>
                <th style="text-align:center;color:#f0a500;">1★</th>
                <th style="text-align:center;color:#e3b341;">2★</th>
                <th style="text-align:center;color:#3fb950;">3★</th>
                <th style="text-align:right;">ATKS</th>
                <th style="text-align:right;">AVG★</th>
            </tr></thead><tbody>`;

            for (const p of players) {
                // Player header row — full-width separator with name, current TH, total attacks.
                html += `<tr style="background:var(--bord2);">
                    <td colspan="9" style="padding:7px 12px;font-weight:700;font-size:13px;">
                        ${escapeHTML(p.name)}
                        ${p.th ? `<span style="font-family:'Rajdhani',sans-serif;font-weight:700;color:var(--accent);margin-left:6px;">TH${p.th}</span>` : ''}
                        <span style="font-size:11px;color:var(--muted);font-weight:400;margin-left:10px;">${p.totalAtks} attack${p.totalAtks !== 1 ? 's' : ''}</span>
                    </td>
                </tr>`;
                let lastAtkTH = null;
                for (const r of p.rows) {
                    if (r.atkTH !== lastAtkTH) {
                        lastAtkTH = r.atkTH;
                        html += `<tr style="background:var(--bg);">
                            <td colspan="9" style="padding:4px 12px;font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.5px;">
                                ATTACKING AS TH${r.atkTH}
                            </td>
                        </tr>`;
                    }
                    const s = r.total || 1;
                    const avgColor = r.avg >= 2.7 ? 'var(--green)' : r.avg >= 2.0 ? 'var(--accent)' : 'var(--red)';
                    html += `<tr>
                        <td style="text-align:center;font-family:'Rajdhani',sans-serif;font-weight:700;color:var(--accent);">TH${r.atkTH}</td>
                        <td style="text-align:center;font-size:12px;color:var(--muted);">TH${r.defTH}</td>
                        <td>${bar(r.counts)}</td>
                        <td style="text-align:center;font-size:11px;color:#8b949e;">${pct(r.counts[0]/s)}</td>
                        <td style="text-align:center;font-size:11px;color:#f0a500;">${pct(r.counts[1]/s)}</td>
                        <td style="text-align:center;font-size:11px;color:#e3b341;">${pct(r.counts[2]/s)}</td>
                        <td style="text-align:center;font-size:11px;color:#3fb950;">${pct(r.counts[3]/s)}</td>
                        <td style="text-align:right;font-size:11px;color:var(--muted);">${r.total}</td>
                        <td style="text-align:right;font-family:'Rajdhani',sans-serif;font-weight:700;color:${avgColor};">${r.avg.toFixed(2)}★</td>
                    </tr>`;
                }
            }
            html += '</tbody></table></div>';
            el.innerHTML = html;
        }
    }
    bd.style.display = 'block';
    modal.style.display = 'block';
}

// ── Shared Compare & Predict ─────────────────────────────────────────────────
// Builds all five compare sections and returns them as HTML strings.
// meta: { ourName, oppName, warsWonOur, warsWonOpp, streakOur, streakOpp,
//         winPct?, lossPct? }
// winPct/lossPct are optional — if omitted a simple sigmoid is used as fallback.
function buildCompareHTML(our, opp, meta) {
    const len = Math.min(our.length, opp.length);
    const ourNameSafe = escapeHTML(meta.ourName);
    const oppNameSafe = escapeHTML(meta.oppName);

    // ── Analysis ─────────────────────────────────────────────────────────────
    const avgThOur = avg(our.map(m => m.th));
    const avgThOpp = avg(opp.map(m => m.th));

    let thDiffTotal = 0, thBetter = 0, thEven = 0, thWorse = 0;
    for (let i = 0; i < len; i++) {
        const d = our[i].th - opp[i].th;
        thDiffTotal += d;
        if (d > 0) thBetter++; else if (d < 0) thWorse++; else thEven++;
    }
    const safeLen   = Math.max(len, 1);
    const thDiffAvg = thDiffTotal / safeLen;
    const posScore  = (thBetter - thWorse) / safeLen;

    const avgLrOur   = avg(our.slice(0, len).map(m => m.lr).filter(r => r > 0));
    const avgLrOpp   = avg(opp.slice(0, len).map(m => m.lr).filter(r => r > 0));
    const leagueDiff = (avgLrOur - avgLrOpp) / 36;

    const maxWins    = Math.max(meta.warsWonOur, meta.warsWonOpp, 1);
    const warsScore  = (Math.log(meta.warsWonOur + 1) - Math.log(meta.warsWonOpp + 1)) / Math.log(maxWins + 1);
    const maxStreak  = Math.max(meta.streakOur, meta.streakOpp, 1);
    const streakScore = (meta.streakOur - meta.streakOpp) / maxStreak;

    let lgBetter = 0, lgEven = 0, lgWorse = 0;
    for (let i = 0; i < len; i++) {
        const o = our[i], p = opp[i];
        if (o.lr > 0 && p.lr > 0) {
            const d = o.lr - p.lr;
            if (d > 0) lgBetter++; else if (d < 0) lgWorse++; else lgEven++;
        } else if (o.lr > 0) { lgBetter++;
        } else if (p.lr > 0) { lgWorse++;
        } else { lgEven++; }
    }
    const lgPosScore = (lgBetter - lgWorse) / Math.max(len, 1);

    let winPct = meta.winPct, lossPct = meta.lossPct;
    if (winPct == null) {
        const rawScore = thDiffAvg * 0.40 + posScore * 0.22 + leagueDiff * 2 * 0.18 + lgPosScore * 0.10 + warsScore * 0.05 + streakScore * 0.05;
        winPct  = Math.round(clamp(sigmoid(rawScore * 1.8), 0.25, 0.75) * 100);
        lossPct = 100 - winPct;
    }

    const verdict = winPct  > 54 ? `${ourNameSafe} have a statistical edge in this matchup.`
                  : lossPct > 54 ? `${oppNameSafe} have a statistical edge in this matchup.`
                  : 'This looks like an even matchup — could go either way.';

    // ── 1. Prediction ─────────────────────────────────────────────────────────
    function factorCard(label, ov, pv, score) {
        const cls = score > 0.05 ? 'pfr-win-our' : score < -0.05 ? 'pfr-win-opp' : '';
        return `<div class="pred-factor-row ${cls}"><div class="pfr-label">${label}</div><div class="pfr-vals"><span class="pfr-our">${ov}</span><span class="pfr-sep">vs</span><span class="pfr-opp">${pv}</span></div></div>`;
    }

    const prediction = `
        <div class="cmp-title">📊 War Prediction</div>
        <div class="pred-verdict" style="margin-bottom:16px;">${verdict}</div>
        <div class="pred-factors-grid">
            ${factorCard('Avg TH', avgThOur.toFixed(1), avgThOpp.toFixed(1), thDiffAvg)}
            ${factorCard('TH Positions Ahead', `+${thBetter} ahead`, `+${thWorse} ahead`, posScore)}
            ${factorCard('Avg League Rank', avgLrOur > 0 ? avgLrOur.toFixed(1) : '—', avgLrOpp > 0 ? avgLrOpp.toFixed(1) : '—', avgLrOur - avgLrOpp)}
            ${factorCard('League Positions Ahead', `+${lgBetter} ahead`, `+${lgWorse} ahead`, lgPosScore)}
            ${factorCard('Wars Won', meta.warsWonOur, meta.warsWonOpp, warsScore)}
            ${factorCard('Win Streak', meta.streakOur || '—', meta.streakOpp || '—', streakScore)}
        </div>`;

    // ── 2. Key Stats ──────────────────────────────────────────────────────────
    function statRow(label, ov, pv, hb = true) {
        const diff = parseFloat(ov) - parseFloat(pv);
        const ow = hb ? diff > 0.01 : diff < -0.01;
        const pw = hb ? diff < -0.01 : diff > 0.01;
        return `<div class="stat-cmp-row"><div class="scr-our ${ow ? 'scr-win' : pw ? 'scr-lose' : ''}">${ov}</div><div class="scr-label">${label}</div><div class="scr-opp ${pw ? 'scr-win' : ow ? 'scr-lose' : ''}">${pv}</div></div>`;
    }

    const stats = `
        <div class="cmp-title">📋 Key Statistics</div>
        <div style="display:grid;grid-template-columns:1fr 140px 1fr;margin-bottom:8px;">
            <span style="font-size:11px;font-weight:600;color:var(--green)">${ourNameSafe}</span>
            <span></span>
            <span style="font-size:11px;font-weight:600;color:var(--red)">${oppNameSafe}</span>
        </div>
        ${statRow('AVG TH', avgThOur.toFixed(1), avgThOpp.toFixed(1))}
        ${statRow('TH POSITIONS AHEAD', thBetter, thWorse)}
        ${avgLrOur > 0 || avgLrOpp > 0 ? statRow('AVG LEAGUE RANK', avgLrOur > 0 ? avgLrOur.toFixed(1) : '—', avgLrOpp > 0 ? avgLrOpp.toFixed(1) : '—') : ''}
        ${lgBetter + lgWorse > 0 ? statRow('LEAGUE POSITIONS AHEAD', lgBetter, lgWorse) : ''}
        ${statRow('WARS WON', meta.warsWonOur ?? '—', meta.warsWonOpp ?? '—')}
        ${statRow('WIN STREAK', meta.streakOur ?? '—', meta.streakOpp ?? '—')}`;

    // ── 3. TH Distribution ────────────────────────────────────────────────────
    const thOur = {}, thOpp = {};
    our.forEach(m => { thOur[m.th] = (thOur[m.th] || 0) + 1; });
    opp.forEach(m => { thOpp[m.th] = (thOpp[m.th] || 0) + 1; });
    const allThs    = [...new Set([...Object.keys(thOur), ...Object.keys(thOpp)].map(Number))].sort((a, b) => b - a);
    const maxCount  = Math.max(...allThs.map(t => Math.max(thOur[t] || 0, thOpp[t] || 0)), 1);

    const th = `
        <div class="cmp-title"><img src="/static/img/townHall.png" style="width:14px;height:14px;vertical-align:middle;"> TH Distribution</div>
        <div class="dist-header"><span class="dist-our-lbl">${ourNameSafe}</span><span></span><span class="dist-opp-lbl">${oppNameSafe}</span></div>
        ${allThs.map(t => {
            const o = thOur[t] || 0, p = thOpp[t] || 0;
            const ow = Math.round(o / maxCount * 130), pw = Math.round(p / maxCount * 130);
            return `<div class="dist-row"><span class="dist-count-our">${o || ''}</span><div style="display:flex;justify-content:flex-end"><div class="dist-bar-our" style="width:${ow}px"></div></div><span class="dist-lbl">TH${t}</span><div><div class="dist-bar-opp" style="width:${pw}px"></div></div><span class="dist-count-opp">${p || ''}</span></div>`;
        }).join('')}`;

    // ── 4. League Comparison ──────────────────────────────────────────────────
    const lgRowsHtml = Array.from({length: len}, (_, i) => {
        const o = our[i], p = opp[i];
        const hasO = o.lr > 0, hasP = p.lr > 0;
        let rowCls = '', diffLabel = '—';
        if (hasO && hasP) {
            const d = o.lr - p.lr;
            if (d > 0)      { rowCls = 'lg-adv'; diffLabel = `+${d}`; }
            else if (d < 0) { rowCls = 'lg-dis'; diffLabel = `${d}`; }
            else            { rowCls = 'lg-even'; diffLabel = '='; }
        } else if (hasO) { rowCls = 'lg-adv'; diffLabel = '+'; }
        else if (hasP)   { rowCls = 'lg-dis'; diffLabel = '−'; }
        else             { rowCls = 'lg-even'; }
        const oLg = hasO ? escapeHTML(o.league) : '<span class="no-data-lg">—</span>';
        const pLg = hasP ? escapeHTML(p.league) : '<span class="no-data-lg">—</span>';
        return `<tr class="${rowCls}"><td class="lgt-pos">#${o.pos}</td><td class="lgt-name">${escapeHTML(o.name)}</td><td class="lgt-lg">${oLg}</td><td class="lgt-diff">${diffLabel}</td><td class="lgt-lg" style="text-align:right">${pLg}</td><td class="lgt-name" style="text-align:right">${escapeHTML(p.name)}</td></tr>`;
    }).join('');

    const league = `
        <div class="cmp-title">🎯 League Comparison</div>
        <div class="matchup-summary">
            <div class="matchup-stat"><div class="mn mn-green">${lgBetter}</div><div class="ml">Ahead</div></div>
            <div class="matchup-stat"><div class="mn mn-muted">${lgEven}</div><div class="ml">Even</div></div>
            <div class="matchup-stat"><div class="mn mn-red">${lgWorse}</div><div class="ml">Behind</div></div>
        </div>
        <table class="lg-table"><thead><tr><th>#</th><th style="text-align:left">${ourNameSafe}</th><th style="text-align:left">League</th><th style="text-align:center">Diff</th><th style="text-align:right">League</th><th style="text-align:right">${oppNameSafe}</th></tr></thead><tbody>${lgRowsHtml}</tbody></table>`;

    // ── 5. TH Matchup by Position ─────────────────────────────────────────────
    const matchupRowsHtml = Array.from({length: len}, (_, i) => {
        const o = our[i], p = opp[i], d = o.th - p.th;
        const rc = d > 0 ? 'lg-adv' : d < 0 ? 'lg-dis' : 'lg-even';
        const dc = d > 0 ? 'mt-adv' : d < 0 ? 'mt-dis' : 'mt-even';
        return `<tr class="${rc}"><td class="lgt-pos">#${o.pos}</td><td class="lgt-name">${escapeHTML(o.name)}</td><td class="lgt-lg">TH${o.th}</td><td class="lgt-diff ${dc}">${d > 0 ? '+' : ''}${d || '='}</td><td class="lgt-lg" style="text-align:right">TH${p.th}</td><td class="lgt-name" style="text-align:right">${escapeHTML(p.name)}</td></tr>`;
    }).join('');

    const matchup = `
        <div class="cmp-title"><img src="/static/img/battle.png" style="width:14px;height:14px;vertical-align:middle;"> TH Matchup by Position</div>
        <div class="matchup-summary">
            <div class="matchup-stat"><div class="mn mn-green">${thBetter}</div><div class="ml">Ahead</div></div>
            <div class="matchup-stat"><div class="mn mn-muted">${thEven}</div><div class="ml">Even</div></div>
            <div class="matchup-stat"><div class="mn mn-red">${thWorse}</div><div class="ml">Behind</div></div>
        </div>
        <table class="lg-table"><thead><tr><th>#</th><th style="text-align:left">${ourNameSafe}</th><th>TH</th><th style="text-align:center">Diff</th><th style="text-align:right">TH</th><th style="text-align:right">${oppNameSafe}</th></tr></thead><tbody>${matchupRowsHtml}</tbody></table>`;

    return { prediction, stats, th, league, matchup };
}
