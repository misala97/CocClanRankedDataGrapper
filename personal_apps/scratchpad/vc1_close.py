"""The VC1-close checks: sorting, the responsive labels, and the breakpoints
the Eighth return scoped back to Chatter.

Every check prints PASS or FAIL with what it saw, and the script exits non-zero
if any failed.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1]).resolve()
BASE = sys.argv[2]

FAILURES = []


def check(label, ok, detail=''):
    print(f'  {"PASS" if ok else "FAIL"}  {label}' + (f'  --  {detail}' if detail else ''))
    if not ok:
        FAILURES.append(label)


TICKERS = """() => Array.from(
  document.querySelectorAll('[data-testid=rh-row-ticker]')).map(
    (el) => el.textContent)"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- sorting, in a real browser --------------------------------------
        print('\nsorting')
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        page.on('response', lambda r: errors.append(f'{r.status} {r.url}')
                if r.status >= 400 and '/radar/api/ticker/' not in r.url else None)
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
        page.wait_for_selector('.rh-chatter')

        radar = page.evaluate(TICKERS)
        check('the list opens in Radar order', len(radar) == 7, ', '.join(radar))
        check('no column claims to be sorted yet',
              page.evaluate("""() => Array.from(
                document.querySelectorAll('.rh-chatter thead th'))
                .every((th) => (th.getAttribute('aria-sort') ?? 'none') === 'none')"""))

        boards = []
        page.on('request', lambda r: boards.append(r.url)
                if '/radar/api/board' in r.url else None)
        page.click('[data-testid=rh-sort-attention]')
        page.wait_for_timeout(200)
        sorted_by_attention = page.evaluate(TICKERS)
        check('a header click reorders the rows',
              sorted_by_attention != radar, ', '.join(sorted_by_attention))
        check('and issues no board request', not boards, str(boards))
        check('the active header carries its state',
              page.evaluate("""() => document.querySelector(
                '.rh-chatter thead th:nth-child(2)').getAttribute('aria-sort')""")
              == 'descending')
        check('the arrow is visible on the active control only',
              page.evaluate("""() =>
                document.querySelectorAll('.rh-sortarrow').length""") == 1)

        # Unknowns last in BOTH directions, on really rendered rows. ORBT is
        # the fixture's row with no baseline and therefore no ratio.
        known = [t for t in sorted_by_attention if t != 'ORBT']
        check('descending: the row with no attention is last',
              sorted_by_attention[-1] == 'ORBT',
              ', '.join(sorted_by_attention))

        page.click('[data-testid=rh-sort-attention]')
        page.wait_for_timeout(150)
        ascending = page.evaluate(TICKERS)
        check('clicking again reverses the rows that HAVE a reading',
              [t for t in ascending if t != 'ORBT'] == list(reversed(known)),
              ', '.join(ascending))
        check('and the header follows',
              page.evaluate("""() => document.querySelector(
                  '.rh-chatter thead th:nth-child(2)').getAttribute('aria-sort')""")
              == 'ascending')
        check('ascending: the row with no attention is STILL last',
              ascending[-1] == 'ORBT', ', '.join(ascending))

        check('the note says what was sorted and what was not',
              'not the whole market' in page.inner_text('.rh-sortnote'),
              page.inner_text('.rh-sortnote').replace('\n', ' ')[:120])

        page.click('.rh-sortreset')
        page.wait_for_timeout(150)
        check('Radar order comes back', page.evaluate(TICKERS) == radar,
              ', '.join(page.evaluate(TICKERS)))
        check('and the note goes with it',
              page.locator('.rh-sortnote').count() == 0)

        print('\nkeyboard')
        page.evaluate("document.querySelector('[data-testid=rh-sort-tone]').focus()")
        page.keyboard.press('Enter')
        page.wait_for_timeout(150)
        check('Enter sorts from the keyboard',
              page.evaluate("""() => document.querySelector(
                '.rh-chatter thead th:nth-child(5)').getAttribute('aria-sort')""")
              == 'descending')
        page.keyboard.press('Space')
        page.wait_for_timeout(150)
        check('Space flips it',
              page.evaluate("""() => document.querySelector(
                '.rh-chatter thead th:nth-child(5)').getAttribute('aria-sort')""")
              == 'ascending')

        print('\nprice and today are two controls')
        page.click('[data-testid=rh-sort-price]')
        page.wait_for_timeout(150)
        check('the shared header names price when price is active',
              page.get_attribute('.rh-pricehead', 'aria-label') == 'Price',
              str(page.get_attribute('.rh-pricehead', 'aria-label')))

        # Read WHILE price is the active sort. An earlier version of this check
        # read the note after switching to Today and asserted `True` instead,
        # so it passed without looking at anything.
        note = page.inner_text('.rh-sortnote')
        check('the currency grouping is disclosed on the price sort',
              'EUR' in note and 'USD' in note and 'grouped by currency' in note,
              note.replace('\n', ' ')[:160])
        check('and it warns that reversing moves the groups too',
              'reversing moves the groups' in note,
              note.replace('\n', ' ')[:160])

        page.click('[data-testid=rh-sort-move]')
        page.wait_for_timeout(150)
        check('and names today when today is active',
              page.get_attribute('.rh-pricehead', 'aria-label') == 'Today',
              str(page.get_attribute('.rh-pricehead', 'aria-label')))
        check('a sort that does not group claims no grouping',
              'grouped by currency' not in page.inner_text('.rh-sortnote'))
        check('the unsorted remainder reads as a sentence',
              "no today's move reading" in page.inner_text('.rh-sortnote'),
              page.inner_text('.rh-sortnote').replace('\n', ' ')[-90:])
        page.click('[data-testid=rh-sort-tone]')
        page.wait_for_timeout(150)

        print('\nthe reset')
        reset = page.locator('.rh-sortreset')
        check('the reset does not look like the prose beside it',
              page.evaluate("""() => {
                const b = getComputedStyle(document.querySelector('.rh-sortreset'));
                const p = getComputedStyle(document.querySelector('.rh-sortnote span'));
                return b.color !== p.color
                       && b.textDecorationLine.includes('underline');
              }"""),
              page.evaluate("""() => {
                const b = getComputedStyle(document.querySelector('.rh-sortreset'));
                return b.color + ' / ' + b.textDecorationLine;
              }"""))
        reset.focus()
        page.keyboard.press('Enter')
        page.wait_for_timeout(200)
        # Pressing it unmounts it. React leaves focus on the body when that
        # happens, and the reader's next Tab restarts at the top of the page.
        landed = page.evaluate("""() => {
          const el = document.activeElement;
          return el === document.body
            ? 'BODY'
            : (el.getAttribute('aria-label') || el.tagName);
        }""")
        check('focus survives the reset unmounting itself',
              landed == 'Ranked companies', landed)

        print('\nwhat a screen reader is told')
        status = page.locator('[role=status]')
        check('there is a status region', status.count() == 1)
        check('it is silent in Radar order',
              (status.inner_text() or '').strip() == '',
              repr(status.inner_text()))
        page.click('[data-testid=rh-sort-voices]')
        page.wait_for_timeout(200)
        check('and it says what the list was just ordered by',
              'Sorted by Voices' in status.inner_text(),
              status.inner_text())
        page.click('.rh-sortreset')
        page.wait_for_timeout(150)

        print('\ncell labels')
        # D: gone from BOTH trees on the desk layout.
        desk = page.evaluate("""() => {
          const el = document.querySelector('.rh-chatter .rh-cell-label');
          return el ? getComputedStyle(el).display : 'absent';
        }""")
        check('the desk layout hides the duplicate cell labels outright',
              desk == 'none', desk)
        # Captured SORTED, which is the state worth looking at: the arrow, the
        # active column and the note all have to sit inside the density and
        # column widths that were already accepted.
        page.click('[data-testid=rh-sort-tone]')
        # Settle the page before capturing. The focus checks above scrolled the
        # table region into view and left the skip link showing, and a
        # full-page shot of a fixed sidebar mid-scroll is a picture of the
        # capture rather than of the page.
        page.evaluate("""() => {
          if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
          }
          window.scrollTo(0, 0);
        }""")
        page.mouse.move(0, 0)
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / 'close-sorted-1440.png'), full_page=True)
        context.close()

        context = browser.new_context(viewport={'width': 390, 'height': 844})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(f'390 pageerror: {e}'))
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
        page.wait_for_selector('.rh-chatter')
        stacked = page.evaluate("""() => {
          const el = document.querySelector('.rh-chatter .rh-cell-label');
          return el ? getComputedStyle(el).display : 'absent';
        }""")
        check('the stacked layout shows them again', stacked == 'block', stacked)
        check('the header row is gone there',
              page.evaluate("""() => getComputedStyle(
                document.querySelector('.rh-chatter thead')).display""") == 'none')
        check('so the selector is the sort control',
              page.locator('.rh-sortpicker').is_visible())
        page.select_option('.rh-sortpicker select', 'voices')
        page.wait_for_timeout(200)
        by_voices = page.evaluate(TICKERS)
        check('sorting from the selector works', by_voices[0] == 'KSTR',
              ', '.join(by_voices))
        # Its NAME is what pressing it does; its TEXT is the current order.
        # A control named "Lowest first" that produces highest-first is a
        # control that lies about itself.
        check('the direction control is named for what it does',
              page.get_attribute('.rh-sortdir', 'aria-label')
              == 'Sort lowest first',
              str(page.get_attribute('.rh-sortdir', 'aria-label')))
        page.click('.rh-sortdir')
        page.wait_for_timeout(200)
        check('and its direction control flips it',
              page.evaluate(TICKERS) != by_voices,
              ', '.join(page.evaluate(TICKERS)))
        check('the name follows the flip',
              page.get_attribute('.rh-sortdir', 'aria-label')
              == 'Sort highest first',
              str(page.get_attribute('.rh-sortdir', 'aria-label')))
        check('the stacked layout is told about the reorder too',
              'Sorted by Voices' in page.inner_text('[role=status]'),
              page.inner_text('[role=status]'))
        check('no sideways scroll while sorted',
              not page.evaluate('document.documentElement.scrollWidth'
                                ' > document.documentElement.clientWidth + 1'))
        # The company control is the affordance here; a second chevron sitting
        # alone at the bottom of every stacked row is not.
        chevron = page.evaluate("""() => {
          const el = document.querySelector('.rh-chatter .rh-col-open');
          return el ? getComputedStyle(el).display : 'absent';
        }""")
        check('the duplicate chevron column is gone from the stacked row',
              chevron == 'none', chevron)
        # Every stacked cell is placed deliberately; nothing falls into an
        # implicit row because it was missed.
        placed = page.evaluate("""() => Array.from(
          document.querySelectorAll('.rh-chatter tbody tr:first-child > *'))
          .filter((el) => getComputedStyle(el).display !== 'none')
          .map((el) => getComputedStyle(el).gridArea.split(' / ')[0])""")
        check('and every visible cell has a place in the grid',
              bool(placed) and all(area != 'auto' for area in placed),
              ', '.join(placed))
        page.screenshot(path=str(OUT / 'close-sorted-390.png'), full_page=True)
        context.close()

        # --- the breakpoints, on POPULATED tables ---------------------------
        print('\nbreakpoints, on populated tables')
        for width in (861, 860, 768, 701, 700):
            context = browser.new_context(viewport={'width': width, 'height': 900})
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(f'{width} pageerror: {e}'))
            shapes = {}
            for route, selector in (('chatter', '.rh-chatter'),
                                    ('watching', '.rh-table'),
                                    ('activity', '.rh-table')):
                page.goto(f'{BASE}/fixture.html#{route}', wait_until='networkidle')
                try:
                    page.wait_for_selector(selector, timeout=8000)
                except Exception:                                 # noqa: BLE001
                    shapes[route] = {'rows': 0}
                    continue
                shapes[route] = page.evaluate("""(sel) => {
                  const table = document.querySelector(sel);
                  const row = table.querySelector('tbody tr');
                  return {
                    rows: table.querySelectorAll('tbody tr').length,
                    stacked: row ? getComputedStyle(row).display !== 'table-row'
                                 : null,
                    sideways: document.documentElement.scrollWidth
                              > document.documentElement.clientWidth + 1,
                  };
                }""", selector)
                if width in (768, 700):
                    page.screenshot(
                        path=str(OUT / f'close-{route}-{width}.png'),
                        full_page=True)
            print(f'    {width}px  ' + '  '.join(
                f'{k}: rows={v["rows"]} stacked={v.get("stacked")}'
                for k, v in shapes.items()))
            check(f'{width}px: chatter is {"stacked" if width <= 860 else "tabular"}',
                  shapes['chatter'].get('stacked') is (width <= 860))
            check(f'{width}px: chatter does not scroll sideways',
                  not shapes['chatter'].get('sideways'))
            for page_name in ('watching', 'activity'):
                shape = shapes[page_name]
                check(f'{width}px: {page_name} has rows to judge',
                      shape['rows'] > 0, f'rows={shape["rows"]}')
                check(f'{width}px: {page_name} is '
                      f'{"stacked" if width <= 700 else "tabular"}',
                      shape.get('stacked') is (width <= 700),
                      f'stacked={shape.get("stacked")}')
                check(f'{width}px: {page_name} does not scroll sideways',
                      not shape.get('sideways'))
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
