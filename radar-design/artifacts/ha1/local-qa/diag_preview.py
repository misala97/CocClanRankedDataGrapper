"""LOCAL-QA diagnosis of verify_preview run2 failures, each in a FRESH context.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/diag_preview.py 5041   (cwd personal_apps)

Uses verify_preview.preflight (same gates, identity and fingerprint refusal).
Separates harness faults from product behaviour for: filter-only query text,
skip-link starting point, loading hold/release order, 8 s timeout, network
abort + Retry, session expiry. Injected responses are UI-state checks only,
never backend evidence. Writes diag_preview.out.json next to this file.
"""
import json
import sys
from pathlib import Path

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(PERSONAL / 'scratchpad' / 'ha1'))

import verify_preview as vp  # noqa: E402

port, manifest, credentials, fingerprint = vp.preflight(sys.argv)
base = f'http://127.0.0.1:{port}'
out = {'port': port, 'fingerprint': fingerprint['digest'], 'injected_ui_only': True}
main_text = lambda page: (page.text_content(vp.MAIN) or '')[:600]  # noqa: E731


def fresh(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    vp.login(page, base, *credentials['admin'])
    return context, page


from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()

    context, page = fresh(browser)
    page.goto(f'{base}/radar/?market=de&window=24')
    page.wait_for_selector('main[aria-label="Human Chatter"]')
    out['filter_only'] = {'search': page.evaluate('location.search'), 'hash': page.evaluate('location.hash')}
    context.close()

    context, page = fresh(browser)
    page.goto(vp.link(base, manifest, 'lines'))
    vp.wait_ready(page)
    page.goto(vp.link(base, manifest, 'typical'))
    vp.wait_ready(page)
    skip = {'active_after_load': page.evaluate(vp.FOCUS_JS)}
    page.evaluate('document.activeElement && document.activeElement.blur()')
    page.keyboard.press('Tab')
    skip['tab_after_blur'] = page.evaluate(vp.FOCUS_JS)
    page.reload()
    vp.wait_ready(page)
    skip['active_after_reload'] = page.evaluate(vp.FOCUS_JS)
    page.keyboard.press('Tab')
    skip['tab_after_reload_no_interaction'] = page.evaluate(vp.FOCUS_JS)
    address = page.url
    if skip['tab_after_reload_no_interaction'] == 'skip':
        page.keyboard.press('Enter')
        skip['after_enter'] = page.evaluate(vp.FOCUS_JS)
        skip['route_unchanged'] = page.url == address
    context.close()
    out['skip_link'] = skip

    context, page = fresh(browser)
    held = []
    page.route(vp.COMPANY_API, lambda route: held.append(route))
    page.goto(vp.link(base, manifest, 'typical'))
    page.wait_for_selector(f'{vp.MAIN} [role=status]:has-text("Reading")')
    loading = {'held_routes': len(held), 'status_text': page.text_content(f'{vp.MAIN} [role=status]')}
    for route in held:
        route.continue_()
    page.unroute(vp.COMPANY_API)
    vp.wait_ready(page)
    loading['days_visible_after_release'] = page.is_visible(vp.DAY_GROUP)
    out['loading_release_before_unroute'] = loading
    context.close()

    context, page = fresh(browser)
    held = []
    page.route(vp.COMPANY_API, lambda route: held.append(route))
    page.goto(vp.link(base, manifest, 'one_close'))
    page.wait_for_timeout(vp.harness.BROWSER_TIMEOUT_MS + 1500)
    out['timeout'] = {'held_routes': len(held), 'main': main_text(page)}
    for route in held:
        route.abort()
    page.unroute(vp.COMPANY_API)
    context.close()

    context, page = fresh(browser)
    page.route(vp.COMPANY_API, lambda route: route.abort())
    page.goto(vp.link(base, manifest, 'regime'))
    try:
        page.wait_for_selector(f'{vp.MAIN} [role=alert]', timeout=15000)
        alert = True
    except Exception:  # noqa: BLE001 -- recorded
        alert = False
    network = {'alert': alert, 'main': main_text(page)}
    page.unroute(vp.COMPANY_API)
    if alert:
        page.click(f'{vp.MAIN} button:has-text("Retry")')
        vp.wait_ready(page)
        network['retry_recovered'] = page.is_visible(vp.DAY_GROUP)
    out['network_abort'] = network
    context.close()

    context, page = fresh(browser)
    responses = []
    page.on('response', lambda r: responses.append({'url': r.url, 'status': r.status,
                                                    'type': r.headers.get('content-type')})
            if '/radar/api/analysis/' in r.url or '/login' in r.url else None)
    page.goto(vp.link(base, manifest, 'typical'))
    vp.wait_ready(page)
    context.clear_cookies()
    responses.clear()
    page.fill('input[name=analysis_to]', manifest['window']['from'])
    page.fill('input[name=analysis_from]', manifest['window']['from'])
    page.click('button:has-text("Show these days")')
    page.wait_for_timeout(10000)
    out['session_expiry'] = {'responses': responses, 'url': page.url, 'main': main_text(page),
                             'body_has_session_expired': 'Session expired' in (page.text_content('body') or ''),
                             'days_visible': page.is_visible(vp.DAY_GROUP)}
    page.screenshot(path=str(Path(__file__).with_name('diag-session-expiry-1440.png')), full_page=True)
    context.close()
    browser.close()

Path(__file__).with_name('diag_preview.out.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
