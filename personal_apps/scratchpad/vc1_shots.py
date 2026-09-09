"""Capture the VC1 screenshots and the measurements the contract names.

Batched: one browser, every viewport and page in one run, because a dozen
small round trips is a dozen chances for the browser to be in a different
state than the last one.

    py -3.12 scratchpad/vc1_shots.py <outdir> <tag> [base-url]
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1])
TAG = sys.argv[2] if len(sys.argv) > 2 else 'after'
BASE = sys.argv[3] if len(sys.argv) > 3 else 'http://127.0.0.1:5061/scratchpad/vc1'

VIEWPORTS = [
    ('1440', 1440, 1000),
    ('1920', 1920, 1080),
    ('1024', 1024, 768),
    ('768', 768, 1024),
    ('390', 390, 844),
    ('320', 320, 800),
]

PAGES = ['real', 'fixture', 'dense', 'empty']

MEASURE = """() => {
  const table = document.querySelector('.rh-chatter') || document.querySelector('.rh-table');
  if (!table) return null;
  const head = Array.from(table.querySelectorAll('thead th'))
      .map((th) => ({ label: th.textContent.trim(),
                      width: Math.round(th.getBoundingClientRect().width) }));
  const rows = Array.from(table.querySelectorAll('tbody tr'))
      .map((tr) => ({
        ticker: (tr.querySelector('[data-testid=rh-row-ticker]') || {}).textContent,
        height: Math.round(tr.getBoundingClientRect().height),
        marks: tr.querySelectorAll('.rh-badge').length,
      }));
  const bar = table.querySelector('.rh-tonebar');
  const wrap = table.closest('.rh-tablewrap');
  return {
    tableWidth: Math.round(table.getBoundingClientRect().width),
    head,
    rows,
    toneBarWidth: bar ? Math.round(bar.getBoundingClientRect().width) : null,
    toneBarHeight: bar ? Math.round(bar.getBoundingClientRect().height) : null,
    fiveRows: rows.slice(0, 5).reduce((sum, r) => sum + r.height, 0),
    scrollsSideways: document.documentElement.scrollWidth
                     > document.documentElement.clientWidth + 1,
    tableOverflows: wrap ? wrap.scrollWidth > wrap.clientWidth + 1 : null,
    fonts: (() => {
      const pick = (sel) => {
        const el = table.querySelector(sel);
        return el ? getComputedStyle(el).fontSize : null;
      };
      return { value: pick('tbody strong'), sub: pick('.rh-sub'),
               head: pick('thead th') };
    })(),
  };
}"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, width, height in VIEWPORTS:
            context = browser.new_context(viewport={'width': width,
                                                    'height': height},
                                          device_scale_factor=1)
            page = context.new_page()
            page.on('console', lambda m: errors.append(f'{name} console {m.type}: {m.text}')
                    if m.type == 'error' else None)
            page.on('pageerror', lambda e: errors.append(f'{name} pageerror: {e}'))
            for slug in PAGES:
                # Only the primary pages get every width; the density and empty
                # states are about content, not layout.
                if slug in ('dense', 'empty') and name not in ('1440', '390'):
                    continue
                # #chatter: the hub opens on Overview otherwise.
                page.goto(f'{BASE}/{slug}.html#chatter', wait_until='networkidle')
                page.wait_for_selector('.rh-main', timeout=15000)
                page.wait_for_timeout(250)
                shot = OUT / f'{TAG}-{slug}-{name}.png'
                page.screenshot(path=str(shot), full_page=(slug != 'dense'))
                if slug in ('real', 'fixture'):
                    report[f'{slug}-{name}'] = page.evaluate(MEASURE)
            context.close()
        browser.close()

    (OUT / f'{TAG}-measurements.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'errors': errors}, indent=2))
    for key, value in report.items():
        if not value:
            print(f'{key}: NO TABLE')
            continue
        print(f'{key}: table {value["tableWidth"]}px  '
              f'five rows {value["fiveRows"]}px  '
              f'bar {value["toneBarWidth"]}x{value["toneBarHeight"]}  '
              f'sideways {value["scrollsSideways"]}  '
              f'fonts {value["fonts"]}')


if __name__ == '__main__':
    main()
