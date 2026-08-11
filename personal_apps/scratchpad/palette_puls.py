"""Measure the "Puls" palette instead of asserting it.

Both themes are first-class (PRODUCT.md 4.3), so every pairing that actually
occurs is checked twice -- a value that only passes in one theme is not done.
Also simulates protanopia/deuteranopia to prove --live / --record / --stall stay
separable, since that is the constraint that moved ATTENTION from red to cyan.

Run:  python scratchpad/palette_puls.py
"""

# Each accent needs TWO values, not one. A colour bright enough to work as a
# FILL under dark label text is not dark enough to work as TEXT on a light
# surface, and vice versa -- the same arithmetic collision the previous system
# hit with its blue. In the dark theme the two can coincide (a bright accent
# reads fine as text on an aubergine field); in the light theme they cannot,
# so `*-ink` is a deeper cut of the same hue.
LIGHT = {
    'ground':     '#F3EAF7',
    'chassis':    '#FFFFFF',
    'raised':     '#EEE5F3',
    'edge':       '#DACAE3',
    'edge-hi':    '#C2ABCF',
    'ink':        '#291238',
    'dim':        '#634674',
    'unlit':      '#6C537E',
    'live':       '#C2410C',
    'live-ink':   '#A83409',
    'live-deep':  '#8E2C07',
    'on-live':    '#FFF4EE',
    'done':       '#8B3A62',
    'done-ink':   '#7A3256',
    'on-done':    '#FFF0F6',
    'record':     '#F0B429',
    'record-ink': '#6B4400',
    'on-record':  '#3A2600',
    'stall':      '#0C7382',
    'stall-ink':  '#0F6B78',
    'on-stall':   '#ECFBFD',
}

DARK = {
    'ground':     '#241132',
    'chassis':    '#371B49',
    'raised':     '#1B0B26',
    'edge':       '#472B5A',
    'edge-hi':    '#634077',
    'ink':        '#F8F1FB',
    'dim':        '#C5ACD2',
    'unlit':      '#9E86AD',
    'live':       '#FF7A4D',
    'live-ink':   '#FF7A4D',
    'live-deep':  '#D2411A',
    'on-live':    '#2A0A00',
    'done':       '#F1C8DD',
    'done-ink':   '#F1C8DD',
    'on-done':    '#2A1233',
    'record':     '#FFC861',
    'record-ink': '#FFC861',
    'on-record':  '#2A1D00',
    'stall':      '#5FDDEC',
    'stall-ink':  '#5FDDEC',
    'on-stall':   '#04262C',
}

# text colour -> the surfaces it actually sits on
TEXT_ON_SURFACE = {
    'ink':        ('ground', 'chassis', 'raised'),
    'dim':        ('ground', 'chassis', 'raised'),
    'unlit':      ('ground', 'chassis', 'raised'),
    'live-ink':   ('ground', 'chassis', 'raised'),
    'record-ink': ('ground', 'chassis', 'raised'),
    'stall-ink':  ('ground', 'chassis', 'raised'),
    'done-ink':   ('ground', 'chassis', 'raised'),
}
# label colour -> the saturated fill it sits on
ON_FILL = {
    'on-live': 'live',
    'on-done': 'done',
    'on-record': 'record',
    'on-stall': 'stall',
}
# what CVD separability is actually measured on: the fills, since that is what
# carries the state at a glance across a room-lit gym
CVD_ROLES = ('live', 'record', 'stall')

AA_BODY = 4.5
AA_LARGE = 3.0
# the previous system measured a 79/255 minimum pair distance; hold near that
CVD_FLOOR = 60.0


def rgb(hex_):
    hex_ = hex_.lstrip('#')
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_):
    r, g, b = (_lin(c) for c in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _unlin(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def cvd(hex_, kind):
    """Simulate the colour as seen, and return it back in sRGB 0-255.

    Returning sRGB rather than raw LMS matters: LMS magnitudes scale with
    luminance, so a distance measured there is systematically smaller for a
    light theme's dark accents than for a dark theme's bright ones, and the two
    themes cannot be held to one threshold. In sRGB both are on the same 0-255
    ruler, which is what the previous palette script used and what the 79/255
    figure in the project's history refers to.
    """
    r, g, b = (_lin(c) for c in rgb(hex_))
    l = 0.31399022 * r + 0.63951294 * g + 0.04649755 * b
    m = 0.15537241 * r + 0.75789446 * g + 0.08670142 * b
    s = 0.01775239 * r + 0.10944209 * g + 0.87256922 * b
    if kind == 'protan':
        l = 1.05118294 * m - 0.05116099 * s
    else:  # deutan
        m = 0.9513092 * l + 0.04866992 * s
    r2 = 5.47221206 * l - 4.6419601 * m + 0.16963708 * s
    g2 = -1.1252419 * l + 2.29317094 * m - 0.1678952 * s
    b2 = 0.02980165 * l - 0.19318073 * m + 1.16364789 * s
    return tuple(_unlin(c) * 255 for c in (r2, g2, b2))


def cvd_distance(a, b, kind):
    pa, pb = cvd(a, kind), cvd(b, kind)
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


def audit(name, tokens):
    print('=' * 62)
    print(name)
    print('=' * 62)
    worst = []
    for text, surfaces in TEXT_ON_SURFACE.items():
        for surface in surfaces:
            ratio = contrast(tokens[text], tokens[surface])
            ok = ratio >= AA_BODY
            worst.append((ratio, f'{text}/{surface}', ok))
            print(f'  {text:<8}/ {surface:<8} {ratio:5.2f}  {"ok" if ok else "FAIL (AA 4.5)"}')
    print('  ---- text on the saturated fills ----')
    for label, fill in ON_FILL.items():
        ratio = contrast(tokens[label], tokens[fill])
        ok = ratio >= AA_BODY
        worst.append((ratio, f'{label}/{fill}', ok))
        print(f'  {label:<10}/{fill:<8} {ratio:5.2f}  {"ok" if ok else "FAIL (AA 4.5)"}')

    print('  ---- accent-fill separability under CVD (sRGB 0-255) ----')
    cvd_ok = True
    for kind in ('protan', 'deutan'):
        pairs = []
        for i, a in enumerate(CVD_ROLES):
            for b in CVD_ROLES[i + 1:]:
                pairs.append((cvd_distance(tokens[a], tokens[b], kind), f'{a}~{b}'))
        lo, which = min(pairs)
        ok = lo >= CVD_FLOOR
        cvd_ok = cvd_ok and ok
        print(f'  {kind:<7} closest pair {which:<14} distance {lo:6.1f}'
              f'  {"ok" if ok else f"TOO CLOSE (floor {CVD_FLOOR})"}')

    fails = [w for w in worst if not w[2]]
    print(f'\n  {len(worst) - len(fails)}/{len(worst)} pairings pass AA; '
          f'floor {min(w[0] for w in worst):.2f}')
    if fails:
        print('  FAILING: ' + ', '.join(f'{n} {r:.2f}' for r, n, _ in fails))
    return (not fails) and cvd_ok


if __name__ == '__main__':
    ok_light = audit('LIGHT  ·  pale plum field', LIGHT)
    print()
    ok_dark = audit('DARK  ·  aubergine field', DARK)
    print()
    print('BOTH THEMES PASS' if (ok_light and ok_dark) else 'NOT DONE -- fix the failures above')
