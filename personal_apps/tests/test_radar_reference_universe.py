# personal_apps/tests/test_radar_reference_universe.py
"""The R6 reference universes (contract supplement §3.5/§3.6, R12–R16).

Everything here runs against the sanitized fixtures with the real DBAG
153-column header; no network. Completeness is the load-bearing bit: a
broken fetch must yield ``complete=False`` (=> IncompleteReference in the
mapping), never an empty-but-complete catalog.
"""
import datetime as dt
import pathlib

import pytest

from features.radar import reference_universe as ru
from features.radar.instruments import VenueReferenceRow

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'radar_market_data'
NOW = dt.datetime(2026, 9, 2, 12, 0)

XETR_TEXT = (FIXTURES / 'reference_xetr.csv').read_text(encoding='utf-8')
XFRA_TEXT = (FIXTURES / 'reference_xfra.csv').read_text(encoding='utf-8')
INDEX_HTML = (FIXTURES / 'reference_tradegate_index.html').read_text(
    encoding='utf-8')


# ---------------------------------------------------------------- DBAG files

def test_parse_instruments_file_reads_the_consumed_columns_by_name():
    rows = ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW)
    assert [r.isin for r in rows] == [
        'DE000ZZTST01', 'IE000ZZTST02', 'DE000ZZTST03', 'DE000ZZTST04']
    first = rows[0]
    assert first.mnemonic == 'ZZ1'
    assert first.name == 'ZZ TEST AG'
    assert first.security_type == 'common stock'
    assert first.currency == 'EUR'


def test_parse_normalizes_only_cs_and_etf_types():
    """Unknown DBAG types get a namespace prefix: a future DBAG value can
    never collide with a supported OpenFIGI type by accident."""
    from features.radar.prices.openfigi import is_supported_type
    rows = ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW)
    assert [r.security_type for r in rows] == [
        'common stock', 'etf', 'dbag:etn', 'dbag:sr']
    assert not is_supported_type(ru._normalize_type('ETP'))


def test_parse_excludes_inactive_and_foreign_mic_rows():
    rows = ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW)
    isins = {r.isin for r in rows}
    assert 'DE000ZZTST05' not in isins  # Instrument Status: Inactive
    assert 'DE000ZZTST06' not in isins  # MIC Code: XFRA inside XETR file


@pytest.mark.parametrize('mutate, match', [
    (lambda t: t.replace('Market:;XETR', 'Market:;XFRA'), 'market'),
    (lambda t: t.replace('Date Last Update:;01.09.2026',
                         'Date Last Update:;garbage'), 'date'),
    (lambda t: t.replace(';Mnemonic;', ';Renamed;'), 'column'),
    (lambda t: t.replace(';Instrument Status;', ';Renamed;'), 'column'),
    (lambda t: '\n'.join(t.split('\n')[:2]), 'header'),
])
def test_structural_violations_raise(mutate, match):
    with pytest.raises(ru.ReferenceDataError, match=match):
        ru.parse_instruments_file(mutate(XETR_TEXT), 'XETR', NOW)


def test_a_stale_file_raises():
    stale_now = dt.datetime(2026, 9, 30, 12, 0)
    with pytest.raises(ru.ReferenceDataError, match='stale'):
        ru.parse_instruments_file(XETR_TEXT, 'XETR', stale_now)


def test_file_age_boundary_is_seven_days():
    ru.parse_instruments_file(
        XETR_TEXT, 'XETR', dt.datetime(2026, 9, 8, 23, 59))


# ------------------------------------------------------------ XETR catalog

def test_xetr_catalog_rows_key_by_mnemonic_and_skip_empty_mnemonics():
    catalog = ru.build_xetr_catalog(XETR_TEXT, NOW, min_rows=2)
    assert catalog.mic == 'XETR'
    assert catalog.complete is True
    by_symbol = {row.symbol: row for row in catalog.rows}
    assert set(by_symbol) == {'ZZ1', 'ZZE2', 'ZZN3'}  # SR row: no mnemonic
    assert isinstance(catalog.rows[0], VenueReferenceRow)
    assert by_symbol['ZZ1'].isin == 'DE000ZZTST01'
    assert by_symbol['ZZE2'].currency == 'USD'
    assert len(catalog.content_sha256) == 64


def test_xetr_catalog_below_the_row_floor_is_incomplete():
    catalog = ru.build_xetr_catalog(XETR_TEXT, NOW, min_rows=5)
    assert catalog.complete is False
    assert catalog.rows == ()


def test_xetr_catalog_default_floor_is_the_captured_baseline_half():
    # Teeth for the pinned constant: the 4-row fixture must NOT satisfy
    # the production floor.
    assert ru.XETR_MIN_ROWS == 2500
    assert ru.build_xetr_catalog(XETR_TEXT, NOW).complete is False


def test_xetr_floor_applies_after_collision_and_mnemonic_exclusions():
    """A mass-corrupted mnemonic column must refuse even when the raw row
    count clears the floor: the floor guards the usable catalog."""
    duplicated = XETR_TEXT.replace(';ZZE2;', ';ZZ1;')  # 4 parsed, 1 usable
    assert ru.build_xetr_catalog(duplicated, NOW, min_rows=2).complete \
        is False


