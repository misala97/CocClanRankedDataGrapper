"""LOCAL-QA: viewable screenshots of the REAL 200% browser zoom.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/zoom_capture.py 5041   (cwd personal_apps)

zoom_real.py proved real zoom by metrics, but Playwright's page.screenshot on a
zoomed page captured only a device-pixel quarter of the viewport. This tries
capture paths that do not depend on Playwright's viewport maths: CDP
Page.captureScreenshot of the visible surface, and page.screenshot(scale='css'),
at the top of the page and scrolled to the chart. Same preflight gates; new
temporary profile; headed window placed off-screen. Metrics are re-recorded.
"""
import base64
import json
import math
import sys
import tempfile
from pathlib import Path

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(PERSONAL / 'scratchpad' / 'ha1'))

import verify_preview as vp  # noqa: E402

port, manifest, credentials, fingerprint = vp.preflight(sys.argv)
base = f'http://127.0.0.1:{port}'
HERE = Path(__file__).resolve().parent
LEVEL = math.log(2) / math.log(1.2)
out = {'fingerprint': fingerprint['digest'], 'captures': []}

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as playwright, tempfile.TemporaryDirectory(prefix='ha1-zoom-capture-') as profile:
    default = Path(profile) / 'Default'
    default.mkdir()
    (default / 'Preferences').write_text(json.dumps({'partition': {'default_zoom_level': {'x': LEVEL}}}),
                                         encoding='utf-8')
    context = playwright.chromium.launch_persistent_context(
        profile, headless=False, no_viewport=True, args=['--window-size=1440,1000', '--window-position=-2400,0'])
    try:
        page = context.pages[0] if context.pages else context.new_page()
        vp.login(page, base, *credentials['admin'])
        page.goto(vp.link(base, manifest, 'typical'))
        vp.wait_ready(page)
        out['metrics'] = page.evaluate('({inner: innerWidth, innerH: innerHeight, outer: outerWidth, '
                                       'dpr: devicePixelRatio, scrollW: document.documentElement.scrollWidth, '
                                       'clientW: document.documentElement.clientWidth})')
        cdp = context.new_cdp_session(page)
        for spot, script in (('top', 'window.scrollTo(0, 0)'),
                             ('chart', 'document.querySelector(".rh-an-chart").scrollIntoView({block: "start"})'),
                             ('table', 'document.querySelector(".rh-an-table").scrollIntoView({block: "start"})')):
            page.evaluate(script)
            page.wait_for_timeout(400)
            name = f'zoom-real-200-cdp-{spot}.png'
            shot = cdp.send('Page.captureScreenshot', {'format': 'png', 'fromSurface': True})
            (HERE / name).write_bytes(base64.b64decode(shot['data']))
            out['captures'].append(name)
            name = f'zoom-real-200-css-{spot}.png'
            try:
                page.screenshot(path=str(HERE / name), scale='css')
                out['captures'].append(name)
            except Exception as exc:  # noqa: BLE001 -- recorded
                out.setdefault('errors', []).append(f'{name}: {type(exc).__name__}: {exc}'[:300])
    finally:
        context.close()

(HERE / 'zoom_capture.out.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
