"""Upstream product and book databases, and the one shape the page reads.

Open Food Facts answers every product type from one URL: with
`product_type=all`, a code that belongs to a sister database (beauty, pet
food, other products) comes back as a 302 to that database -- verified
2026-09-24 -- so one request covers food and non-food. Books go to the
Deutsche Nationalbibliothek, which holds every German-language title and
answers without a key.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import requests

from .codes import classify, gs1_label

# OFF asks clients to name themselves. No contact details: it identifies the
# app, not the person using it.
USER_AGENT = 'PersonalApps-Barcode/1.0'
TIMEOUT = 8

OFF_URL = 'https://world.openfoodfacts.org/api/v2/product/{code}.json'
OFF_ADD_URL = ('https://world.openfoodfacts.org/cgi/product.pl'
               '?type=search_or_add&action=process&code={code}')
OFF_FIELDS = ','.join([
    'code', 'product_type', 'product_name', 'product_name_de', 'generic_name', 'generic_name_de',
    'brands', 'quantity', 'product_quantity_unit', 'serving_size', 'image_front_small_url',
    'nutriscore_grade', 'nova_group', 'ecoscore_grade', 'nutriments',
    'ingredients_text', 'ingredients_text_de', 'allergens_tags', 'traces_tags',
    'ingredients_analysis_tags', 'labels_tags',
])
DNB_URL = 'https://services.dnb.de/sru/dnb'
DNB_COVER_URL = 'https://portal.dnb.de/opac/mvb/cover'
# Raster formats only: an SVG served from our own origin could carry script.
_COVER_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
# The DNB answers "no cover" with a tiny placeholder rather than a 404.
_COVER_MIN_BYTES = 1000

# Final host after OFF's redirect -> (product type, database name).
_FLAVORS = {
    'world.openfoodfacts.org': ('food', 'Open Food Facts'),
    'world.openbeautyfacts.org': ('beauty', 'Open Beauty Facts'),
    'world.openpetfoodfacts.org': ('petfood', 'Open Pet Food Facts'),
    'world.openproductsfacts.org': ('product', 'Open Products Facts'),
}
_IMAGE_HOSTS = {'images.openfoodfacts.org', 'images.openbeautyfacts.org',
                'images.openpetfoodfacts.org', 'images.openproductsfacts.org'}

# Table order of the nutrition label printed on German packs.
_NUTRIENTS = [
    ('energy-kcal', 'Energie', 'kcal'),
    ('fat', 'Fett', 'g'),
    ('saturated-fat', 'davon gesättigte Fettsäuren', 'g'),
    ('carbohydrates', 'Kohlenhydrate', 'g'),
    ('sugars', 'davon Zucker', 'g'),
    ('fiber', 'Ballaststoffe', 'g'),
    ('proteins', 'Eiweiß', 'g'),
    ('salt', 'Salz', 'g'),
]
_SUB_ROWS = {'saturated-fat', 'sugars'}

# The 14 allergens EU law makes packs declare, as German packs name them.
_ALLERGENS_DE = {
    'en:gluten': 'Gluten', 'en:crustaceans': 'Krebstiere', 'en:eggs': 'Eier',
    'en:fish': 'Fisch', 'en:peanuts': 'Erdnüsse', 'en:soybeans': 'Soja',
    'en:milk': 'Milch', 'en:nuts': 'Schalenfrüchte', 'en:celery': 'Sellerie',
    'en:mustard': 'Senf', 'en:sesame-seeds': 'Sesam',
    'en:sulphur-dioxide-and-sulphites': 'Schwefeldioxid/Sulfite',
    'en:lupin': 'Lupinen', 'en:molluscs': 'Weichtiere',
}

_SRW = '{http://www.loc.gov/zing/srw/}'
_DC = '{http://purl.org/dc/elements/1.1/}'
_XSI_TYPE = '{http://www.w3.org/2001/XMLSchema-instance}type'
_PAGES = re.compile(r'(\d+)\s*(?:S\.|Seiten)')
# "978-3-423-28239-0 Gewebe : EUR 20.00 (DE), EUR 20.60 (AT)" -- the German
# price, or an unmarked one; never the Austrian or Swiss one.
_PRICE = re.compile(r'EUR\s*(\d+[.,]\d{2})(?!\s*\((?:AT|CH)\))')


class UpstreamError(Exception):
    """A database did not answer usefully: timeout, 5xx, 429 or garbage."""


def lookup(code):
    """Everything the page shows for one normalized code."""
    kind = classify(code)
    result = {'code': code, 'kind': kind, 'gs1': gs1_label(code), 'found': False,
              'product': None, 'book': None, 'add_url': None}
    if kind == 'book':
        book = fetch_dnb(code)
        if book:
            result.update(found=True, book=book)
            return result
    hit = fetch_off(code)
    if hit:
        result.update(found=True, product=normalize_off(*hit))
    else:
        result['add_url'] = OFF_ADD_URL.format(code=code)
    return result


def _get(url, params):
    try:
        return requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise UpstreamError(str(exc)) from exc


# --- Open Food Facts and its sister databases ---------------------------------

def fetch_off(code):
    """(raw product, host that answered), or None when no database knows the code."""
    response = _get(OFF_URL.format(code=code), {'product_type': 'all', 'fields': OFF_FIELDS})
    # 404 is OFF's "not found" and still carries JSON; anything else that is
    # not a 200 means we learned nothing about the product.
    if response.status_code not in (200, 404):
        raise UpstreamError(f'Open Food Facts answered HTTP {response.status_code}')
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamError('Open Food Facts answered no JSON') from exc
    if not isinstance(payload, dict):
        raise UpstreamError('Open Food Facts answered an unexpected shape')
    product = payload.get('product') if payload.get('status') == 1 else None
    if not product:
        return None
    return product, urlsplit(response.url).hostname


def normalize_off(product, host):
    kind, source = _FLAVORS.get(host, _FLAVORS['world.openfoodfacts.org'])
    site = host if host in _FLAVORS else 'world.openfoodfacts.org'
    product_type = product.get('product_type')
    name = _first_text(product, 'product_name_de', 'product_name', 'generic_name_de', 'generic_name')
    generic = _text(product.get('generic_name_de'))
    return {
        'type': product_type if product_type in ('food', 'beauty', 'petfood', 'product') else kind,
        'name': name,
        'generic': generic if generic != name else None,
        'brand': _text(product.get('brands')),
        'quantity': _text(product.get('quantity')),
        'image': _image(product.get('image_front_small_url')),
        'scores': _scores(product),
        'nutrition': _nutrition(product.get('nutriments') or {}, product),
        'ingredients': _ingredients(product),
        'allergens': _tag_names(product.get('allergens_tags')),
        'traces': _tag_names(product.get('traces_tags')),
        'diet': _diet(product.get('ingredients_analysis_tags')),
        'deposit': _deposit(product.get('labels_tags')),
        'source': {'name': source, 'url': f"https://{site}/product/{product.get('code')}"},
    }


def _text(value):
    return (value.strip() or None) if isinstance(value, str) else None


def _first_text(product, *keys):
    for key in keys:
        text = _text(product.get(key))
        if text:
            return text
    return None


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.replace(',', '.'))
        except ValueError:
            return None
    return None


def _image(url):
    """Only an https image on an Open ... Facts image host reaches the page."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    return url if parts.scheme == 'https' and parts.hostname in _IMAGE_HOSTS else None