# -------------------------------------------------------- Tradegate crawl

def test_tradegate_index_parse_follows_the_captured_link_grammar():
    rows = ru.parse_tradegate_index(INDEX_HTML)
    assert rows == [
        ('DE000ZZTST01', 'ZZ Test AG'),
        ('US000ZZTST08', 'ZZ US Corp & Co.'),
        ('BM000ZZTST10', 'ZZ Offshore Ltd.'),
    ]


def test_tradegate_index_without_the_listing_body_yields_nothing():
    assert ru.parse_tradegate_index('<html><body>maintenance</body></html>') \
        == []


def test_xgat_catalog_joins_symbols_by_isin_and_excludes_unresolvable():
    """R13: resolved rows carry the German mnemonic; missing/ambiguous
    ISINs are excluded so the mapping can only refuse them."""
    enrichment = (ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW) +
                  ru.parse_instruments_file(XFRA_TEXT, 'XFRA', NOW))
    # Every letter page needs a row; duplicates dedupe across pages.
    universe = {letter: [('DE000ZZTST01', 'ZZ Test AG')]
                for letter in ru.TRADEGATE_LETTERS}
    universe['Z'] = ru.parse_tradegate_index(INDEX_HTML)
    catalog = ru.build_xgat_catalog(universe, enrichment, min_isins=2)
    by_isin = {row.isin: row for row in catalog.rows}
    # DE000ZZTST01 appears in XETR and XFRA with the SAME (mnemonic, type):
    # resolved. US000ZZTST08 only in XFRA: resolved. BM000ZZTST10 nowhere:
    # excluded.
    assert set(by_isin) == {'DE000ZZTST01', 'US000ZZTST08'}
    row = by_isin['US000ZZTST08']
    assert row.mic == 'XGAT'
    assert row.symbol == 'ZZ8'
    assert row.security_type == 'common stock'
    assert row.currency == 'EUR'          # R15: venue statement, not a file
    assert row.name == 'ZZ US Corp & Co.'  # Tradegate's own display name
    assert catalog.complete is True


def test_xgat_catalog_excludes_isins_with_conflicting_enrichment():
    conflicting = ru.parse_instruments_file(XFRA_TEXT, 'XFRA', NOW) + [
        ru.FileRow(isin='US000ZZTST08', mnemonic='OTHER', name='ZZ US CORP',
                   security_type='common stock', currency='EUR')]
    universe = {letter: [] for letter in ru.TRADEGATE_LETTERS}
    universe['U'] = [('US000ZZTST08', 'ZZ US Corp & Co.')]
    catalog = ru.build_xgat_catalog(universe, conflicting, min_isins=1)
    assert catalog.rows == ()
    assert catalog.complete is False  # floor no longer met after exclusion


def test_xgat_catalog_requires_every_letter_page():
    universe = {letter: [('DE000ZZTST01', 'ZZ Test AG')]
                for letter in ru.TRADEGATE_LETTERS}
    del universe['Q']
    enrichment = ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW)
    catalog = ru.build_xgat_catalog(universe, enrichment, min_isins=1)
    assert catalog.complete is False


def test_xgat_catalog_requires_rows_on_every_page():
    universe = {letter: [('DE000ZZTST01', 'ZZ Test AG')]
                for letter in ru.TRADEGATE_LETTERS}
    universe['Q'] = []
    enrichment = ru.parse_instruments_file(XETR_TEXT, 'XETR', NOW)
    catalog = ru.build_xgat_catalog(universe, enrichment, min_isins=1)
    assert catalog.complete is False


def test_xgat_default_floor_is_pinned():
    assert ru.TRADEGATE_MIN_ISINS == 3000
    assert ru.XFRA_MIN_ROWS == 25000


# --------------------------------------------------- symbol collisions

def test_xetr_catalog_drops_every_row_of_a_colliding_mnemonic():
    """Spec §5.2 step 5: _reference_by_symbol keys the catalog by symbol,
    so a duplicated symbol would silently last-win into a wrong ISIN.
    Both rows must go."""
    duplicated = XETR_TEXT.replace(
        ';ZZE2;', ';ZZ1;')  # the ETF row now claims the CS row's mnemonic
    catalog = ru.build_xetr_catalog(duplicated, NOW, min_rows=1)
    assert catalog.complete is True
    assert {row.symbol for row in catalog.rows} == {'ZZN3'}


def test_xgat_catalog_drops_cross_isin_symbol_collisions():
    """Two different Tradegate ISINs enriched to the SAME mnemonic (one
    via XETR, one via XFRA) must both be excluded, never last-win."""
    enrichment = [
        ru.FileRow(isin='DE000ZZTST01', mnemonic='ZZ1', name='ZZ TEST AG',
                   security_type='common stock', currency='EUR'),
        ru.FileRow(isin='US000ZZTST08', mnemonic='ZZ1', name='ZZ US CORP',
                   security_type='common stock', currency='EUR'),
        ru.FileRow(isin='BM000ZZTST10', mnemonic='ZZX9', name='ZZ OFFSHORE',
                   security_type='common stock', currency='EUR'),
    ]
    universe = {letter: [('DE000ZZTST01', 'ZZ Test AG')]
                for letter in ru.TRADEGATE_LETTERS}
    universe['U'] = [('US000ZZTST08', 'ZZ US Corp & Co.')]
    universe['B'] = [('BM000ZZTST10', 'ZZ Offshore Ltd.'),
                     ('DE000ZZTST01', 'ZZ Test AG')]
    catalog = ru.build_xgat_catalog(universe, enrichment, min_isins=1)
    assert {row.isin for row in catalog.rows} == {'BM000ZZTST10'}


