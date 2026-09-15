"""LOCAL-QA: real Chromium browser zoom at 200%, not viewport/DPR emulation.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/zoom_real.py 5041   (cwd personal_apps)

Same gates as verify_preview (preflight: target, registry, runtime nonce,
fingerprint, manifest). A NEW temporary Chromium profile gets the browser's own
default page zoom preference (`partition.default_zoom_level` = log(2)/log(1.2),
Chromium's 200% level) BEFORE launch; no device_scale_factor or small viewport
is set. Evidence that the browser zoomed rather than being emulated: the window
keeps a 1440 px outer width while the page's CSS viewport (innerWidth) halves
and devicePixelRatio reports 2 on a scale-1 display. Then the same usability
checks as zoom_200: no document overflow, select a day, controls >=44 CSS px,
change the range. Screenshots are written for viewing. The profile directory is
temporary and removed at exit.
"""
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
out = {'port': port, 'fingerprint': fingerprint['digest'], 'zoom_level_pref': LEVEL, 'runs': {}}

from playwright.sync_api import sync_playwright  # noqa: E402


def check(page, label):
    facts = {}
    facts['metrics'] = page.evaluate('({inner: innerWidth, outer: outerWidth, dpr: devicePixelRatio, '
                                     'vv: visualViewport ? visualViewport.scale : null, '
                                     'screen: screen.width})')
    page.goto(vp.link(base, manifest, 'typical'))
    vp.wait_ready(page)
    facts['metrics_on_analysis'] = page.evaluate('({inner: innerWidth, outer: outerWidth, dpr: devicePixelRatio})')
    facts['no_overflow'] = vp.no_overflow(page)
    buttons = page.locator(f'{vp.DAY_GROUP} button')
    target = buttons.nth(2)
    target.scroll_into_view_if_needed()
    target.click()
    facts['day_selected'] = target.get_attribute('aria-pressed') == 'true'
    facts['small_targets'] = vp.small_targets(page)
    page.screenshot(path=str(HERE / f'zoom-real-200-{label}.png'), full_page=True)
    window = manifest['window']
    page.locator('input[name=analysis_from]').scroll_into_view_if_needed()
    page.fill('input[name=analysis_from]', window['to'])
    page.fill('input[name=analysis_to]', window['to'])
    page.click('button:has-text("Show these days")')
    page.wait_for_function('location.search.includes("analysis_from=' + window['to'] + '")')
    vp.wait_ready(page)
    facts['one_day_buttons'] = buttons.count()
    page.screenshot(path=str(HERE / f'zoom-real-200-{label}-oneday.png'), full_page=False)
    return facts


with sync_playwright() as playwright:
    for label, headless in (('headless', True), ('headed', False)):
        with tempfile.TemporaryDirectory(prefix='ha1-zoom-profile-') as profile:
            default = Path(profile) / 'Default'
            default.mkdir()
            (default / 'Preferences').write_text(json.dumps(
                {'partition': {'default_zoom_level': {'x': LEVEL}}}), encoding='utf-8')
            context = playwright.chromium.launch_persistent_context(
                profile, headless=headless, viewport=None, no_viewport=True,
                args=['--window-size=1440,1000', '--window-position=-2400,0'])
            try:
                page = context.pages[0] if context.pages else context.new_page()
                vp.login(page, base, *credentials['admin'])
                facts = check(page, label)
                m = facts['metrics_on_analysis']
                facts['real_zoom_evidence'] = bool(m['dpr'] >= 1.9 and m['outer'] >= 1.8 * m['inner'])
                facts['pass'] = (facts['real_zoom_evidence'] and facts['no_overflow'] and facts['day_selected']
                                 and not facts['small_targets'] and facts['one_day_buttons'] == 1)
                out['runs'][label] = facts
            except Exception as exc:  # noqa: BLE001 -- recorded
                out['runs'][label] = {'error': f'{type(exc).__name__}: {exc}'[:800]}
            finally:
                context.close()

(HERE / 'zoom_real.out.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