def _scores(product):
    scores = {}
    nutri = str(product.get('nutriscore_grade') or '').lower()
    if nutri in ('a', 'b', 'c', 'd', 'e'):
        scores['nutriscore'] = nutri
    try:
        nova = int(product.get('nova_group'))
    except (TypeError, ValueError):
        nova = None
    if nova in (1, 2, 3, 4):
        scores['nova'] = nova
    eco = str(product.get('ecoscore_grade') or '').lower()
    if eco in ('a-plus', 'a', 'b', 'c', 'd', 'e', 'f'):
        scores['ecoscore'] = eco
    return scores


def _amount(nutriments, key, per):
    value = _num(nutriments.get(f'{key}_{per}'))
    if value is None and key == 'energy-kcal':
        # Some entries carry only kJ; `energy_*` is kJ too.
        kj = _num(nutriments.get(f'energy-kj_{per}'))
        if kj is None:
            kj = _num(nutriments.get(f'energy_{per}'))
        value = None if kj is None else round(kj / 4.184)
    return value


def _nutrition(nutriments, product):
    rows = []
    for key, label, unit in _NUTRIENTS:
        per_100g = _amount(nutriments, key, '100g')
        per_serving = _amount(nutriments, key, 'serving')
        if per_100g is None and per_serving is None:
            continue
        rows.append({'key': key, 'label': label, 'unit': unit, 'sub': key in _SUB_ROWS,
                     'per_100g': per_100g, 'per_serving': per_serving})
    if not rows:
        return None
    has_serving = any(row['per_serving'] is not None for row in rows)
    return {
        # OFF keeps drinks "per 100 g" in its keys; the pack says 100 ml.
        'basis': '100 ml' if product.get('product_quantity_unit') == 'ml' else '100 g',
        'serving_size': _text(product.get('serving_size')) if has_serving else None,
        'rows': rows,
    }