# ------------------------------------------------------- transport layer

def test_reference_http_wraps_transport_failures(monkeypatch):
    import requests as requests_module

    http = ru.ReferenceHttp(sleep=lambda seconds: None)

    class BoomSession:
        headers = {}

        def get(self, url, timeout=None):
            raise requests_module.ConnectionError('refused')

    http._session = BoomSession()
    with pytest.raises(ru.ReferenceFetchError):
        http.instruments_file(ru.XETR_INSTRUMENTS_URL)
    with pytest.raises(ru.ReferenceFetchError):
        http.tradegate_page('A')


def test_reference_http_rejects_oversized_files(monkeypatch):
    http = ru.ReferenceHttp(sleep=lambda seconds: None)

    class HugeResponse:
        content = b'x' * (ru._MAX_DOWNLOAD_BYTES + 1)

        def raise_for_status(self):
            return None

    class HugeSession:
        headers = {}

        def get(self, url, timeout=None):
            return HugeResponse()

    http._session = HugeSession()
    with pytest.raises(ru.ReferenceFetchError, match='size cap'):
        http.instruments_file(ru.XETR_INSTRUMENTS_URL)


# ------------------------------------------------- end-to-end catalog build

class FakeHttp:
    def __init__(self, xetr=XETR_TEXT, xfra=XFRA_TEXT, pages=None,
                 boom=None):
        self._xetr, self._xfra = xetr, xfra
        self._pages = pages if pages is not None else {
            letter: INDEX_HTML for letter in ru.TRADEGATE_LETTERS}
        self._boom = boom
        self.fetched_letters = []

    def instruments_file(self, url):
        if self._boom == 'file':
            raise ru.ReferenceFetchError('boom')
        return self._xetr if 'xetr' in url else self._xfra

    def tradegate_page(self, letter):
        if self._boom == 'page':
            raise ru.ReferenceFetchError('boom')
        self.fetched_letters.append(letter)
        return self._pages[letter]


def _lowered_floors(monkeypatch):
    monkeypatch.setattr(ru, 'XETR_MIN_ROWS', 2)
    monkeypatch.setattr(ru, 'XFRA_MIN_ROWS', 2)
    monkeypatch.setattr(ru, 'TRADEGATE_MIN_ISINS', 2)


def test_build_reference_catalogs_returns_both_complete(monkeypatch):
    _lowered_floors(monkeypatch)
    catalogs = ru.build_reference_catalogs(FakeHttp(), NOW)
    assert set(catalogs) == {'XETR', 'XGAT'}
    assert catalogs['XETR'].complete and catalogs['XGAT'].complete
    assert {row.symbol for row in catalogs['XGAT'].rows} == {'ZZ1', 'ZZ8'}


def test_build_reference_catalogs_hashes_are_deterministic(monkeypatch):
    _lowered_floors(monkeypatch)
    first = ru.build_reference_catalogs(FakeHttp(), NOW)
    second = ru.build_reference_catalogs(FakeHttp(), NOW)
    for mic in ('XETR', 'XGAT'):
        assert first[mic].content_sha256 == second[mic].content_sha256


def test_a_transport_failure_never_looks_like_an_empty_success(monkeypatch):
    _lowered_floors(monkeypatch)
    for boom in ('file', 'page'):
        catalogs = ru.build_reference_catalogs(FakeHttp(boom=boom), NOW)
        assert catalogs['XETR'].complete is False or \
            catalogs['XGAT'].complete is False
        if boom == 'file':
            # Both venues depend on the DBAG files (XGAT via enrichment).
            assert catalogs['XETR'].complete is False
            assert catalogs['XGAT'].complete is False


def test_a_structurally_broken_file_yields_incomplete_catalogs(monkeypatch):
    _lowered_floors(monkeypatch)
    http = FakeHttp(xetr=XETR_TEXT.replace('Market:;XETR', 'Market:;XFRA'))
    catalogs = ru.build_reference_catalogs(http, NOW)
    assert catalogs['XETR'].complete is False
    assert catalogs['XGAT'].complete is False


def test_incomplete_catalogs_make_decide_mapping_raise(monkeypatch):
    from features.radar import instruments
    _lowered_floors(monkeypatch)
    catalogs = ru.build_reference_catalogs(FakeHttp(boom='file'), NOW)
    instrument = type('I', (), {'ticker': 'ZZRU1', 'mic': 'XNAS'})()
    with pytest.raises(instruments.IncompleteReference):
        instruments.decide_mapping(instrument, object(), catalogs, {})
