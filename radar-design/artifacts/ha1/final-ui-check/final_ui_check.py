"""FINAL-UI-CHECK (F1): focused actual-app date-field checks.

    py -3.12 -u ../radar-design/artifacts/ha1/final-ui-check/final_ui_check.py 5041   (cwd personal_apps)

Gated by verify_preview.preflight (target + registry, runtime record, nonce,
live pid, branch/HEAD and current source/build fingerprint, owned fixture
manifest, credentials) before any login. Contexts:
- emulated widths 320 and 390 (touch), sanity widths 768 and 1440;
- REAL browser zoom: headed Chromium, new temporary profile with Chromium's own
  default page zoom preference at 200%, window 640 and 780 device px wide
  (= 320 and 390 CSS px), no viewport or device-scale emulation. Real zoom is
  proven per context by outerWidth ~= 2 x innerWidth and devicePixelRatio 2.

Per context (owned `typical` fixture): standard YYYY-MM-DD values visible at
rest and while focused/editing (text width vs content box, scrollWidth,
scrollLeft after End), editable, >=44 px fields and submit, no document
overflow, one-day range submission, refresh restores inputs/request/days, Back
restores the week; a malformed raw value stays in the input, is disclosed in
the role=alert notice and aria-invalid, and fetches nothing. Screenshots are
viewport captures (CDP surface capture under real zoom). Writes
final_ui_check.out.json here; exits 1 on any failure.
"""
import base64
import json
import math
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(PERSONAL / 'scratchpad' / 'ha1'))

import verify_preview as vp  # noqa: E402

port, manifest, credentials, fingerprint = vp.preflight(sys.argv)
base = f'http://127.0.0.1:{port}'
HERE = Path(__file__).resolve().parent
LEVEL = math.log(2) / math.log(1.2)
MALFORMED = '2026-9-8x'
out = {'port': port, 'fingerprint': fingerprint['digest'], 'synthetic': True, 'contexts': {}, 'failures': []}

from playwright.sync_api import sync_playwright  # noqa: E402


def shoot(page, name, real_zoom):
    path = HERE / f'{name}.png'
    if real_zoom:
        cdp = page.context.new_cdp_session(page)
        path.write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))
        cdp.detach()
    else:
        page.screenshot(path=str(path))
    return path.name


def form_into_view(page):
    page.evaluate('document.querySelector("form.rh-an-range").scrollIntoView({block: "center"})')
    page.wait_for_timeout(250)


