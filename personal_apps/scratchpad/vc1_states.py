"""The three remaining Chatter states the contract lists: no search match,
loading, and a failed refresh.

Loading and error are driven by making the board request slow or fail, which
is what the real page does when the server is slow or down -- not by rendering
a component in isolation.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1]).resolve()
BASE = sys.argv[2]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # No search match: the filter narrows what is already listed, and the
        # message has to say that rather than "empty board".
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='networkidle')
        page.wait_for_selector('.rh-chatter')
        page.fill('.rh-tablefilter input', 'zzzzz')
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / 'state-nomatch-1440.png'), full_page=True)
        print('nomatch:', page.inner_text('.rh-panelempty').replace('\n', ' '))
        page.close()

        # A failed refresh. The first board is embedded, so the page renders
        # and then the refetch fails -- which is the interesting case: the
        # rows must not vanish because a later request did.
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.route('**/radar/api/board*', lambda route: route.abort())
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-main')
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / 'state-refresh-failed-1440.png'),
                        full_page=True)
        has_rows = page.locator('.rh-chatter tbody tr').count()
        print(f'failed refresh: rows still shown = {has_rows}')
        context.close()

        # A filter change still in flight. This is the only loading state
        # Chatter really has: the first board is embedded in the page, so
        # first paint has nothing to wait for, and a screenshot of it is
        # byte-identical to the failed-refresh one above -- which is the
        # honest answer, not two states.
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        held = []
        page.route('**/radar/api/board*', lambda route: held.append(route))
        page.goto(f'{BASE}/fixture.html#chatter', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-chatter')
        page.select_option('.rh-filters label:nth-of-type(2) select', '1')
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / 'state-loading-1440.png'), full_page=True)
        rows = page.locator('.rh-chatter tbody tr').count()
        print(f'filter change in flight: held requests = {len(held)}, '
              f'rows still shown = {rows}')
        context.close()

        browser.close()


if __name__ == '__main__':
    main()
