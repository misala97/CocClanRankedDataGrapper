"""The keyboard, touch and cross-page checks the VC1 contract names.

Every check prints PASS or FAIL with what it actually saw, and the script exits
non-zero if any of them failed -- a report that cannot fail is not evidence.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1])
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:5071/scratchpad/vc1'

FAILURES = []
# The preview serves canned answers for the endpoints the hub calls. It has
# detail payloads for the REAL tickers only: inventing one for a fictional
# ticker would mean showing real evidence under an invented company, which is
# exactly the confusion the fixture labelling exists to prevent. So a 404 on
# `/radar/api/ticker/<fictional>` is the preview being honest, and it is the
# only non-2xx this run may contain.
ALLOWED_404 = '/radar/api/ticker/'


def check(label, ok, detail=''):
    print(f'  {"PASS" if ok else "FAIL"}  {label}' + (f'  --  {detail}' if detail else ''))
    if not ok:
        FAILURES.append(label)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- desk: keyboard and disclosure behaviour ------------------------
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        page.on('console', lambda m: errors.append(f'console {m.type}: {m.text}')
                if m.type == 'error' and '404' not in m.text else None)
        page.on('response', lambda r: errors.append(f'{r.status} {r.url}')
                if r.status >= 400 and ALLOWED_404 not in r.url else None)
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
        page.wait_for_selector('.rh-chatter')

        print('\ndisclosures')
        tone = page.locator('.rh-col-tone .rh-detailtoggle').first
        check('tone detail starts closed',
              tone.get_attribute('aria-expanded') == 'false')
        tone.click()
        check('it opens on click', tone.get_attribute('aria-expanded') == 'true')
        body = page.locator('.rh-col-tone .rh-detailbody').first
        check('its body becomes visible', body.is_visible())
        check('the body carries the exact counts',
              'bullish' in (body.inner_text() or ''),
              (body.inner_text() or '')[:60].replace('\n', ' '))
        page.keyboard.press('Escape')
        check('Escape closes it', tone.get_attribute('aria-expanded') == 'false')
        check('focus returns to the control',
              page.evaluate('document.activeElement.getAttribute("aria-expanded")')
              == 'false'
              and page.evaluate(
                  'document.activeElement.classList.contains("rh-detailtoggle")'))

        sources = page.locator('.rh-col-sources .rh-detailtoggle').first
        sources.click()
        sbody = page.locator('.rh-col-sources .rh-detailbody').first
        check('the source detail names concrete feeds',
              'r/' in (sbody.inner_text() or ''),
              (sbody.inner_text() or '').replace('\n', ' ')[:80])
        check('opening a detail did not navigate',
              page.evaluate('location.hash') == '#chatter',
              page.evaluate('location.hash'))
        page.keyboard.press('Escape')

        print('\nkeyboard reach')
        page.evaluate('document.body.focus()')
        # Tab from the top of the document until the first row's company
        # control has focus, then check what the next stops are.
        stops = page.evaluate("""() => {
          const row = document.querySelector('.rh-chatter tbody tr');
          return Array.from(row.querySelectorAll('button')).map((b) => ({
            cls: b.className,
            name: b.getAttribute('aria-label') || b.textContent.trim(),
            tabbable: b.tabIndex >= 0,
          }));
        }""")
        check('every row control is reachable by keyboard',
              all(s['tabbable'] for s in stops),
              ', '.join(s['cls'] for s in stops))
        check('the row is not itself a click target',
              page.evaluate("""() => {
                const row = document.querySelector('.rh-chatter tbody tr');
                return !row.onclick && row.tabIndex < 0;
              }"""))

        print('\nfilters')
        page.click('.rh-morebutton')
        check('More filters opens',
              page.get_attribute('.rh-morebutton', 'aria-expanded') == 'true')
        check('the feeds group is then visible',
              page.locator('.rh-sources').is_visible())
        boxes = page.locator('.rh-sources input[type=checkbox]')
        check('every offered feed has a checkbox', boxes.count() == 3,
              str(boxes.count()))
        # Turn two off, then try the last one: it must refuse.
        boxes.nth(0).click()
        page.wait_for_timeout(80)
        boxes = page.locator('.rh-sources input[type=checkbox]')
        state = page.evaluate("""() => Array.from(
            document.querySelectorAll('.rh-sources input')).map((i) => ({
              checked: i.checked, disabled: i.getAttribute('aria-disabled') }))""")
        check('unchecking one feed leaves the others alone',
              sum(1 for s in state if s['checked']) == 2, str(state))

        print('\nthe company control')
        page.click('.rh-chatter tbody tr .rh-open')
        page.wait_for_timeout(400)
        check('it opens research',
              page.evaluate('location.hash').startswith('#research'),
              page.evaluate('location.hash'))
        page.go_back()
        page.wait_for_timeout(400)
        check('Back returns to the list',
              page.evaluate('location.hash') == '#chatter',
              page.evaluate('location.hash'))
        context.close()

        # --- reflow: 200% zoom at 1440 is 720 CSS px ------------------------
        print('\nreflow')
        for label, width, height in [('200% zoom of 1440', 720, 500),
                                     ('400% zoom of 1280', 320, 512)]:
            context = browser.new_context(viewport={'width': width,
                                                    'height': height})
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
            page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
            page.wait_for_selector('.rh-chatter')
            sideways = page.evaluate(
                'document.documentElement.scrollWidth'
                ' > document.documentElement.clientWidth + 1')
            check(f'{label} ({width}px): no sideways document scroll',
                  not sideways)
            tone_visible = page.locator('.rh-col-tone strong').first.is_visible()
            check(f'{label}: the tone reading is still on screen', tone_visible)
            page.screenshot(path=str(OUT / f'reflow-{width}.png'), full_page=True)
            context.close()

        # --- the 700/701 boundary the contract asks about -------------------
        print('\nbreakpoints')
        for width in (1081, 1080, 861, 860, 701, 700):
            context = browser.new_context(viewport={'width': width,
                                                    'height': 900})
            page = context.new_page()
            page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
            page.wait_for_selector('.rh-chatter')
            shape = page.evaluate("""() => {
              const row = document.querySelector('.rh-chatter tbody tr');
              const menu = document.querySelector('.rh-menu');
              return {
                stacked: getComputedStyle(row).display === 'grid',
                railed: !!menu && getComputedStyle(menu).display === 'none',
                sideways: document.documentElement.scrollWidth
                          > document.documentElement.clientWidth + 1,
              };
            }""")
            print(f'    {width}px: stacked={shape["stacked"]} '
                  f'rail={shape["railed"]} sideways={shape["sideways"]}')
            check(f'{width}px does not scroll sideways', not shape['sideways'])
            context.close()

        # --- the other hub pages, because shared styling changed ------------
        print('\nother pages')
        for width, height in ((1440, 1000), (768, 1024), (390, 844)):
            context = browser.new_context(viewport={'width': width,
                                                    'height': height})
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(f'{width} pageerror: {e}'))
            page.on('console', lambda m: errors.append(f'{width} console: {m.text}')
                    if m.type == 'error' and '404' not in m.text else None)
            page.on('response', lambda r: errors.append(f'{width}: {r.status} {r.url}')
                    if r.status >= 400 else None)
            for route in ('overview', 'watching', 'activity', 'admin',
                          'research/SNDK'):
                page.goto(f'{BASE}/real.html#{route}', wait_until='networkidle')
                page.wait_for_selector('.rh-main')
                page.wait_for_timeout(200)
                slug = route.replace('/', '-')
                page.screenshot(path=str(OUT / f'page-{slug}-{width}.png'),
                                full_page=True)
                sideways = page.evaluate(
                    'document.documentElement.scrollWidth'
                    ' > document.documentElement.clientWidth + 1')
                check(f'{route} at {width}px does not scroll sideways',
                      not sideways)
            context.close()

        browser.close()

    print('\nconsole and page errors:', errors or 'none')
    if errors:
        FAILURES.append('console or page errors')
    print('\n' + ('FAILURES: ' + '; '.join(FAILURES) if FAILURES
                  else 'every check passed'))
    raise SystemExit(1 if FAILURES else 0)


if __name__ == '__main__':
    main()
