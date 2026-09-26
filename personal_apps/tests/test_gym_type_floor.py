"""D11 (the walkthrough's visual rulings): text that carries data on the gym
pages is never under 13 px.

gym.css is where every text size on those pages comes from -- figtree.css
sets none, and the TSX and the templates set none (B12's survey) -- and it
takes them from a fixed rem scale: the --t-* and --num-* tokens, defined once
at :root, and rem/px literals. The two steps under 13 px are left to
navigation chrome, the tab bar's labels and the account footer's links, and
nothing else may use them.

A size the file can't settle is not guessed at: one relative to its parent
(em, %, the smaller keywords), to the viewport or a container, or worked out
in calc() fails, and so do a var() the file never defines (with no fallback),
a custom property that refers back to itself, and a root font size (the rem
itself). The rest band's fluid numerals are the one exception, named below."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / 'static' / 'gym' / 'gym.css').read_text(encoding='utf-8')
FLOOR_PX = 13
CHROME = {'.tabbar__tab', '.nav-footer a'}
# The rest countdown's numeral, min(3.5rem, 48cqi): the container is the rest
# band, as wide as the card, so it drops under 13 px only in a band under 28 px.
FLUID = {'.restband__num', '.restband__num.is-long'}
VAR = re.compile(r'(?<![\w-])var\(', re.I)
LENGTH = re.compile(r'(\d*\.?\d+)([a-z%]+)', re.I)
ODD = re.compile(r'calc\(|\b(?:smaller|x-small|xx-small|xxx-small)\b', re.I)


def _rules():
    """(selector, [(property, value)]) for every rule, comments stripped and
    !important dropped; a rule inside an at-rule is found on its own."""
    text = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)
    rules = []
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', text):
        declarations = []
        for part in body.split(';'):
            name, colon, value = part.partition(':')
            if colon:
                declarations.append((name.strip().lower(), re.sub(r'!\s*important', '', value, flags=re.I).strip()))
        rules.append((' '.join(selector.split()), declarations))
    return rules


RULES = _rules()
PROPS = {}
for _, _declarations in RULES:
    for _name, _value in _declarations:
        if _name.startswith('--'):
            PROPS.setdefault(_name, []).append(_value)


def _split(text, sep):
    """text split at each sep outside parentheses and brackets."""
    parts, depth, start = [], 0, 0
    for at, char in enumerate(text):
        if char in '([':
            depth += 1
        elif char in ')]':
            depth -= 1
        elif char == sep and not depth:
            parts.append(text[start:at])
            start = at + 1
    return parts + [text[start:]]


def _var_calls(value):
    """(start, end, name, fallback) of each outermost var() in value. The
    parentheses inside a fallback are counted, so var(--x, max(1rem, 2rem))
    is one call whose fallback is max(1rem, 2rem); no fallback is None."""
    calls, at = [], 0
    while match := VAR.search(value, at):
        depth, end = 1, match.end()
        while depth and end < len(value):
            depth += {'(': 1, ')': -1}.get(value[end], 0)
            end += 1
        assert not depth, f'an unclosed var(): {value}'
        name, comma, fallback = value[match.end():end - 1].partition(',')
        calls.append((match.start(), end, name.strip(), fallback.strip() if comma else None))
        at = end
    return calls


SETTLED = {}


def _property(name, chain):
    """Every text a custom property can come to, through each of its
    definitions (at :root, on an element, inside an at-rule). Each property
    is followed once -- the file's definitions don't change -- so the work
    stays the size of the file however the properties refer to each other."""
    assert name not in chain, f'{" -> ".join(chain + (name,))}: the property refers back to itself'
    if name not in SETTLED:
        texts = {}
        for definition in PROPS[name]:
            texts.update(dict.fromkeys(_texts(definition, chain + (name,))))
        SETTLED[name] = tuple(texts)
    return SETTLED[name]


def _texts(value, chain=()):
    """Every text a value can come to: its own text outside var(), and for
    each var() every text of that property and of its fallback, so a size
    anywhere down the chain shows."""
    own, texts, at = [], {}, 0
    for start, end, name, fallback in _var_calls(value):
        own.append(value[at:start])
        at = end
        assert name in PROPS or fallback is not None, f'var({name}) is never defined and has no fallback'
        if name in PROPS:
            texts.update(dict.fromkeys(_property(name, chain)))
        if fallback is not None:
            texts.update(dict.fromkeys(_texts(fallback, chain)))
    own.append(value[at:])
    return (' '.join(own), *texts)


def _font_values():
    for selector, declarations in RULES:
        for name, value in declarations:
            if name in ('font', 'font-size'):
                try:
                    texts = _texts(value)
                except AssertionError as unsettled:
                    raise AssertionError(f'{selector}: {value}: {unsettled}') from None
                yield selector, value, ' '.join(texts)


def _picks_the_root(selector):
    """Whether one selector of a list picks the root element itself: html or
    :root with anything but a combinator after it (html.x, :root:not(...))."""
    flat = selector.strip()
    while (inner := re.sub(r'\([^()]*\)|\[[^\[\]]*\]', '', flat)) != flat:
        flat = inner
    return bool(re.match(r'(?:html|:root)(?![\w-])', flat, re.I)) and not re.search(r'[\s>+~]', flat)


def test_no_text_is_set_under_13px_outside_the_chrome():
    small = []
    for selector, value, full in _font_values():
        for number, unit in LENGTH.findall(full):
            px = float(number) * {'rem': 16, 'px': 1}.get(unit.lower(), 0)
            if 0 < px < FLOOR_PX and selector not in CHROME:
                small.append(f'{selector}: {value} ({px:g}px)')
    assert small == []


def test_sizes_come_from_the_fixed_scale():
    """em, % and the smaller keywords follow their parent down: 0.85em inside
    13 px meta text is 11 px again, and no token shows it. calc(), viewport
    and container units are sizes this file can't settle."""
    odd = []
    for selector, value, full in _font_values():
        units = {unit.lower() for _, unit in LENGTH.findall(full)} - {'rem', 'px'}
        if selector in FLUID:
            units -= {'cqi'}
        if units or ODD.search(full):
            odd.append(f'{selector}: {value}')
    assert odd == []


def test_the_scale_is_defined_once_at_root():
    """A token redefined on some element would shrink every size under it
    that the first test read at its :root value."""
    moved = [f'{selector}: {name}' for selector, declarations in RULES for name, _ in declarations
             if re.match(r'--(?:t|num)-', name) and selector != ':root']
    assert moved == []


def test_the_root_size_is_left_to_the_browser():
    """The rem the whole scale is counted in: 13 px is 0.8125rem only while
    the root keeps the browser's (and the lifter's) own size."""
    set_root = [f'{selector}: {value}' for selector, declarations in RULES
                if any(_picks_the_root(part) for part in _split(selector, ','))
                for name, value in declarations if name in ('font', 'font-size')]
    assert set_root == []
