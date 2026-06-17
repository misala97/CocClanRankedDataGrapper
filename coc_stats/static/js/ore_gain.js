/* Shared Ore Gain module — window.OreGain
 *
 * Usage:
 *   OreGain.init({ getBalance, getTotalCost })
 *   OreGain.open() / OreGain.close()
 *   OreGain.getDailyGain()          → { shiny, glowy, starry }
 *   OreGain.applyStarBonus(th, league)
 *   OreGain.applyWarStats(data)
 *   OreGain.applyCwlStats(data)
 *
 * getBalance   : optional () => { shiny, glowy, starry }  — current ore the player has
 * getTotalCost : optional () => { shiny, glowy, starry }  — total cost of the upgrade plan
 * Both default to zero; without them the "days to complete" panel stays hidden.
 */
window.OreGain = (function () {

    // ── Sources ──────────────────────────────────────────────────────────────
    let gainSources = [
        { id: 'star',   name: 'Star Bonus',      icon: '⭐', freq: 'daily',   shiny: 0,    glowy: 0,   starry: 0,  enabled: true,  th: 0, league: 'Unranked' },
        { id: 'war',    name: 'Clan War',        icon: '⚔️', freq: 'monthly', shiny: 0,    glowy: 0,   starry: 0,  enabled: true,  attacks: 0, wars: 0 },
        { id: 'cwl',    name: 'CWL',             icon: '🏆', freq: 'monthly', shiny: 0,    glowy: 0,   starry: 0,  enabled: true,  attacks: 0, wars: 0 },
        { id: 'trader', name: 'Trader (Medals)', icon: '🪙', freq: 'weekly',  shiny: 1000, glowy: 100, starry: 10, enabled: true,  shinyBuys: 2, glowyBuys: 2, starryBuys: 2 },
        { id: 'prosp',  name: 'Prospector',      icon: '⛏️', freq: 'monthly', shiny: 0,    glowy: 0,   starry: 0,  enabled: false, pairCounts: [0,0,0,0,0,0] },
        { id: 'custom', name: 'Custom',          icon: '✨', freq: 'monthly', shiny: 0,    glowy: 0,   starry: 0,  enabled: true },
    ];
    const GAIN_LS_KEY = 'coc_ore_gain';

    // ── Trader constants ─────────────────────────────────────────────────────
    const TRADER_BUNDLES = { shiny: 500, glowy: 50, starry: 5 };

    // ── Prospector constants ──────────────────────────────────────────────────
    const PROSP_PAIRS = [
        { give: 'shiny',  giveAmt: 2000, recv: 'glowy',  recvAmt: 120  },
        { give: 'shiny',  giveAmt: 2000, recv: 'starry', recvAmt: 2    },
        { give: 'glowy',  giveAmt: 120,  recv: 'shiny',  recvAmt: 2000 },
        { give: 'glowy',  giveAmt: 120,  recv: 'starry', recvAmt: 2    },
        { give: 'starry', giveAmt: 2,    recv: 'shiny',  recvAmt: 2000 },
        { give: 'starry', giveAmt: 2,    recv: 'glowy',  recvAmt: 120  },
    ];
    const ORE_COL = { shiny: '#f0a500', glowy: '#3fb950', starry: '#a78bfa' };

    // ── Star Bonus lookup ────────────────────────────────────────────────────
    const SB_LEAGUES = ['Unranked','Skeleton 1','Skeleton 2','Skeleton 3','Barbarian 4','Barbarian 5','Barbarian 6','Archer 7','Archer 8','Archer 9','Wizard 10','Wizard 11','Wizard 12','Valkyrie 13','Valkyrie 14','Valkyrie 15','Witch 16','Witch 17','Witch 18','Golem 19','Golem 20','Golem 21','P.E.K.K.A 22','P.E.K.K.A 23','P.E.K.K.A 24','Titan 25','Titan 26','Titan 27','Dragon 28','Dragon 29','Dragon 30','Electro 31','Electro 32','Electro 33','Legend'];
    const SB_RAW = {
        8:  [[360,23,0],[390,25,1],[395,25,1],[400,25,1],[450,30,1],[455,30,1],[460,30,1],[510,35,1],[515,35,1],[520,35,1],[570,38,1],[575,38,1],[580,38,1],[630,43,1],[635,43,1],[640,43,1],[690,46,1],[695,46,1],[700,46,1],[750,49,1],[755,49,1],[760,49,1],[770,52,1],[775,52,1],[780,52,1],[790,55,1],[795,55,1],[800,55,1],[810,56,1],[815,56,1],[820,56,1],[830,57,2],[835,57,2],[840,57,2],[850,58,2]],
        9:  [[450,27,0],[490,30,1],[495,30,1],[500,30,1],[550,35,1],[555,35,1],[560,35,1],[610,40,1],[615,40,1],[620,40,1],[670,43,1],[675,43,1],[680,43,1],[730,48,1],[735,48,1],[740,48,1],[790,51,1],[795,51,1],[800,51,1],[850,54,1],[855,54,1],[860,54,1],[870,57,1],[875,57,1],[880,57,1],[890,60,1],[895,60,1],[900,60,1],[910,61,1],[915,61,1],[920,61,1],[930,62,2],[935,62,2],[940,62,2],[950,63,2]],
        10: [[590,33,0],[590,31,1],[595,31,1],[600,31,1],[650,36,1],[655,36,1],[660,36,1],[710,41,1],[715,41,1],[720,41,1],[770,44,1],[775,44,1],[780,44,1],[830,49,1],[835,49,1],[840,49,1],[890,52,1],[895,52,1],[900,52,1],[950,55,1],[955,55,1],[960,55,1],[970,58,1],[975,58,1],[980,58,1],[990,61,1],[995,61,1],[1000,61,1],[1010,62,1],[1015,62,1],[1020,62,1],[1030,63,2],[1035,63,2],[1040,63,2],[1050,64,2]],
        11: [[640,34,0],[640,32,1],[645,32,1],[650,32,1],[700,37,1],[705,37,1],[710,37,1],[760,42,1],[765,42,1],[770,42,1],[820,45,1],[825,45,1],[830,45,1],[880,50,1],[885,50,1],[890,50,1],[940,53,1],[945,53,1],[950,53,1],[1000,56,1],[1005,56,1],[1010,56,1],[1020,59,1],[1025,59,1],[1030,59,1],[1040,62,1],[1045,62,1],[1050,62,1],[1060,63,1],[1065,63,1],[1070,63,1],[1080,64,2],[1085,64,2],[1090,64,2],[1100,65,2]],
        12: [[730,39,1],[690,33,1],[695,33,1],[700,33,1],[750,38,1],[755,38,1],[760,38,1],[810,43,1],[815,43,1],[820,43,1],[870,46,1],[875,46,1],[880,46,1],[930,51,1],[935,51,1],[940,51,1],[990,54,1],[995,54,1],[1000,54,1],[1050,57,1],[1055,57,1],[1060,57,1],[1070,60,1],[1075,60,1],[1080,60,1],[1090,63,1],[1095,63,1],[1100,63,1],[1110,64,1],[1115,64,1],[1120,64,1],[1130,65,2],[1135,65,2],[1140,65,2],[1150,66,2]],
        13: [[830,43,1],[740,34,1],[745,34,1],[750,34,1],[800,39,1],[805,39,1],[810,39,1],[860,44,1],[865,44,1],[870,44,1],[920,47,1],[925,47,1],[930,47,1],[980,52,1],[985,52,1],[990,52,1],[1040,55,1],[1045,55,1],[1050,55,1],[1100,58,1],[1105,58,1],[1110,58,1],[1120,61,1],[1125,61,1],[1130,61,1],[1140,64,1],[1145,64,1],[1150,64,1],[1160,65,1],[1165,65,1],[1170,65,1],[1180,66,2],[1185,66,2],[1190,66,2],[1200,67,2]],
        14: [[900,48,1],[750,35,1],[755,35,1],[760,35,1],[810,40,1],[815,40,1],[820,40,1],[870,45,1],[875,45,1],[880,45,1],[930,48,1],[935,48,1],[940,48,1],[990,53,1],[995,53,1],[1000,53,1],[1050,56,1],[1055,56,1],[1060,56,1],[1110,59,1],[1115,59,1],[1120,59,1],[1130,62,1],[1135,62,1],[1140,62,1],[1150,65,1],[1155,65,1],[1160,65,1],[1170,66,1],[1175,66,1],[1180,66,1],[1190,67,2],[1195,67,2],[1200,67,2],[1210,68,2]],
        15: [[960,52,1],[760,36,1],[765,36,1],[770,36,1],[820,41,1],[825,41,1],[830,41,1],[880,46,1],[885,46,1],[890,46,1],[940,49,1],[945,49,1],[950,49,1],[1000,54,1],[1005,54,1],[1010,54,1],[1060,57,1],[1065,57,1],[1070,57,1],[1120,60,1],[1125,60,1],[1130,60,1],[1140,63,1],[1145,63,1],[1150,63,1],[1160,66,1],[1165,66,1],[1170,66,1],[1180,67,1],[1185,67,1],[1190,67,1],[1200,68,2],[1205,68,2],[1210,68,2],[1220,69,2]],
        16: [[1020,55,1],[770,37,1],[775,37,1],[780,37,1],[830,42,1],[835,42,1],[840,42,1],[890,47,1],[895,47,1],[900,47,1],[950,50,1],[955,50,1],[960,50,1],[1010,55,1],[1015,55,1],[1020,55,1],[1070,58,1],[1075,58,1],[1080,58,1],[1130,61,1],[1135,61,1],[1140,61,1],[1150,64,1],[1155,64,1],[1160,64,1],[1170,67,1],[1175,67,1],[1180,67,1],[1190,68,1],[1195,68,1],[1200,68,1],[1210,69,2],[1215,69,2],[1220,69,2],[1230,70,2]],
        17: [[1050,59,1],[780,38,1],[785,38,1],[790,38,1],[840,43,1],[845,43,1],[850,43,1],[900,48,1],[905,48,1],[910,48,1],[960,51,1],[965,51,1],[970,51,1],[1020,56,1],[1025,56,1],[1030,56,1],[1080,59,1],[1085,59,1],[1090,59,1],[1140,62,1],[1145,62,1],[1150,62,1],[1160,65,1],[1165,65,1],[1170,65,1],[1180,68,1],[1185,68,1],[1190,68,1],[1200,69,1],[1205,69,1],[1210,69,1],[1220,70,2],[1225,70,2],[1230,70,2],[1240,71,2]],
        18: [[1080,63,1],[790,39,1],[795,39,1],[800,39,1],[850,44,1],[855,44,1],[860,44,1],[910,49,1],[915,49,1],[920,49,1],[970,52,1],[975,52,1],[980,52,1],[1030,57,1],[1035,57,1],[1040,57,1],[1090,60,1],[1095,60,1],[1100,60,1],[1150,63,1],[1155,63,1],[1160,63,1],[1170,66,1],[1175,66,1],[1180,66,1],[1190,69,1],[1195,69,1],[1200,69,1],[1210,70,1],[1215,70,1],[1220,70,1],[1230,71,2],[1235,71,2],[1240,71,2],[1250,72,2]],
    };

    // ── Injected hooks (overridden by init()) ─────────────────────────────────
    let _getBalance   = () => ({ shiny: 0, glowy: 0, starry: 0 });
    let _getTotalCost = () => ({ shiny: 0, glowy: 0, starry: 0 });

    // ── Persistence ───────────────────────────────────────────────────────────
    function loadGainSources() {
        try {
            const saved = JSON.parse(localStorage.getItem(GAIN_LS_KEY) || 'null');
            if (!Array.isArray(saved)) return;
            const map  = Object.fromEntries(saved.map(s => [s.id, s]));
            const AUTO = new Set(['star', 'war', 'cwl']);
            gainSources.forEach(s => {
                const sv = map[s.id];
                if (!sv) return;
                if (sv.shiny      != null) s.shiny      = sv.shiny;
                if (sv.glowy      != null) s.glowy      = sv.glowy;
                if (sv.starry     != null) s.starry     = sv.starry;
                if (sv.freq       != null) s.freq       = sv.freq;
                if (sv.enabled    != null && !AUTO.has(s.id)) s.enabled = sv.enabled;
                if (sv.shinyBuys  != null) s.shinyBuys  = sv.shinyBuys;
                if (sv.glowyBuys  != null) s.glowyBuys  = sv.glowyBuys;
                if (sv.starryBuys != null) s.starryBuys = sv.starryBuys;
                if (sv.pairCounts != null) s.pairCounts = sv.pairCounts;
            });
            _recomputeTrader();
            _recomputeProsp();
        } catch(e) {}
    }

    function saveGainSources() {
        try {
            localStorage.setItem(GAIN_LS_KEY, JSON.stringify(
                gainSources.map(({ id, shiny, glowy, starry, freq, enabled, shinyBuys, glowyBuys, starryBuys, pairCounts }) =>
                    ({ id, shiny, glowy, starry, freq, enabled, shinyBuys, glowyBuys, starryBuys, pairCounts }))
            ));
        } catch(e) {}
    }

    // ── Calculations ──────────────────────────────────────────────────────────
    function calcDailyGain() {
        const M = { daily: 1, weekly: 1/7, monthly: 1/30 };
        return gainSources.filter(s => s.enabled).reduce((acc, s) => {
            const m = M[s.freq] || 0;
            acc.shiny  += s.shiny  * m;
            acc.glowy  += s.glowy  * m;
            acc.starry += s.starry * m;
            return acc;
        }, { shiny: 0, glowy: 0, starry: 0 });
    }

    function calcDaysToCover(total, balance, daily) {
        const rem = {
            shiny:  Math.max(0, total.shiny  - balance.shiny),
            glowy:  Math.max(0, total.glowy  - balance.glowy),
            starry: Math.max(0, total.starry - balance.starry),
        };
        if (rem.shiny === 0 && rem.glowy === 0 && rem.starry === 0) return 0;
        if ((rem.shiny  > 0 && daily.shiny  === 0) ||
            (rem.glowy  > 0 && daily.glowy  === 0) ||
            (rem.starry > 0 && daily.starry === 0)) return Infinity;
        let days = 0;
        if (daily.shiny  > 0) days = Math.max(days, rem.shiny  / daily.shiny);
        if (daily.glowy  > 0) days = Math.max(days, rem.glowy  / daily.glowy);
        if (daily.starry > 0) days = Math.max(days, rem.starry / daily.starry);
        return days;
    }

    // ── Formatting helpers ────────────────────────────────────────────────────
    function fmtOreD(n)  { const d = (n||0)/30; return Number.isInteger(d) ? d.toLocaleString() : d.toFixed(1); }
    function fmtOreMo(n) { return Math.round((n||0)*30).toLocaleString(); }
    function _fd(n)      { return n < 10 ? n.toFixed(1) : Math.round(n).toString(); }

    // ── Trader helpers ────────────────────────────────────────────────────────
    function _traderBtn(ore, n, active) {
        return `<button onclick="OreGain.setTraderBuys('${ore}',${n})" id="trader-${ore}-${n}"
            style="font-family:'Rajdhani',sans-serif;font-size:11px;font-weight:700;padding:2px 6px;
                   border-radius:4px;cursor:pointer;
                   background:${active?'var(--accent)':'var(--surf2)'};
                   color:${active?'var(--bg)':'var(--muted)'};
                   border:1px solid ${active?'var(--accent)':'var(--border)'};">${n}×</button>`;
    }
    function _traderFmtD(weekly) { const d = weekly/7; return d < 10 ? d.toFixed(1) : Math.round(d).toString(); }

    // ── Card renderers ────────────────────────────────────────────────────────
    function renderStarCard(s) {
        const v = lookupStarBonus(s.th, s.league);
        const thLabel = s.th ? `TH${s.th}` : '—';
        return `
            <div class="gain-card ${s.enabled ? '' : 'gain-card-off'}" id="gain-card-star">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                </div>
                <div style="display:flex;gap:6px;">
                    <div class="gain-ore-ro" id="star-th-lbl" style="flex:0 0 auto;padding:4px 10px;">${thLabel}</div>
                    <div class="gain-ore-ro" id="star-league-lbl" style="flex:1;text-align:left;">${s.league || 'Unranked'}</div>
                </div>
                <div class="gain-ore-table">
                    <span></span>
                    <div class="gain-ore-hd">Daily</div>
                    <div class="gain-ore-hd">Monthly</div>
                    <img src="/static/img/shiny.png">
                    <div class="gain-ore-num" id="star-shiny">${v.shiny.toLocaleString()}</div>
                    <div class="gain-ore-num dim" id="star-shiny-mo">${fmtOreMo(v.shiny)}</div>
                    <img src="/static/img/glowy.png">
                    <div class="gain-ore-num" id="star-glowy">${v.glowy.toLocaleString()}</div>
                    <div class="gain-ore-num dim" id="star-glowy-mo">${fmtOreMo(v.glowy)}</div>
                    <img src="/static/img/starry.png">
                    <div class="gain-ore-num" id="star-starry">${v.starry.toLocaleString()}</div>
                    <div class="gain-ore-num dim" id="star-starry-mo">${fmtOreMo(v.starry)}</div>
                </div>
                <div class="gain-auto-lbl">Synced from profile</div>
            </div>`;
    }

    function renderWarCard(s) {
        const a = s.attacks||0, w = s.wars||0;
        const countTxt = a > 0 ? `${a} attack${a!==1?'s':''} · ${w} war${w!==1?'s':''} · last 30d` : 'No war attacks in last 30d';
        return `
            <div class="gain-card ${s.enabled ? '' : 'gain-card-off'}" id="gain-card-war">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                </div>
                <div class="gain-ore-ro" style="text-align:left;font-size:12px;" id="war-count">${countTxt}</div>
                <div class="gain-ore-table">
                    <span></span>
                    <div class="gain-ore-hd">Daily</div>
                    <div class="gain-ore-hd">Monthly</div>
                    <img src="/static/img/shiny.png">
                    <div class="gain-ore-num dim" id="war-shiny-d">${fmtOreD(s.shiny)}</div>
                    <div class="gain-ore-num" id="war-shiny">${(s.shiny||0).toLocaleString()}</div>
                    <img src="/static/img/glowy.png">
                    <div class="gain-ore-num dim" id="war-glowy-d">${fmtOreD(s.glowy)}</div>
                    <div class="gain-ore-num" id="war-glowy">${(s.glowy||0).toLocaleString()}</div>
                    <img src="/static/img/starry.png">
                    <div class="gain-ore-num dim" id="war-starry-d">${fmtOreD(s.starry)}</div>
                    <div class="gain-ore-num" id="war-starry">${(s.starry||0).toLocaleString()}</div>
                </div>
                <div class="gain-auto-lbl">Synced from war log</div>
            </div>`;
    }

    function renderCwlCard(s) {
        const a = s.attacks||0, w = s.wars||0;
        const countTxt = a > 0 ? `${a} attack${a!==1?'s':''} · ${w} round${w!==1?'s':''} · last CWL season` : 'No CWL data in last 31d';
        return `
            <div class="gain-card ${s.enabled ? '' : 'gain-card-off'}" id="gain-card-cwl">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                </div>
                <div class="gain-ore-ro" style="text-align:left;font-size:12px;" id="cwl-count">${countTxt}</div>
                <div class="gain-ore-table">
                    <span></span>
                    <div class="gain-ore-hd">Daily</div>
                    <div class="gain-ore-hd">Monthly</div>
                    <img src="/static/img/shiny.png">
                    <div class="gain-ore-num dim" id="cwl-shiny-d">${fmtOreD(s.shiny)}</div>
                    <div class="gain-ore-num" id="cwl-shiny">${(s.shiny||0).toLocaleString()}</div>
                    <img src="/static/img/glowy.png">
                    <div class="gain-ore-num dim" id="cwl-glowy-d">${fmtOreD(s.glowy)}</div>
                    <div class="gain-ore-num" id="cwl-glowy">${(s.glowy||0).toLocaleString()}</div>
                    <img src="/static/img/starry.png">
                    <div class="gain-ore-num dim" id="cwl-starry-d">${fmtOreD(s.starry)}</div>
                    <div class="gain-ore-num" id="cwl-starry">${(s.starry||0).toLocaleString()}</div>
                </div>
                <div class="gain-auto-lbl">Synced from CWL season</div>
            </div>`;
    }

    function renderTraderCard(s) {
        const bs = s.shinyBuys??2, bg = s.glowyBuys??2, bst = s.starryBuys??2;
        const ws = TRADER_BUNDLES.shiny*bs, wg = TRADER_BUNDLES.glowy*bg, wst = TRADER_BUNDLES.starry*bst;
        const btns = (ore, buys) => `<div style="display:flex;gap:3px;">${[0,1,2].map(n => _traderBtn(ore,n,buys===n)).join('')}</div>`;
        return `
            <div class="gain-card" id="gain-card-trader">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                </div>
                <div style="display:grid;grid-template-columns:18px 1fr 1fr 1fr;gap:4px 8px;align-items:center;">
                    <span></span>
                    <div class="gain-ore-hd"></div>
                    <div class="gain-ore-hd">Daily</div>
                    <div class="gain-ore-hd">Weekly</div>
                    <img src="/static/img/shiny.png" style="width:16px;height:16px;object-fit:contain;justify-self:center;">
                    ${btns('shiny', bs)}
                    <div class="gain-ore-num dim" id="trader-shiny-d">${_traderFmtD(ws)}</div>
                    <div class="gain-ore-num" id="trader-shiny-mo">${ws}</div>
                    <img src="/static/img/glowy.png" style="width:16px;height:16px;object-fit:contain;justify-self:center;">
                    ${btns('glowy', bg)}
                    <div class="gain-ore-num dim" id="trader-glowy-d">${_traderFmtD(wg)}</div>
                    <div class="gain-ore-num" id="trader-glowy-mo">${wg}</div>
                    <img src="/static/img/starry.png" style="width:16px;height:16px;object-fit:contain;justify-self:center;">
                    ${btns('starry', bst)}
                    <div class="gain-ore-num dim" id="trader-starry-d">${_traderFmtD(wst)}</div>
                    <div class="gain-ore-num" id="trader-starry-mo">${wst}</div>
                </div>
            </div>`;
    }

    function _calcProspNet(counts) {
        let shiny = 0, glowy = 0, starry = 0;
        PROSP_PAIRS.forEach((p, i) => {
            const c = counts[i] || 0;
            shiny  += (p.recv === 'shiny'  ? p.recvAmt : p.give === 'shiny'  ? -p.giveAmt : 0) * c;
            glowy  += (p.recv === 'glowy'  ? p.recvAmt : p.give === 'glowy'  ? -p.giveAmt : 0) * c;
            starry += (p.recv === 'starry' ? p.recvAmt : p.give === 'starry' ? -p.giveAmt : 0) * c;
        });
        return { shiny, glowy, starry };
    }

    function _recomputeProsp() {
        const src = gainSources.find(s => s.id === 'prosp');
        if (!src) return;
        if (!src.pairCounts) src.pairCounts = [0,0,0,0,0,0];
        const net = _calcProspNet(src.pairCounts);
        src.shiny  = net.shiny;
        src.glowy  = net.glowy;
        src.starry = net.starry;
        src.freq   = 'monthly';
        src.enabled = src.pairCounts.some(c => c > 0);
    }

    function _updateProspCard() {
        const src = gainSources.find(s => s.id === 'prosp');
        if (!src || !src.pairCounts) return;
        const counts = src.pairCounts;
        const totalUses = counts.reduce((a, b) => a + b, 0);
        const net = _calcProspNet(counts);
        const fmtNet = v => v === 0 ? '—' : (v > 0 ? '+' : '') + v.toLocaleString();
        const netColor = v => v > 0 ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--muted)';
        counts.forEach((count, i) => {
            const el = document.getElementById(`prosp-count-${i}`);
            if (el) { el.textContent = count; el.style.color = count > 0 ? 'var(--text)' : 'var(--muted)'; }
            const dec = document.getElementById(`prosp-dec-${i}`);
            if (dec) dec.style.opacity = count <= 0 ? '.25' : '1';
            const inc = document.getElementById(`prosp-inc-${i}`);
            if (inc) inc.style.opacity = totalUses >= 30 ? '.25' : '1';
        });
        const usesEl = document.getElementById('prosp-uses');
        if (usesEl) { usesEl.textContent = `${totalUses}/30`; usesEl.style.color = totalUses > 30 ? 'var(--red)' : 'var(--muted)'; }
        ['shiny', 'glowy', 'starry'].forEach(ore => {
            const el = document.getElementById('prosp-net-' + ore);
            if (el) { const v = net[ore]; el.textContent = fmtNet(v); el.style.color = netColor(v); }
        });
    }

    function renderProspCard(s) {
        if (!s.pairCounts) s.pairCounts = [0,0,0,0,0,0];
        const counts = s.pairCounts;
        const totalUses = counts.reduce((a, b) => a + b, 0);
        const net = _calcProspNet(counts);
        const fmtNet = v => v === 0 ? '—' : (v > 0 ? '+' : '') + v.toLocaleString();
        const netColor = v => v > 0 ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--muted)';

        const oreLabel = (ore, amt) =>
            `<span style="display:inline-flex;align-items:center;gap:4px;font-family:'Rajdhani',sans-serif;font-size:12px;font-weight:700;color:${ORE_COL[ore]};white-space:nowrap;">` +
            `<img src="/static/img/${ore}.png" style="width:13px;height:13px;object-fit:contain;">${amt.toLocaleString()}</span>`;

        const btnS = `font-family:'Rajdhani',sans-serif;font-size:13px;font-weight:900;width:20px;height:20px;` +
            `border-radius:4px;border:1px solid var(--border);background:var(--surf2);color:var(--muted);` +
            `cursor:pointer;display:inline-flex;align-items:center;justify-content:center;line-height:1;padding:0;flex-shrink:0;`;

        const stepper = (i, count) =>
            `<div style="display:inline-flex;align-items:center;gap:5px;">` +
            `<button id="prosp-dec-${i}" onmousedown="OreGain.prospHoldStart(${i},-1)" onmouseup="OreGain.prospHoldStop()" onmouseleave="OreGain.prospHoldStop()" style="${btnS}${count<=0?'opacity:.25;':''}">−</button>` +
            `<span id="prosp-count-${i}" style="min-width:20px;text-align:center;font-family:'Rajdhani',sans-serif;font-size:13px;font-weight:700;color:${count>0?'var(--text)':'var(--muted)'};">${count}</span>` +
            `<button id="prosp-inc-${i}" onmousedown="OreGain.prospHoldStart(${i},1)" onmouseup="OreGain.prospHoldStop()" onmouseleave="OreGain.prospHoldStop()" style="${btnS}${totalUses>=30?'opacity:.25;':''}">+</button>` +
            `</div>`;

        const hd = t => `<span style="font-family:'Rajdhani',sans-serif;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);">${t}</span>`;

        const pairRows = PROSP_PAIRS.map((p, i) =>
            `${oreLabel(p.give, p.giveAmt)}` +
            `<span style="color:var(--muted);font-size:11px;text-align:center;">→</span>` +
            `${oreLabel(p.recv, p.recvAmt)}` +
            `${stepper(i, counts[i])}`
        ).join('');

        const netItem = ore =>
            `<span style="display:inline-flex;align-items:center;gap:3px;">` +
            `<img src="/static/img/${ore}.png" style="width:13px;height:13px;object-fit:contain;">` +
            `<span id="prosp-net-${ore}" style="font-family:'Rajdhani',sans-serif;font-size:12px;font-weight:700;color:${netColor(net[ore])};">${fmtNet(net[ore])}</span>` +
            `</span>`;

        return `
            <div class="gain-card" id="gain-card-prosp">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                    <button onclick="OreGain.resetProsp()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);font-family:'Rajdhani',sans-serif;font-size:11px;font-weight:700;padding:3px 9px;cursor:pointer;transition:border-color .12s,color .12s;" onmouseover="this.style.borderColor='var(--red)';this.style.color='var(--red)'" onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--muted)'">Reset</button>
                </div>
                <div style="display:grid;grid-template-columns:auto 12px auto auto;gap:6px 10px;align-items:center;">
                    ${hd('give')}<span></span>${hd('receive')}<span></span>
                    ${pairRows}
                </div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-family:'Rajdhani',sans-serif;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);">net/mo</span>
                        ${netItem('shiny')}${netItem('glowy')}${netItem('starry')}
                    </div>
                    <span id="prosp-uses" style="font-family:'Rajdhani',sans-serif;font-size:10px;font-weight:700;color:${totalUses>30?'var(--red)':'var(--muted)'};">${totalUses}/30</span>
                </div>
            </div>`;
    }

    function renderCustomCard(s) {
        return `
            <div class="gain-card" id="gain-card-${s.id}">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                </div>
                <div class="gain-card-ores">
                    <div class="gain-card-ore"><img src="/static/img/shiny.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.shiny}" data-id="${s.id}" data-ore="shiny" oninput="OreGain.onGainInput(this)"></div>
                    <div class="gain-card-ore"><img src="/static/img/glowy.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.glowy}" data-id="${s.id}" data-ore="glowy" oninput="OreGain.onGainInput(this)"></div>
                    <div class="gain-card-ore"><img src="/static/img/starry.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.starry}" data-id="${s.id}" data-ore="starry" oninput="OreGain.onGainInput(this)"></div>
                </div>
                <select class="gain-card-freq" data-id="${s.id}" onchange="OreGain.onGainFreq(this)">
                    <option value="daily"   ${s.freq==='daily'   ?'selected':''}>Per Day</option>
                    <option value="weekly"  ${s.freq==='weekly'  ?'selected':''}>Per Week</option>
                    <option value="monthly" ${s.freq==='monthly' ?'selected':''}>Per Month</option>
                </select>
            </div>`;
    }

    function renderGenericCard(s) {
        return `
            <div class="gain-card ${s.enabled ? '' : 'gain-card-off'}" id="gain-card-${s.id}">
                <div class="gain-card-head">
                    <div class="gain-card-title"><span>${s.icon}</span><span>${s.name}</span></div>
                    <label class="gain-toggle">
                        <input type="checkbox" data-id="${s.id}" onchange="OreGain.onGainToggle(this)" ${s.enabled ? 'checked' : ''}>
                        <span class="gain-t-track"></span>
                        <span class="gain-t-thumb"></span>
                    </label>
                </div>
                <div class="gain-card-ores">
                    <div class="gain-card-ore"><img src="/static/img/shiny.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.shiny}" data-id="${s.id}" data-ore="shiny" oninput="OreGain.onGainInput(this)"></div>
                    <div class="gain-card-ore"><img src="/static/img/glowy.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.glowy}" data-id="${s.id}" data-ore="glowy" oninput="OreGain.onGainInput(this)"></div>
                    <div class="gain-card-ore"><img src="/static/img/starry.png">
                        <input class="gain-ore-val" type="number" min="0" value="${s.starry}" data-id="${s.id}" data-ore="starry" oninput="OreGain.onGainInput(this)"></div>
                </div>
                <select class="gain-card-freq" data-id="${s.id}" onchange="OreGain.onGainFreq(this)">
                    <option value="daily"   ${s.freq==='daily'   ?'selected':''}>Per Day</option>
                    <option value="weekly"  ${s.freq==='weekly'  ?'selected':''}>Per Week</option>
                    <option value="monthly" ${s.freq==='monthly' ?'selected':''}>Per Month</option>
                </select>
            </div>`;
    }

    function renderGainCards() {
        const container = document.getElementById('gain-cards');
        if (!container) return;
        container.innerHTML = gainSources.map(s => {
            if (s.id === 'star')   return renderStarCard(s);
            if (s.id === 'war')    return renderWarCard(s);
            if (s.id === 'cwl')    return renderCwlCard(s);
            if (s.id === 'trader') return renderTraderCard(s);
            if (s.id === 'prosp')   return renderProspCard(s);
            if (s.id === 'custom')  return renderCustomCard(s);
            return renderGenericCard(s);
        }).join('');
        updateGainSummary();
    }

    // ── Summary update ────────────────────────────────────────────────────────
    function updateGainSummary() {
        const daily   = calcDailyGain();
        const balance = _getBalance();
        const total   = _getTotalCost();
        const days    = calcDaysToCover(total, balance, daily);

        const pillsEl = document.getElementById('gain-pills');
        const _fmo = n => Math.round(n * 30).toLocaleString();
        if (pillsEl) {
            const hd = t => `<span style="font-family:'Rajdhani',sans-serif;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);text-align:right;">${t}</span>`;
            const ic = f => `<img src="/static/img/${f}.png" style="width:14px;height:14px;object-fit:contain;justify-self:center;">`;
            const dv = (v,c) => `<span style="font-family:'Rajdhani',sans-serif;font-size:13px;font-weight:700;color:${c};text-align:right;">${v}</span>`;
            const mv = v  => `<span style="font-family:'Rajdhani',sans-serif;font-size:12px;font-weight:600;color:var(--muted);text-align:right;">${v}</span>`;
            pillsEl.innerHTML = `<div style="display:grid;grid-template-columns:16px 52px 68px;gap:4px 10px;align-items:center;">
                <span></span>${hd('/day')}${hd('/mo')}
                ${ic('shiny')}${dv(_fd(daily.shiny),'#f0a500')}${mv(_fmo(daily.shiny))}
                ${ic('glowy')}${dv(_fd(daily.glowy),'#3fb950')}${mv(_fmo(daily.glowy))}
                ${daily.starry > 0 ? `${ic('starry')}${dv(_fd(daily.starry),'#a78bfa')}${mv(_fmo(daily.starry))}` : ''}
            </div>`;
        }

        const dailyEl = document.getElementById('gain-daily');
        if (dailyEl) dailyEl.innerHTML =
            `<span class="ore-pill ore-shiny"><img src="/static/img/shiny.png" class="ore-img"> <span style="color:#f0a500;">${_fd(daily.shiny)}</span></span>` +
            `<span class="ore-pill ore-glowy"><img src="/static/img/glowy.png" class="ore-img"> <span style="color:#3fb950;">${_fd(daily.glowy)}</span></span>` +
            (daily.starry > 0 ? `<span class="ore-pill ore-starry"><img src="/static/img/starry.png" class="ore-img"> <span style="color:#a78bfa;">${_fd(daily.starry)}</span></span>` : '');

        const monthlyEl = document.getElementById('gain-monthly');
        if (monthlyEl) monthlyEl.innerHTML =
            `<span class="ore-pill ore-shiny"><img src="/static/img/shiny.png" class="ore-img"> <span style="color:#f0a500;">${_fmo(daily.shiny)}</span></span>` +
            `<span class="ore-pill ore-glowy"><img src="/static/img/glowy.png" class="ore-img"> <span style="color:#3fb950;">${_fmo(daily.glowy)}</span></span>` +
            (daily.starry > 0 ? `<span class="ore-pill ore-starry"><img src="/static/img/starry.png" class="ore-img"> <span style="color:#a78bfa;">${_fmo(daily.starry)}</span></span>` : '');

        // Hero page ore grid (pog-* elements)
        const _setEl = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        _setEl('pog-shiny-d',  _fd(daily.shiny));   _setEl('pog-shiny-m',  _fmo(daily.shiny));
        _setEl('pog-glowy-d',  _fd(daily.glowy));   _setEl('pog-glowy-m',  _fmo(daily.glowy));
        _setEl('pog-starry-d', _fd(daily.starry));  _setEl('pog-starry-m', _fmo(daily.starry));

        const daysEl  = document.getElementById('gain-days');
        const lblEl   = document.getElementById('gain-days-lbl');
        const shortEl = document.getElementById('gain-days-short');
        const hasPlan = total.shiny > 0 || total.glowy > 0 || total.starry > 0;

        if (!hasPlan) {
            if (daysEl)  daysEl.textContent = '';
            if (lblEl)   lblEl.style.display = 'none';
            if (shortEl) shortEl.textContent = '';
        } else if (days === 0) {
            if (daysEl)  { daysEl.textContent = 'Affordable now'; daysEl.style.color = 'var(--green)'; }
            if (lblEl)   lblEl.style.display = 'inline';
            if (shortEl) { shortEl.textContent = 'Plan: affordable now'; shortEl.style.color = 'var(--green)'; }
        } else if (!isFinite(days)) {
            if (daysEl)  { daysEl.textContent = 'Enable more sources'; daysEl.style.color = 'var(--red)'; }
            if (lblEl)   lblEl.style.display = 'none';
            if (shortEl) { shortEl.textContent = 'Missing ore source'; shortEl.style.color = 'var(--muted)'; }
        } else {
            const d  = Math.ceil(days);
            const dt = new Date(); dt.setDate(dt.getDate() + d);
            const ds = dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
            const tx = `~${d} day${d!==1?'s':''} (by ${ds})`;
            if (daysEl)  { daysEl.textContent = tx; daysEl.style.color = 'var(--text)'; }
            if (lblEl)   lblEl.style.display = 'inline';
            if (shortEl) { shortEl.textContent = `Plan done in ${tx}`; shortEl.style.color = 'var(--muted)'; }
        }
    }

    // ── Star Bonus ────────────────────────────────────────────────────────────
    function lookupStarBonus(th, league) {
        const idx  = SB_LEAGUES.indexOf((league||'').replace('League ', ''));
        const rows = SB_RAW[th];
        if (!rows || idx < 0 || !rows[idx]) return { shiny: 0, glowy: 0, starry: 0 };
        return { shiny: rows[idx][0], glowy: rows[idx][1], starry: rows[idx][2] };
    }

    function applyStarBonus(th, league) {
        const star = gainSources.find(s => s.id === 'star');
        if (!star) return;
        star.th = th; star.league = league; star.freq = 'daily';
        const v = lookupStarBonus(th, league);
        star.shiny = v.shiny; star.glowy = v.glowy; star.starry = v.starry;
        const upd   = k => { const el = document.getElementById('star-'+k);      if (el) el.textContent = (v[k]||0).toLocaleString(); };
        const updMo = k => { const el = document.getElementById('star-'+k+'-mo'); if (el) el.textContent = fmtOreMo(v[k]); };
        upd('shiny'); upd('glowy'); upd('starry');
        updMo('shiny'); updMo('glowy'); updMo('starry');
        const thEl  = document.getElementById('star-th-lbl');     if (thEl)  thEl.textContent  = th ? `TH${th}` : '—';
        const lgEl  = document.getElementById('star-league-lbl'); if (lgEl)  lgEl.textContent  = league || 'Unranked';
        saveGainSources();
        updateGainSummary();
    }

    // ── War / CWL ─────────────────────────────────────────────────────────────
    function applyWarStats(data) {
        const war = gainSources.find(s => s.id === 'war');
        if (!war) return;
        war.freq = 'monthly';
        war.shiny = data.shiny||0; war.glowy = data.glowy||0; war.starry = data.starry||0;
        war.attacks = data.attacks||0; war.wars = data.wars||0;
        const upd  = k => { const el = document.getElementById('war-'+k);      if (el) el.textContent = (data[k]||0).toLocaleString(); };
        const updD = k => { const el = document.getElementById('war-'+k+'-d'); if (el) el.textContent = fmtOreD(data[k]); };
        upd('shiny'); upd('glowy'); upd('starry');
        updD('shiny'); updD('glowy'); updD('starry');
        const countEl = document.getElementById('war-count');
        if (countEl) {
            const a = data.attacks||0, w = data.wars||0;
            countEl.textContent = a > 0 ? `${a} attack${a!==1?'s':''} · ${w} war${w!==1?'s':''} (last 30d)` : 'No war attacks in last 30d';
        }
        saveGainSources(); updateGainSummary();
    }

    function applyCwlStats(data) {
        const cwl = gainSources.find(s => s.id === 'cwl');
        if (!cwl) return;
        cwl.freq = 'monthly';
        cwl.shiny = data.shiny||0; cwl.glowy = data.glowy||0; cwl.starry = data.starry||0;
        cwl.attacks = data.attacks||0; cwl.wars = data.wars||0;
        const upd  = k => { const el = document.getElementById('cwl-'+k);      if (el) el.textContent = (data[k]||0).toLocaleString(); };
        const updD = k => { const el = document.getElementById('cwl-'+k+'-d'); if (el) el.textContent = fmtOreD(data[k]); };
        upd('shiny'); upd('glowy'); upd('starry');
        updD('shiny'); updD('glowy'); updD('starry');
        const countEl = document.getElementById('cwl-count');
        if (countEl) {
            const a = data.attacks||0, w = data.wars||0;
            countEl.textContent = a > 0 ? `${a} attack${a!==1?'s':''} · ${w} round${w!==1?'s':''} · last CWL season` : 'No CWL data in last 31d';
        }
        saveGainSources(); updateGainSummary();
    }

    // ── Trader ────────────────────────────────────────────────────────────────
    function setTraderBuys(ore, val) {
        const src = gainSources.find(s => s.id === 'trader');
        if (!src) return;
        if (ore === 'shiny')  src.shinyBuys  = val;
        if (ore === 'glowy')  src.glowyBuys  = val;
        if (ore === 'starry') src.starryBuys = val;
        src.shiny  = TRADER_BUNDLES.shiny  * (src.shinyBuys  ?? 2);
        src.glowy  = TRADER_BUNDLES.glowy  * (src.glowyBuys  ?? 2);
        src.starry = TRADER_BUNDLES.starry * (src.starryBuys ?? 2);
        src.freq   = 'weekly';
        src.enabled = src.shiny > 0 || src.glowy > 0 || src.starry > 0;
        const upd = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        upd('trader-shiny-d',   _traderFmtD(src.shiny));
        upd('trader-shiny-mo',  src.shiny);
        upd('trader-glowy-d',   _traderFmtD(src.glowy));
        upd('trader-glowy-mo',  src.glowy);
        upd('trader-starry-d',  _traderFmtD(src.starry));
        upd('trader-starry-mo', src.starry);
        ['shiny','glowy','starry'].forEach(o => [0,1,2].forEach(n => {
            const btn = document.getElementById(`trader-${o}-${n}`);
            if (!btn) return;
            const buys = o==='shiny' ? src.shinyBuys : o==='glowy' ? src.glowyBuys : src.starryBuys;
            const active = buys === n;
            btn.style.background  = active ? 'var(--accent)' : 'var(--surf2)';
            btn.style.color       = active ? 'var(--bg)'     : 'var(--muted)';
            btn.style.borderColor = active ? 'var(--accent)' : 'var(--border)';
        }));
        saveGainSources(); updateGainSummary();
        window.scheduleAutoSave?.(); _flashModalSaved();
    }

    // ── Prospector handler ────────────────────────────────────────────────────
    function resetProsp() {
        const src = gainSources.find(s => s.id === 'prosp');
        if (!src) return;
        src.pairCounts = [0,0,0,0,0,0];
        _recomputeProsp();
        _updateProspCard();
        saveGainSources();
        updateGainSummary();
        window.scheduleAutoSave?.(); _flashModalSaved();
    }

    function adjProspPair(idx, delta) {
        const src = gainSources.find(s => s.id === 'prosp');
        if (!src) return;
        if (!src.pairCounts) src.pairCounts = [0,0,0,0,0,0];
        const newVal = (src.pairCounts[idx] || 0) + delta;
        const newTotal = src.pairCounts.reduce((a, b, i) => a + (i === idx ? newVal : b), 0);
        if (newVal < 0 || newTotal > 30) return;
        src.pairCounts[idx] = newVal;
        _recomputeProsp();
        _updateProspCard();
        saveGainSources();
        updateGainSummary();
        window.scheduleAutoSave?.(); _flashModalSaved();
    }

    let _holdTimer = null, _holdInterval = null;
    function prospHoldStart(idx, delta) {
        adjProspPair(idx, delta);
        _holdTimer = setTimeout(() => {
            _holdInterval = setInterval(() => adjProspPair(idx, delta), 80);
        }, 400);
    }
    function prospHoldStop() {
        clearTimeout(_holdTimer);
        clearInterval(_holdInterval);
        _holdTimer = _holdInterval = null;
    }

    function setProspPair(idx, val) {
        const src = gainSources.find(s => s.id === 'prosp');
        if (!src) return;
        if (!src.pairCounts) src.pairCounts = [0,0,0,0,0,0];
        src.pairCounts[idx] = Math.max(0, Math.min(30, parseInt(val) || 0));
        _recomputeProsp();
        _updateProspCard();
        saveGainSources();
        updateGainSummary();
        window.scheduleAutoSave?.(); _flashModalSaved();
    }

    // ── Modal saved flash ─────────────────────────────────────────────────────
    let _flashT = null;
    function _flashModalSaved() {
        const el = document.getElementById('gain-modal-save');
        if (!el) return;
        el.textContent = 'Saved';
        el.style.opacity = '1';
        clearTimeout(_flashT);
        _flashT = setTimeout(() => { el.style.opacity = '0'; }, 2000);
    }

    // ── Generic card handlers ─────────────────────────────────────────────────
    function onGainInput(input) {
        const src = gainSources.find(s => s.id === input.dataset.id);
        if (src) src[input.dataset.ore] = Math.max(0, parseInt(input.value) || 0);
        saveGainSources(); updateGainSummary(); window.scheduleAutoSave?.(); _flashModalSaved();
    }

    function onGainFreq(select) {
        const src = gainSources.find(s => s.id === select.dataset.id);
        if (src) src.freq = select.value;
        saveGainSources(); updateGainSummary(); window.scheduleAutoSave?.(); _flashModalSaved();
    }

    function onGainToggle(cb) {
        const src = gainSources.find(s => s.id === cb.dataset.id);
        if (!src) return;
        src.enabled = cb.checked;
        const card = document.getElementById('gain-card-' + src.id);
        if (card) card.classList.toggle('gain-card-off', !src.enabled);
        saveGainSources(); updateGainSummary(); window.scheduleAutoSave?.(); _flashModalSaved();
    }

    // ── Modal ─────────────────────────────────────────────────────────────────
    function openGainModal()  { document.getElementById('gain-modal')?.classList.add('open'); }
    function closeGainModal() { document.getElementById('gain-modal')?.classList.remove('open'); }

    // ── Settings serialisation ────────────────────────────────────────────────
    function getSettings() {
        return gainSources.map(({ id, shiny, glowy, starry, freq, enabled, shinyBuys, glowyBuys, starryBuys, pairCounts }) =>
            ({ id, shiny, glowy, starry, freq, enabled, shinyBuys, glowyBuys, starryBuys, pairCounts }));
    }

    function applySettings(saved) {
        if (!Array.isArray(saved)) return;
        const map  = Object.fromEntries(saved.map(s => [s.id, s]));
        const AUTO = new Set(['star', 'war', 'cwl']);
        gainSources.forEach(s => {
            const sv = map[s.id];
            if (!sv) return;
            if (sv.shiny      != null) s.shiny      = sv.shiny;
            if (sv.glowy      != null) s.glowy      = sv.glowy;
            if (sv.starry     != null) s.starry     = sv.starry;
            if (sv.freq       != null) s.freq       = sv.freq;
            if (sv.enabled    != null && !AUTO.has(s.id)) s.enabled = sv.enabled;
            if (sv.shinyBuys  != null) s.shinyBuys  = sv.shinyBuys;
            if (sv.glowyBuys  != null) s.glowyBuys  = sv.glowyBuys;
            if (sv.starryBuys != null) s.starryBuys = sv.starryBuys;
            if (sv.pairCounts != null) s.pairCounts = sv.pairCounts;
        });
        _recomputeTrader();
        _recomputeProsp();
    }

    function _recomputeTrader() {
        const trader = gainSources.find(s => s.id === 'trader');
        if (!trader) return;
        trader.shiny   = TRADER_BUNDLES.shiny  * (trader.shinyBuys  ?? 2);
        trader.glowy   = TRADER_BUNDLES.glowy  * (trader.glowyBuys  ?? 2);
        trader.starry  = TRADER_BUNDLES.starry * (trader.starryBuys ?? 2);
        trader.freq    = 'weekly';
        trader.enabled = trader.shiny > 0 || trader.glowy > 0 || trader.starry > 0;
    }

    // ── Public init ───────────────────────────────────────────────────────────
    function init({ getBalance, getTotalCost, savedSettings } = {}) {
        if (getBalance)   _getBalance   = getBalance;
        if (getTotalCost) _getTotalCost = getTotalCost;
        // Server settings take priority over localStorage
        if (savedSettings) {
            applySettings(savedSettings);
        } else {
            loadGainSources();
        }
        renderGainCards();
        document.getElementById('gain-modal')?.addEventListener('click', e => {
            if (e.target === e.currentTarget) closeGainModal();
        });
    }

    return {
        init,
        open:  openGainModal,
        close: closeGainModal,
        getDailyGain:    calcDailyGain,
        updateSummary:   updateGainSummary,
        getSettings,
        applyStarBonus,
        applyWarStats,
        applyCwlStats,
        setTraderBuys,
        resetProsp,
        adjProspPair,
        setProspPair,
        prospHoldStart,
        prospHoldStop,
        onGainInput,
        onGainFreq,
        onGainToggle,
    };
})();
