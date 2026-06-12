// ── Shared war/CWL probability engine ────────────────────────────────────────
// Included by clanwar.html and cwl.html. Do not add page-specific code here.

// Fallback star distributions by TH diff (attacker - defender), clamped [-4, +4]
const _DIFF_FALLBACK = {
     4: [0.00, 0.01, 0.04, 0.95],
     3: [0.00, 0.02, 0.08, 0.90],
     2: [0.01, 0.02, 0.12, 0.85],
     1: [0.01, 0.03, 0.16, 0.80],
     0: [0.01, 0.04, 0.20, 0.75],
    '-1': [0.02, 0.08, 0.30, 0.60],
    '-2': [0.05, 0.15, 0.35, 0.45],
    '-3': [0.10, 0.25, 0.38, 0.27],
    '-4': [0.18, 0.35, 0.32, 0.15],
};

// Return [p0,p1,p2,p3] for an attacker TH vs defender TH from the given rates dict.
// Falls back to _DIFF_FALLBACK when the matchup has <5 recorded attacks.
function atkDist(rates, atkTH, defTH) {
    const d = rates[atkTH + '_' + defTH];
    if (d) return d;
    const diff = Math.max(-4, Math.min(4, atkTH - defTH));
    return _DIFF_FALLBACK[String(diff)] || _DIFF_FALLBACK['0'];
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

// Full win-probability calculation given pre-built attacker→defender pair lists.
// Each pair: { tag, atkTH, name, pos, defTH, defName, defPos? }
// The attack→defender mapping is the only thing callers differ on — everything else is shared.
function calcWinProb(ourPairs, oppPairs, ourStars, oppStars, maxPossible, playerInfoFn, atkDistFn, matchupCounts) {
    function buildSide(pairs) {
        const dists = [], breakdown = [];
        for (const p of pairs) {
            const { dist, srcLabel } = resolveAtkDist(playerInfoFn, atkDistFn, p.tag, p.atkTH, p.defTH, matchupCounts);
            dists.push(dist);
            const entry = { name: p.name, th: p.atkTH, pos: p.pos, defTH: p.defTH, defName: p.defName,
                            dist, expStars: dist.reduce((s, q, k) => s + q * k, 0), srcLabel };
            if (p.defPos !== undefined) entry.defPos = p.defPos;
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
    const expOurAdd = ourBreakdown.reduce((s, a) => s + a.expStars, 0);
    const expOppAdd = oppBreakdown.reduce((s, a) => s + a.expStars, 0);
    const avgTHfn   = arr => arr.length ? (arr.reduce((s, a) => s + a.th, 0) / arr.length).toFixed(1) : '—';
    return {
        pWin, pDraw, pLoss,
        ourStars, oppStars,
        ourRem: ourPairs.length, oppRem: oppPairs.length,
        ourMax: Math.min(ourStars + ourPairs.length * 3, maxPossible),
        oppMax: Math.min(oppStars + oppPairs.length * 3, maxPossible),
        expOurFinal: Math.min(ourStars + expOurAdd, maxPossible),
        expOppFinal: Math.min(oppStars + expOppAdd, maxPossible),
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

        let html = `<div style="font-size:12px;color:var(--muted);margin-bottom:18px;">
            Total attacks in DB: <strong style="color:var(--accent);font-family:'Rajdhani',sans-serif;font-size:15px;">${totalAtks.toLocaleString()}</strong>
            &nbsp;&#183;&nbsp; ${allKeys.length} matchup combinations
            &nbsp;&#183;&nbsp; <span style="color:var(--muted);font-size:11px;">&#9733; distribution shown for &#8805;5 attacks</span>
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