def _ingredients(product):
    german = _text(product.get('ingredients_text_de'))
    if german:
        return {'text': german, 'lang': 'de'}
    other = _text(product.get('ingredients_text'))
    return {'text': other, 'lang': 'other'} if other else None


def _tag_names(tags):
    names = []
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        name = _ALLERGENS_DE.get(tag) or tag.split(':', 1)[-1].replace('-', ' ').strip().capitalize()
        if name and name not in names:
            names.append(name)
    return names


def _diet(tags):
    tags = {tag for tag in tags or [] if isinstance(tag, str)}

    def status(yes, no, maybe):
        if yes in tags:
            return 'yes'
        if no in tags:
            return 'no'
        return 'maybe' if maybe in tags else None

    diet = {
        'vegan': status('en:vegan', 'en:non-vegan', 'en:maybe-vegan'),
        'vegetarian': status('en:vegetarian', 'en:non-vegetarian', 'en:maybe-vegetarian'),
        'palm_oil_free': status('en:palm-oil-free', 'en:palm-oil', 'en:may-contain-palm-oil'),
    }
    return diet if any(diet.values()) else None


def _deposit(labels):
    """Pfand, when someone tagged the pack with it -- rarely done, so absence means nothing."""
    for label in labels or []:
        tag = str(label).lower()
        if 'mehrweg' in tag:
            return 'Mehrweg-Pfand'
        if 'pfand' in tag or 'deposit' in tag:
            return 'Einweg-Pfand' if 'einweg' in tag else 'Pfand'
    return None


# --- Deutsche Nationalbibliothek ----------------------------------------------

def fetch_dnb(isbn):
    """The book, or None when the DNB has no record of the ISBN."""
    response = _get(DNB_URL, {'version': '1.1', 'operation': 'searchRetrieve',
                              'query': f'isbn={isbn}', 'recordSchema': 'oai_dc',
                              'maximumRecords': '1'})
    if response.status_code != 200:
        raise UpstreamError(f'DNB answered HTTP {response.status_code}')
    return normalize_dnb(response.content, isbn)


def normalize_dnb(xml, isbn):
    """The book in the DNB's answer for `isbn`, or None when it has no record."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise UpstreamError('DNB answered no XML') from exc
    record = root.find(f'.//{_SRW}recordData')
    if record is None:
        return None

    def texts(tag):
        return [e.text.strip() for e in record.iter(_DC + tag) if e.text and e.text.strip()]

    titles = texts('title')
    if not titles:
        return None
    # "Der Vorleser : Roman / Bernhard Schlink" -- the part after " / " is
    # the statement of responsibility, which the author line already shows.
    title = re.sub(r'\s+:\s+', ': ', titles[0].split(' / ')[0]).strip()

    place, _, publisher = (texts('publisher') or [''])[0].partition(' : ')
    year = next((m.group(0) for d in texts('date') for m in [re.search(r'\d{4}', d)] if m), None)
    pages = next((int(m.group(1)) for f in texts('format') for m in [_PAGES.search(f)] if m), None)
    subject = next((re.sub(r'^[0-9A-Z]{1,3}\s+', '', s) for s in texts('subject')), None)

    idn, price = None, None
    for element in record.iter(_DC + 'identifier'):
        kind, text = element.get(_XSI_TYPE), (element.text or '').strip()
        if kind == 'dnb:IDN' and text and idn is None:
            idn = text
        elif kind == 'tel:ISBN' and price is None:
            match = _PRICE.search(text)
            if match:
                price = float(match.group(1).replace(',', '.'))

    return {
        'title': title,
        'authors': [_person(c) for c in texts('creator')],
        'publisher': f'{publisher}, {place}' if publisher else (place or None),
        'year': year,
        'pages': pages,
        'price_de': price,
        'subject': subject,
        'source': {'name': 'Deutsche Nationalbibliothek',
                   'url': f'https://d-nb.info/{idn}' if idn else None},
    }


def fetch_cover(isbn):
    """(image bytes, media type) of the cover, or None when there is none.

    Fetched here and served from /barcode/cover/ because the DNB answers a
    browser's image request with an HTML page (checked 2026-09-24), which
    Chrome then blocks as ORB; a plain server request gets the JPEG.
    """
    response = _get(DNB_COVER_URL, {'isbn': isbn})
    media_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
    if (response.status_code != 200 or media_type not in _COVER_TYPES
            or len(response.content) < _COVER_MIN_BYTES):
        return None
    return response.content, media_type


def _person(creator):
    """'Schlink, Bernhard [Verfasser]' -> 'Bernhard Schlink'."""
    name = re.sub(r'\s*\[[^\]]*\]', '', creator).strip()
    last, sep, first = name.partition(', ')
    return f'{first} {last}' if sep and first else name
