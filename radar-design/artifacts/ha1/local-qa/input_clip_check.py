import json, sys
sys.path.insert(0, 'scratchpad/ha1')
import verify_preview as vp
from playwright.sync_api import sync_playwright
port, manifest, creds, fp = vp.preflight(['x', '5041'])
base = f'http://127.0.0.1:{port}'
res = {'fingerprint': fp['digest']}
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (320, 390, 768):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, has_touch=w < 768)
        page = ctx.new_page(); vp.login(page, base, *creds['admin'])
        page.goto(vp.link(base, manifest, 'typical')); vp.wait_ready(page)
        res[w] = page.evaluate("""() => Array.from(document.querySelectorAll('form.rh-an-range input')).map(i => ({name: i.name, value: i.value, clientWidth: i.clientWidth, scrollWidth: i.scrollWidth, clipped: i.scrollWidth > i.clientWidth}))""")
        ctx.close()
    b.close()
print(json.dumps(res, indent=1))
