"""The annotated before/after comparison the VC1 contract asks for.

Same data, same viewport, same browser -- the only difference between the two
halves is the bundle. Numbers come from the measurement files rather than from
this script, so the caption cannot drift from what was measured.
"""
import base64
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

SHOTS = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()

PAIRS = [
    ('fixture', '1440', 'Fictional fixture at 1440x1000'),
    ('real', '1440', 'Local development data at 1440x1000'),
    ('fixture', '768', 'Fictional fixture at 768x1024'),
]


def data_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(
        path.read_bytes()).decode('ascii')


def main():
    before = json.loads((SHOTS / 'before-measurements.json').read_text('utf-8'))
    after = json.loads((SHOTS / 'after-measurements.json').read_text('utf-8'))

    blocks = []
    for slug, width, caption in PAIRS:
        key = f'{slug}-{width}'
        b, a = before.get(key), after.get(key)

        def note(m):
            if not m:
                return 'not measured'
            ordinary = [r['height'] for r in m['rows'] if not r['marks']]
            marked = [r['height'] for r in m['rows'] if r['marks']]
            parts = []
            if ordinary:
                parts.append(f'plain row {min(ordinary)}–{max(ordinary)}px '
                             f'(five would be {min(ordinary) * 5}px)')
            if marked:
                parts.append(f'flagged row {min(marked)}–{max(marked)}px')
            parts.append('tone bar '
                         + (f'{m["toneBarWidth"]}×{m["toneBarHeight"]}px'
                            if m['toneBarWidth'] else 'none'))
            if m['scrollsSideways']:
                parts.append('DOCUMENT SCROLLS SIDEWAYS')
            return ' · '.join(parts)

        blocks.append(f"""
        <section>
          <h2>{caption}</h2>
          <div class="pair">
            <figure>
              <figcaption><b class="bad">Before</b> — deployed build
                <code>hub-Cr-xj2rB.js</code>, from d3bc795</figcaption>
              <p class="note">{note(b)}</p>
              <img src="{data_uri(SHOTS / f'before-{slug}-{width}.png')}">
            </figure>
            <figure>
              <figcaption><b class="good">After</b> — the VC1 correction</figcaption>
              <p class="note">{note(a)}</p>
              <img src="{data_uri(SHOTS / f'after-{slug}-{width}.png')}">
            </figure>
          </div>
        </section>""")

    html = f"""<!doctype html><meta charset="utf-8">
<style>
  body {{ font: 13px/1.5 Inter, system-ui, sans-serif; margin: 0; padding: 26px;
         background: #FBFBFC; color: #1d2b26; }}
  h1 {{ font-size: 21px; margin: 0 0 4px; }}
  .lede {{ color: #5d6b66; margin: 0 0 22px; max-width: 100ch; }}
  h2 {{ font-size: 15px; margin: 26px 0 10px; }}
  .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  figure {{ margin: 0; }}
  figcaption {{ font-size: 12px; margin-bottom: 3px; }}
  .note {{ font-size: 11px; color: #5d6b66; margin: 0 0 7px; min-height: 2.6em; }}
  img {{ width: 100%; border: 1px solid #dfe4e2; border-radius: 7px;
         display: block; background: #fff; }}
  code {{ font-size: 11px; color: #5d6b66; }}
  .bad {{ color: #a33; }} .good {{ color: #2f6f56; }}
</style>
<h1>Human chatter — VC1 before and after</h1>
<p class="lede">Both halves of every pair are the same payload rendered by the
same browser at the same viewport. The only difference is the bundle: the left
is the build that is deployed today, the right is the correction. The fictional
fixture is labelled as such; the “local development data” pair is real rows from
the disposable copy of the development database, not production and not today.</p>
{''.join(blocks)}
"""
    page_file = SHOTS / 'comparison.html'
    page_file.write_text(html, encoding='utf-8')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1500, 'height': 1200})
        page.goto(page_file.as_uri(), wait_until='networkidle')
        page.screenshot(path=str(OUT / 'comparison-1440.png'), full_page=True)
        browser.close()
    print(f'wrote {OUT / "comparison-1440.png"}')


if __name__ == '__main__':
    main()
