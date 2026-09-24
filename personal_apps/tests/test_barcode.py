"""Barcode scanner: code rules, upstream normalizers, routes and access.

DB-free: logins are faked by monkeypatching `auth.current_user`, as
test_showoff.py does, and upstream HTTP is replaced by recorded fixtures.
"""
import json
from pathlib import Path

import pytest
import requests

from features.barcode import codes, sources

FIXTURES = Path(__file__).parent / 'fixtures' / 'barcode'
OFF = 'https://world.openfoodfacts.org/'
DNB = 'https://services.dnb.de/'


def _with_check(body):
    """`body` plus the GS1 check digit that makes it a valid code."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


# --- codes ------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('4001686301265', '4001686301265'),      # EAN-13, Haribo Goldbären
    (' 4001686 301265 ', '4001686301265'),   # spaces from a hand-typed code
    ('978-3-423-28239-0', '9783423282390'),  # ISBN as printed on the back
    ('40111445', '40111445'),                # EAN-8
    ('036000291452', '0036000291452'),       # a UPC-A is the EAN-13 with a leading 0
])
def test_normalize_accepts_valid_codes(raw, expected):
    assert codes.normalize(raw) == expected


@pytest.mark.parametrize('raw', [
    '4001686301266',              # wrong check digit
    '40016863012',                # 11 digits
    '4001686301265x',             # letters
    '',
    None,
    '４００１６８６３０１２６５',  # full-width digits pass str.isdigit()
    '3423282395',                 # an ISBN-10 is not a barcode
])
def test_normalize_rejects(raw):
    with pytest.raises(codes.InvalidCode):
        codes.normalize(raw)


@pytest.mark.parametrize('code, kind', [
    ('9783423282390', 'book'),
    (_with_check('979100000000'), 'book'),
    ('4001686301265', 'product'),
    ('40111445', 'product'),
    (_with_check('200123400000'), 'instore'),  # weighed goods, own labels
    (_with_check('020123400000'), 'instore'),  # UPC number system 2
    (_with_check('040123400000'), 'instore'),
    (_with_check('2004723'), 'instore'),       # EAN-8 restricted circulation (Lidl, Aldi)
    (_with_check('0012345'), 'instore'),
])
def test_classify(code, kind):
    assert codes.classify(code) == kind


@pytest.mark.parametrize('code, label', [
    ('4001686301265', 'Deutschland'),
    (_with_check('400000000000'), 'Deutschland'),
    (_with_check('440000000000'), 'Deutschland'),
    (_with_check('441000000000'), None),
    ('40111445', 'Deutschland'),
    ('0036000291452', 'USA & Kanada'),
    (_with_check('900000000000'), 'Österreich'),
    (_with_check('977000000000'), 'ISSN (Zeitschrift)'),
    ('9783423282390', 'ISBN (Buch)'),
    (_with_check('140000000000'), None),
    (_with_check('200000000000'), 'Handelsinterne Nummer'),
    (_with_check('2004723'), 'Handelsinterne Nummer'),
])
def test_gs1_label(code, label):
    assert codes.gs1_label(code) == label


# --- sources: normalizers on recorded answers (recorded 2026-09-24) ----------

def _recorded(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _haribo():
    return _recorded('off_haribo.json')['product']


def test_normalize_off_food():
    product = sources.normalize_off(_haribo(), 'world.openfoodfacts.org')
    assert product['type'] == 'food'
    assert product['name'] == 'Goldbären'
    assert product['generic'] == 'Fruchtgummis'
    assert product['brand'] == 'Haribo'
    assert product['quantity'] == '200g'
    assert product['image'].startswith('https://images.openfoodfacts.org/')
    assert product['scores'] == {'nutriscore': 'd', 'nova': 4, 'ecoscore': 'a'}
    assert product['source'] == {
        'name': 'Open Food Facts',
        'url': 'https://world.openfoodfacts.org/product/4001686301265',
    }
    assert product['allergens'] == ['Kiwi']
    assert product['traces'] == []
    assert product['diet'] == {'vegan': 'no', 'vegetarian': None, 'palm_oil_free': 'yes'}
    assert product['ingredients']['lang'] == 'de'
    assert product['ingredients']['text'].startswith('Glukosesirup, Zucker, Gelatine')
    assert product['deposit'] is None


def test_nutrition_rows_per_100g_and_per_serving():
    nutrition = sources.normalize_off(_haribo(), 'world.openfoodfacts.org')['nutrition']
    assert nutrition['basis'] == '100 g'
    assert nutrition['serving_size'] == '25g'
    rows = {row['key']: row for row in nutrition['rows']}
    # Table order; fibre is absent from this product, so it has no row.
    assert list(rows) == ['energy-kcal', 'fat', 'saturated-fat', 'carbohydrates',
                          'sugars', 'proteins', 'salt']
    assert (rows['energy-kcal']['per_100g'], rows['energy-kcal']['per_serving']) == (343, 85.8)
    assert (rows['proteins']['per_100g'], rows['proteins']['per_serving']) == (6.9, 1.73)
    assert rows['sugars']['sub'] is True
    assert rows['carbohydrates']['sub'] is False


def test_drink_is_per_100_ml_and_zero_is_a_value():
    product = sources.normalize_off(_recorded('off_clubmate.json')['product'], 'world.openfoodfacts.org')
    nutrition = product['nutrition']
    assert nutrition['basis'] == '100 ml'
    assert nutrition['serving_size'] is None
    rows = {row['key']: row for row in nutrition['rows']}
    assert rows['fat']['per_100g'] == 0          # 0 g is data, not "unknown"
    assert rows['fiber']['per_100g'] == 0
    assert all(row['per_serving'] is None for row in nutrition['rows'])
    assert product['scores'] == {'nutriscore': 'c', 'nova': 4}  # Eco-Score not-applicable
    assert product['diet'] == {'vegan': 'yes', 'vegetarian': 'yes', 'palm_oil_free': 'yes'}


def test_kcal_falls_back_to_kilojoules():
    raw = _recorded('off_clubmate.json')['product']
    del raw['nutriments']['energy-kcal_100g']
    rows = sources.normalize_off(raw, 'world.openfoodfacts.org')['nutrition']['rows']
    assert rows[0]['key'] == 'energy-kcal' and rows[0]['per_100g'] == 20  # 84 kJ


def test_allergens_and_traces_in_german():
    raw = _haribo()
    raw['allergens_tags'] = ['en:nuts', 'en:soybeans', 'en:kiwi', 'en:nuts']
    raw['traces_tags'] = ['en:milk', 'de:haselnüsse']
    product = sources.normalize_off(raw, 'world.openfoodfacts.org')
    assert product['allergens'] == ['Schalenfrüchte', 'Soja', 'Kiwi']
    assert product['traces'] == ['Milch', 'Haselnüsse']


@pytest.mark.parametrize('labels, deposit', [
    (['de:einwegpfand'], 'Einweg-Pfand'),
    (['en:no-gluten', 'de:mehrweg'], 'Mehrweg-Pfand'),
    (['de:pfandflasche'], 'Pfand'),
    (['en:no-gluten'], None),
])
def test_deposit_from_labels(labels, deposit):
    raw = _haribo()
    raw['labels_tags'] = labels
    assert sources.normalize_off(raw, 'world.openfoodfacts.org')['deposit'] == deposit


def test_ingredients_fall_back_to_another_language():
    raw = _haribo()
    del raw['ingredients_text_de']
    raw['ingredients_text'] = 'Sciroppo di glucosio, zucchero'
    assert sources.normalize_off(raw, 'world.openfoodfacts.org')['ingredients'] == {
        'text': 'Sciroppo di glucosio, zucchero', 'lang': 'other'}
    raw['ingredients_text'] = ''
    assert sources.normalize_off(raw, 'world.openfoodfacts.org')['ingredients'] is None


def test_name_falls_back_past_empty_german_name():
    raw = _haribo()
    raw['product_name_de'] = ''
    raw['product_name'] = 'Orsetti d’oro'
    assert sources.normalize_off(raw, 'world.openfoodfacts.org')['name'] == 'Orsetti d’oro'


@pytest.mark.parametrize('url', [
    'http://images.openfoodfacts.org/images/x.jpg',
    'https://images.evil.example/x.jpg',
    'javascript:alert(1)',
    None,
])
def test_image_only_from_open_food_facts_hosts_over_https(url):
    raw = _haribo()
    raw['image_front_small_url'] = url
    assert sources.normalize_off(raw, 'world.openfoodfacts.org')['image'] is None


def test_normalize_off_beauty():
    product = sources.normalize_off(_recorded('obf_nivea.json')['product'], 'world.openbeautyfacts.org')
    assert product['type'] == 'beauty'
    assert product['name'] == 'Nivea soft'
    assert product['source'] == {
        'name': 'Open Beauty Facts',
        'url': 'https://world.openbeautyfacts.org/product/4005808890507',
    }
    assert product['image'].startswith('https://images.openbeautyfacts.org/')
    assert product['nutrition'] is None
    assert product['scores'] == {}
    assert product['diet'] is None


def test_normalize_dnb():
    book = sources.normalize_dnb((FIXTURES / 'dnb_schulze.xml').read_bytes(), '9783423282390')
    assert book == {
        'title': 'Tasso im Irrenhaus: drei Erzählungen',
        'authors': ['Ingo Schulze'],
        'publisher': 'dtv, München',
        'year': '2021',
        'pages': 158,
        'price_de': 20.0,
        'subject': 'Deutsche Literatur',
        'image': 'https://portal.dnb.de/opac/mvb/cover?isbn=9783423282390',
        'source': {'name': 'Deutsche Nationalbibliothek', 'url': 'https://d-nb.info/1220520136'},
    }


def test_normalize_dnb_without_a_record():
    assert sources.normalize_dnb((FIXTURES / 'dnb_empty.xml').read_bytes(), '9780000000002') is None


# --- sources: lookup routing and upstream failures -----------------------------

class _Response:
    """What `requests.get` hands back, minus the network."""

    def __init__(self, status_code=200, payload=None, content=b'', url=''):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.url = url

    def json(self):
        if self._payload is None:
            raise ValueError('no JSON')
        return self._payload


def _fake_get(monkeypatch, routes):
    """Replace requests.get; the first URL prefix in `routes` that matches answers."""
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        assert headers['User-Agent'].startswith('PersonalApps-Barcode/')
        assert timeout
        for prefix, answer in routes.items():
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f'unexpected upstream call: {url}')

    monkeypatch.setattr(sources.requests, 'get', get)
    return calls


def test_lookup_food(monkeypatch):
    _fake_get(monkeypatch, {OFF: _Response(200, _recorded('off_haribo.json'),
                                           url=OFF + 'api/v2/product/4001686301265.json')})
    result = sources.lookup('4001686301265')
    assert (result['found'], result['kind'], result['gs1']) == (True, 'product', 'Deutschland')
    assert result['product']['name'] == 'Goldbären'
    assert result['book'] is None and result['add_url'] is None


def test_lookup_non_food_reads_the_database_it_was_redirected_to(monkeypatch):
    # requests follows OFF's 302; the final URL says which database answered.
    _fake_get(monkeypatch, {OFF: _Response(200, _recorded('obf_nivea.json'),
                                           url='https://world.openbeautyfacts.org/api/v2/product/4005808890507.json')})
    product = sources.lookup('4005808890507')['product']
    assert (product['type'], product['source']['name']) == ('beauty', 'Open Beauty Facts')


def test_lookup_not_found_offers_to_add_it(monkeypatch):
    _fake_get(monkeypatch, {OFF: _Response(404, _recorded('off_missing.json'))})
    result = sources.lookup('4099999999996')
    assert result['found'] is False and result['product'] is None
    assert result['add_url'] == ('https://world.openfoodfacts.org/cgi/product.pl'
                                 '?type=search_or_add&action=process&code=4099999999996')


def test_lookup_book_asks_only_the_dnb(monkeypatch):
    calls = _fake_get(monkeypatch, {DNB: _Response(200, content=(FIXTURES / 'dnb_schulze.xml').read_bytes())})
    result = sources.lookup('9783423282390')
    assert (result['found'], result['kind']) == (True, 'book')
    assert result['book']['authors'] == ['Ingo Schulze']
    assert calls == [DNB + 'sru/dnb']


def test_lookup_book_unknown_to_the_dnb_tries_open_food_facts(monkeypatch):
    calls = _fake_get(monkeypatch, {
        DNB: _Response(200, content=(FIXTURES / 'dnb_empty.xml').read_bytes()),
        OFF: _Response(404, _recorded('off_missing.json')),
    })
    result = sources.lookup('9780000000002')
    assert result['found'] is False
    assert [c.split('/')[2] for c in calls] == ['services.dnb.de', 'world.openfoodfacts.org']


@pytest.mark.parametrize('failure', [
    requests.Timeout('slow'),
    requests.ConnectionError('down'),
    _Response(503),
    _Response(429),
    _Response(200),          # a 200 whose body is not JSON (maintenance page)
])
def test_off_failures_raise(monkeypatch, failure):
    _fake_get(monkeypatch, {OFF: failure})
    with pytest.raises(sources.UpstreamError):
        sources.lookup('4001686301265')


@pytest.mark.parametrize('failure', [
    requests.Timeout('slow'),
    _Response(500),
    _Response(200, content=b'<html>Wartungsarbeiten'),
])
def test_dnb_failures_raise_instead_of_claiming_not_found(monkeypatch, failure):
    _fake_get(monkeypatch, {DNB: failure})
    with pytest.raises(sources.UpstreamError):
        sources.lookup('9783423282390')
