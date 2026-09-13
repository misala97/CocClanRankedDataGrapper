from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'radar-design' / 'artifacts'
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100},
                                device_scale_factor=1)
        page.goto('http://127.0.0.1:5021/login', wait_until='networkidle')
        page.fill('input[name="username"]', 'b1cadmin')
        page.fill('input[name="password"]', 'b1c-local-only')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.goto('http://127.0.0.1:5021/radar/hub/?segment=discover',
                  wait_until='networkidle')
        page.locator('#radar-hub-root').wait_for()
        page.wait_for_timeout(1200)
        page.get_by_text('Human chatter', exact=True).click()
        page.wait_for_timeout(1200)
        for width in (1440, 1920, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1100})
            page.screenshot(path=str(OUT / f'b1c-{width}.png'), full_page=True)
        group = page.locator('[role="group"][aria-label^="Chatter tone intervals"]')
        before = group.locator('.chatter-interval-detail').inner_text()
        group.focus()
        group.press('ArrowRight')
        after = group.locator('.chatter-interval-detail').inner_text()
        group.press('Escape')
        print('url', page.url)
        print('title', page.title())
        print('histograms', page.locator('.chatter-histogram').count())
        print('overflow', page.evaluate(
            '() => document.documentElement.scrollWidth > document.documentElement.clientWidth'))
        print('keyboard_changed_detail', before != after)
        print('escape_cleared_detail', group.locator('.chatter-interval-detail').count() == 0)
        browser.close()


if __name__ == '__main__':
    main()
