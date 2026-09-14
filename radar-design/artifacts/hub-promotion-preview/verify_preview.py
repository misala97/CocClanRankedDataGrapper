import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = 'http://127.0.0.1:5033'
OUT = Path(__file__).parent


def login(page):
    page.goto(f'{BASE}/login', wait_until='domcontentloaded')
    page.locator('#username').fill('releaseverify')
    page.locator('#password').fill('release-verify-local')
    page.get_by_role('button', name='Anmelden').click()
    page.wait_for_load_state('domcontentloaded')


def inspect(browser, width, height, name):
    page = browser.new_page(viewport={'width': width, 'height': height})
    board_requests = []
    page.on('request', lambda request: board_requests.append(request.url)
            if '/radar/api/board' in request.url else None)
    login(page)

    page.goto(f'{BASE}/radar/', wait_until='domcontentloaded')
    page.get_by_role('main', name='Overview').wait_for()
    assert page.locator('#radar-hub-data').count() == 1
    page.screenshot(path=str(OUT / f'root-{name}.png'), full_page=True)

    page.goto(f'{BASE}/radar/hub/', wait_until='domcontentloaded')
    page.get_by_role('main', name='Overview').wait_for()
    assert page.locator('#radar-hub-data').count() == 1

    page.goto(f'{BASE}/radar/#chatter', wait_until='domcontentloaded')
    page.get_by_role('main', name='Human Chatter').wait_for()
    candidates = page.locator('[data-testid="rh-row-ticker"], [data-testid="rh-candidate-ticker"]')
    candidates.first.wait_for(timeout=15000)
    tickers = candidates.all_inner_texts()
    assert tickers
    ticker = tickers[0]
    assert any('sort=chatter' in url and 'dir=desc' in url for url in board_requests)

    page.goto(f'{BASE}/radar/?t={ticker}&market=de&window=12', wait_until='domcontentloaded')
    page.get_by_role('main', name='Human Chatter').wait_for()
    assert ticker in page.locator('body').inner_text()

    page.goto(f'{BASE}/radar/?t={ticker}#nonsense', wait_until='domcontentloaded')
    page.get_by_role('main', name='Human Chatter').wait_for()
    assert ticker in page.locator('body').inner_text()

    page.goto(f'{BASE}/radar/?market=de&window=24', wait_until='domcontentloaded')
    page.get_by_role('main', name='Human Chatter').wait_for()
    page.screenshot(path=str(OUT / f'filters-{name}.png'), full_page=True)
    page.reload(wait_until='domcontentloaded')
    page.get_by_role('main', name='Human Chatter').wait_for()

    page.goto(f'{BASE}/radar/?t={ticker}&market=de#overview', wait_until='domcontentloaded')
    page.get_by_role('main', name='Overview').wait_for()
    assert page.url.endswith('#overview')

    page.goto(f'{BASE}/radar/legacy/?t={ticker}&market=de&window=12', wait_until='domcontentloaded')
    assert page.locator('#radar-data').count() == 1
    assert page.locator('#radar-hub-data').count() == 0
    assert page.get_by_role('link', name='Return to Radar hub').get_attribute('href').startswith('/radar/?t=')
    page.screenshot(path=str(OUT / f'legacy-{name}.png'), full_page=True)
    page.get_by_role('link', name='Return to Radar hub').click()
    page.get_by_role('main', name='Human Chatter').wait_for()
    page.close()
    return {'viewport': [width, height], 'ticker': ticker, 'board_requests': board_requests}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    result = {
        'desktop': inspect(browser, 1440, 1000, 'desktop'),
        'mobile': inspect(browser, 390, 844, 'mobile'),
    }
    browser.close()

(OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