def run_context(label, page, real_zoom, facts, fail):
    def check(condition, message):
        facts.setdefault('checks', 0)
        facts['checks'] += 1
        if not condition:
            fail(f'{label}: {message}')

    facts['metrics'] = page.evaluate('({inner: innerWidth, outer: outerWidth, dpr: devicePixelRatio, '
                                     'vv: visualViewport ? visualViewport.scale : null})')
    if real_zoom:
        m = facts['metrics']
        check(m['dpr'] >= 1.9 and m['outer'] >= 1.8 * m['inner'], f'real zoom not in effect: {m}')
    requests = vp.company_requests(page)
    window = manifest['window']
    address = vp.link(base, manifest, 'typical')
    page.goto(address)
    vp.wait_ready(page)
    facts['css_width'] = page.evaluate('document.documentElement.clientWidth')
    check(vp.no_overflow(page), 'document scrolls horizontally')

    rest = page.evaluate(vp.DATE_CLIP_JS)
    facts['at_rest'] = rest
    check(len(rest) == 2 and [i['value'] for i in rest] == [window['from'], window['to']],
          f'inputs do not hold the window: {rest}')
    check(all(not i['clipped'] for i in rest), f'a date is clipped at rest: {rest}')
    check(all(i['height'] >= 44 and i['width'] >= 44 for i in rest), f'a date field is under 44 px: {rest}')
    submit = page.locator('form.rh-an-range button[type=submit]').bounding_box()
    facts['submit_box'] = submit
    check(submit and submit['height'] >= 44 and submit['width'] >= 44, f'submit under 44 px: {submit}')
    small = vp.small_targets(page) if facts['css_width'] <= 860 else []
    facts['small_targets'] = small
    check(not small, f'controls under 44 px: {small}')
    facts['layout'] = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
      const f = r('input[name=analysis_from]'), t = r('input[name=analysis_to]'), b = r('form.rh-an-range button');
      return {from: [f.left, f.top, f.width], to: [t.left, t.top, t.width], button: [b.left, b.top, b.width],
              stacked: t.top > f.top + 10} }""")
    form_into_view(page)
    facts['shots'] = [shoot(page, f'{label}-rest', real_zoom)]

    focused = {}
    for name in ('analysis_from', 'analysis_to'):
        field = page.locator(f'input[name={name}]')
        field.click()
        page.keyboard.press('End')
        state = page.evaluate(f"""() => {{ const el = document.querySelector('input[name={name}]');
          return {{active: document.activeElement === el, scrollLeft: el.scrollLeft, selectionEnd: el.selectionEnd}} }}""")
        clip = next(i for i in page.evaluate(vp.DATE_CLIP_JS) if i['name'] == name)
        focused[name] = {**state, **clip}
        check(state['active'] and state['scrollLeft'] == 0 and not clip['clipped'],
              f'{name} does not show its whole value while focused: {focused[name]}')
    facts['focused'] = focused
    facts['shots'].append(shoot(page, f'{label}-focus', real_zoom))

    # Edit by keyboard, submit a one-day range, refresh, Back.
    one = window['to']
    for name in ('analysis_from', 'analysis_to'):
        field = page.locator(f'input[name={name}]')
        field.click()
        page.keyboard.press('Control+A')
        page.keyboard.type(one)
        check(field.input_value() == one, f'{name} not editable by keyboard: {field.input_value()!r}')
    editing = page.evaluate(vp.DATE_CLIP_JS)
    facts['while_editing'] = editing
    check(all(not i['clipped'] for i in editing), f'a date is clipped while editing: {editing}')
    requests.clear()
    page.click('form.rh-an-range button[type=submit]')
    page.wait_for_function(f'location.search.includes("analysis_from={one}") && '
                           f'location.search.includes("analysis_to={one}")')
    vp.wait_ready(page)
    days = page.locator(f'{vp.DAY_GROUP} button')
    check(days.count() == 1, f'one-day range rendered {days.count()} days')
    check(any(f'from={one}' in u and f'to={one}' in u for u in requests), f'no request for the one-day range: {requests}')
    submitted = page.url
    requests.clear()
    page.reload()
    vp.wait_ready(page)
    restored = page.evaluate(vp.DATE_CLIP_JS)
    facts['after_refresh'] = restored
    check(page.url == submitted, 'refresh changed the address')
    check([i['value'] for i in restored] == [one, one] and all(not i['clipped'] for i in restored),
          f'refresh did not restore whole dates: {restored}')
    check(days.count() == 1 and any(f'from={one}' in u for u in requests), 'refresh did not re-request the range')
    page.go_back()
    page.wait_for_function('location.search.includes("analysis_from=' + window['from'] + '")')
    vp.wait_ready(page)
    back = page.evaluate(vp.DATE_CLIP_JS)
    check([i['value'] for i in back] == [window['from'], window['to']] and days.count() == 7,
          f'Back did not restore the week: {back}, {days.count()} days')

    # Malformed raw input: kept, disclosed, not fetched.
    requests.clear()
    field = page.locator('input[name=analysis_from]')
    field.click()
    page.keyboard.press('Control+A')
    page.keyboard.type(MALFORMED)
    page.click('form.rh-an-range button[type=submit]')
    page.wait_for_selector('#rh-an-rangeproblem')
    page.wait_for_timeout(800)
    notice = page.text_content('#rh-an-rangeproblem') or ''
    malformed = {'value': field.input_value(), 'aria_invalid': field.get_attribute('aria-invalid'),
                 'describedby': field.get_attribute('aria-describedby'),
                 'notice': notice, 'notice_role': page.get_attribute('#rh-an-rangeproblem', 'role'),
                 'address': page.url, 'requests': list(requests),
                 'clip': next(i for i in page.evaluate(vp.DATE_CLIP_JS) if i['name'] == 'analysis_from')}
    facts['malformed'] = malformed
    check(malformed['value'] == MALFORMED, f'malformed raw value not kept: {malformed["value"]!r}')
    check(malformed['aria_invalid'] == 'true' and malformed['describedby'] == 'rh-an-rangeproblem',
          f'malformed field not marked invalid/described: {malformed}')
    check(MALFORMED in notice and malformed['notice_role'] == 'alert', f'raw value not disclosed: {notice!r}')
    check(not requests, f'fetched for a malformed range: {requests}')
    check(not malformed['clip']['clipped'], f'malformed value clipped: {malformed["clip"]}')
    check(vp.no_overflow(page), 'document scrolls horizontally with the notice')
    form_into_view(page)
    facts['shots'].append(shoot(page, f'{label}-malformed', real_zoom))
    query = parse_qs(urlsplit(page.url).query)
    facts['malformed_address_from'] = query.get('analysis_from')


def fail_into(label):
    def fail(message):
        out['failures'].append(message)
    return fail


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for label, width, height, touch in (('320', 320, 844, True), ('390', 390, 844, True),
                                        ('768', 768, 1024, False), ('1440', 1440, 1000, False)):
        context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=touch)
        page = context.new_page()
        vp.login(page, base, *credentials['admin'])
        facts = {'mode': 'viewport emulation (DPR 1)' if touch or width < 1000 else 'desktop viewport'}
        out['contexts'][label] = facts
        try:
            run_context(label, page, False, facts, fail_into(label))
        except Exception as exc:  # noqa: BLE001 -- a raised check is a failure
            out['failures'].append(f'{label}: raised {type(exc).__name__}: {exc}'[:600])
        context.close()
    browser.close()

    for label, window_width in (('zoom200-real-320css', 640), ('zoom200-real-390css', 780)):
        facts = {'mode': 'REAL browser zoom 200% (Chromium default_zoom_level preference, headed)',
                 'window_device_px': window_width}
        out['contexts'][label] = facts
        with tempfile.TemporaryDirectory(prefix='ha1-final-zoom-') as profile:
            default = Path(profile) / 'Default'
            default.mkdir()
            (default / 'Preferences').write_text(json.dumps(
                {'partition': {'default_zoom_level': {'x': LEVEL}}}), encoding='utf-8')
            context = playwright.chromium.launch_persistent_context(
                profile, headless=False, no_viewport=True,
                args=[f'--window-size={window_width},900', '--window-position=-2400,0'])
            try:
                page = context.pages[0] if context.pages else context.new_page()
                vp.login(page, base, *credentials['admin'])
                run_context(label, page, True, facts, fail_into(label))
            except Exception as exc:  # noqa: BLE001
                out['failures'].append(f'{label}: raised {type(exc).__name__}: {exc}'[:600])
            finally:
                context.close()

(HERE / 'final_ui_check.out.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps({'failures': out['failures'],
                  'contexts': {k: {'css_width': v.get('css_width'), 'metrics': v.get('metrics'),
                                   'checks': v.get('checks'), 'stacked': (v.get('layout') or {}).get('stacked'),
                                   'rest': [(i['value'], i['text'], i['content'], i['clipped']) for i in v.get('at_rest', [])]}
                               for k, v in out['contexts'].items()}}, indent=1))
raise SystemExit(1 if out['failures'] else 0)
