# personal_apps/features/radar/reference_universe.py
"""Official German reference universes (contract supplement §3.5/§3.6).

Builds the two ``ReferenceCatalog`` inputs the mapping generation needs:

- ``XETR`` straight from the DBAG "all tradable instruments" file;
- ``XGAT`` from the Tradegate BSX A–Z crawl, with mnemonic/type derived by
  ISIN from the DBAG Xetra+Frankfurt files (ruling R13) because Tradegate
  publishes no bulk mnemonics. Unresolvable or ambiguous ISINs are excluded
  so the mapping can only refuse them, never mis-map them.

Completeness is load-bearing: any transport failure, structural violation,
staleness, missing crawl page, or row-count floor miss yields
``complete=False`` — which ``decide_mapping`` turns into
``IncompleteReference`` so the generation build writes nothing (spec §5.4).
A failure must never look like an empty, successful universe.
"""
import dataclasses
import datetime as dt
import hashlib
import html as html_module
import logging
import re
import time

import requests

from .instruments import ReferenceCatalog, VenueReferenceRow

logger = logging.getLogger(__name__)

XETR_INSTRUMENTS_URL = (
    'https://www.cashmarket.deutsche-boerse.com/resource/blob/1528/'
    '025198b8d1f317b79e6724dd6b5f87b6/data/'
    't7-xetr-allTradableInstruments.csv')
XFRA_INSTRUMENTS_URL = (
    'https://www.cashmarket.deutsche-boerse.com/resource/blob/2289108/'
    '926cf6a36dbbd65465d592c48ef30d19/data/'
    't7-xfra-BF-allTradableInstruments.csv')
TRADEGATE_INDEX_URL = ('https://www.tradegatebsx.com/indizes.php'
                       '?lang=en&buchstabe={letter}')
TRADEGATE_LETTERS = ('0-9',) + tuple(
    chr(code) for code in range(ord('A'), ord('Z') + 1))

# Row-count floors: roughly half the captured baselines (§3.5/§3.6, R16).
XETR_MIN_ROWS = 2500
XFRA_MIN_ROWS = 25000
TRADEGATE_MIN_ISINS = 3000
MAX_FILE_AGE_DAYS = 7
_MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024

# The §3.5 grammar: consumed columns are addressed BY NAME, never index.
_CONSUMED_COLUMNS = ('Instrument', 'ISIN', 'Mnemonic', 'Instrument Type',
                     'Currency', 'MIC Code', 'Product Status',
                     'Instrument Status')
_TYPE_NORMALIZATION = {'CS': 'common stock', 'ETF': 'etf'}
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')
# The §3.6 anchor grammar, exactly as captured.
_TRADEGATE_BODY_RE = re.compile(
    r'<tbody id="kursliste_abc">(.*?)</tbody>', re.DOTALL)
_TRADEGATE_LINK_RE = re.compile(
    r'href="orderbuch\.php\?lang=en&amp;isin='
    r'([A-Z]{2}[A-Z0-9]{9}\d)"[^>]*>([^<]+)<')


class ReferenceFetchError(RuntimeError):
    """A reference download failed at the transport level."""


class ReferenceDataError(ValueError):
    """A reference payload violated the captured §3.5/§3.6 grammar."""


@dataclasses.dataclass(frozen=True)
class FileRow:
    """One consumed row of a DBAG instruments file (type already
    normalized)."""
    isin: str
    mnemonic: str
    name: str
    security_type: str
    currency: str


class ReferenceHttp:
    """Plain, throttled transport for the public reference sources."""

    def __init__(self, timeout=(3.05, 120), sleep=time.sleep):
        self._session = requests.Session()
        self._session.headers['User-Agent'] = 'radar-reference/1.0'
        self._timeout = timeout
        self._sleep = sleep
        self._page_fetches = 0

    def instruments_file(self, url):
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ReferenceFetchError(f'instruments file: {exc}') from exc
        if len(response.content) > _MAX_DOWNLOAD_BYTES:
            raise ReferenceFetchError('instruments file exceeds size cap')
        return response.content.decode('utf-8', errors='strict')

    def tradegate_page(self, letter):
        if self._page_fetches:
            self._sleep(1.0)  # stay polite: 27 pages per weekly refresh
        self._page_fetches += 1
        url = TRADEGATE_INDEX_URL.format(letter=letter)
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ReferenceFetchError(f'tradegate page {letter}: {exc}') \
                from exc
        return response.text


def _normalize_type(raw):
    """CS/ETF map into the OpenFIGI vocabulary; everything else gets a
    namespace prefix so a future DBAG type can never collide with a
    supported OpenFIGI value by accident."""
    normalized = _TYPE_NORMALIZATION.get(raw)
    if normalized is not None:
        return normalized
    return f'dbag:{(raw or "").strip().lower()}'


def parse_instruments_file(text, expected_market, now):
    """§3.5 grammar: two meta lines, a named-column header, ';' rows."""
    lines = text.split('\n')
    if len(lines) < 4:
        raise ReferenceDataError('missing header lines')
    market = lines[0].strip()
    if market != f'Market:;{expected_market}':
        raise ReferenceDataError(
            f'market line {market!r} is not {expected_market}')
    date_line = lines[1].strip()
    prefix = 'Date Last Update:;'
    if not date_line.startswith(prefix):
        raise ReferenceDataError('missing date line')
    try:
        updated = dt.datetime.strptime(
            date_line[len(prefix):], '%d.%m.%Y').date()
    except ValueError as exc:
        raise ReferenceDataError(f'unparseable date line: {exc}') from exc
    if (now.date() - updated).days > MAX_FILE_AGE_DAYS:
        raise ReferenceDataError(f'stale file: last update {updated}')

    header = lines[2].split(';')
    index = {column: position for position, column in enumerate(header)}
    missing = [column for column in _CONSUMED_COLUMNS if column not in index]
    if missing:
        raise ReferenceDataError(f'missing column(s): {missing}')

    rows = []
    for line in lines[3:]:
        if not line.strip():
            continue
        cells = line.split(';')
        if len(cells) < len(header):
            continue  # short/foreign trailer lines carry no identity
        isin = cells[index['ISIN']].strip()
        if not _ISIN_RE.match(isin):
            continue
        if cells[index['MIC Code']].strip() != expected_market:
            continue  # never let a foreign venue's row into this catalog
        if cells[index['Product Status']].strip() != 'Active' or \
                cells[index['Instrument Status']].strip() != 'Active':
            continue  # a dying trading line must not validate a mapping
        rows.append(FileRow(
            isin=isin,
            mnemonic=cells[index['Mnemonic']].strip(),
            name=cells[index['Instrument']].strip(),
            security_type=_normalize_type(
                cells[index['Instrument Type']].strip()),
            currency=cells[index['Currency']].strip()))
    return rows


def _drop_symbol_collisions(rows, mic):
    """Spec §5.2 step 5: a symbol held by two rows is an ambiguity and the
    mapping must refuse it, never pick one. ``_reference_by_symbol`` keys
    the catalog by symbol, so EVERY row of a colliding symbol is dropped."""
    counts = {}
    for row in rows:
        counts[row.symbol] = counts.get(row.symbol, 0) + 1
    kept = tuple(row for row in rows if counts[row.symbol] == 1)
    dropped = len(rows) - len(kept)
    if dropped:
        logger.warning('%s reference: %d rows dropped for symbol '
                       'collisions', mic, dropped)
    return kept


def parse_tradegate_index(page_html):
    """§3.6 grammar: (ISIN, display name) pairs from the price-list body."""
    body = _TRADEGATE_BODY_RE.search(page_html)
    if body is None:
        return []
    rows = []
    seen = set()
    for isin, name in _TRADEGATE_LINK_RE.findall(body.group(1)):
        if isin in seen:
            continue
        seen.add(isin)
        rows.append((isin, html_module.unescape(name).strip()))
    return rows


def _incomplete(mic):
    return ReferenceCatalog(mic=mic, rows=(), complete=False,
                            content_sha256='')


def build_xetr_catalog(text, now, min_rows=None):
    floor = XETR_MIN_ROWS if min_rows is None else min_rows
    try:
        rows = parse_instruments_file(text, 'XETR', now)
    except ReferenceDataError as exc:
        logger.error('XETR reference refused: %s', exc)
        return _incomplete('XETR')
    if len(rows) < floor:
        logger.error('XETR reference has %d rows, floor is %d',
                     len(rows), floor)
        return _incomplete('XETR')
    catalog_rows = _drop_symbol_collisions(tuple(
        VenueReferenceRow(mic='XETR', isin=row.isin, symbol=row.mnemonic,
                          name=row.name, currency=row.currency,
                          security_type=row.security_type)
        for row in rows if row.mnemonic), 'XETR')
    return ReferenceCatalog(
        mic='XETR', rows=catalog_rows, complete=True,
        content_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())


def build_xgat_catalog(universe_by_letter, enrichment_rows, min_isins=None):
    """R13: XGAT rows exist only for uniquely enriched Tradegate ISINs.

    ``universe_by_letter`` must cover every §3.6 letter page with at least
    one parsed row each — a missing or empty page means the crawl cannot
    prove the universe and the catalog is incomplete.
    """
    floor = TRADEGATE_MIN_ISINS if min_isins is None else min_isins
    for letter in TRADEGATE_LETTERS:
        if not universe_by_letter.get(letter):
            logger.error('tradegate page %r missing or empty', letter)
            return _incomplete('XGAT')

    enrichment = {}
    for row in enrichment_rows:
        enrichment.setdefault(row.isin, set()).add(
            (row.mnemonic, row.security_type))

    rows = []
    excluded = 0
    seen = set()
    for letter in TRADEGATE_LETTERS:
        for isin, name in universe_by_letter[letter]:
            if isin in seen:
                continue
            seen.add(isin)
            candidates = {pair for pair in enrichment.get(isin, set())
                          if pair[0]}
            if len(candidates) != 1:
                excluded += 1  # unknown or ambiguous: refusal, never a guess
                continue
            mnemonic, security_type = next(iter(candidates))
            rows.append(VenueReferenceRow(
                mic='XGAT', isin=isin, symbol=mnemonic, name=name,
                currency='EUR',  # R15: venue-wide statement
                security_type=security_type))
    rows = list(_drop_symbol_collisions(tuple(rows), 'XGAT'))
    if len(rows) < floor:
        logger.error('XGAT reference resolved %d rows (excluded %d), '
                     'floor is %d', len(rows), excluded, floor)
        return _incomplete('XGAT')
    canonical = '\n'.join(f'{row.isin}\t{row.symbol}\t{row.security_type}'
                          for row in sorted(rows, key=lambda r: r.isin))
    return ReferenceCatalog(
        mic='XGAT', rows=tuple(rows), complete=True,
        content_sha256=hashlib.sha256(
            canonical.encode('utf-8')).hexdigest())


def build_reference_catalogs(http, now):
    """Fetch and build both catalogs; failures degrade to incomplete."""
    try:
        xetr_text = http.instruments_file(XETR_INSTRUMENTS_URL)
        xfra_text = http.instruments_file(XFRA_INSTRUMENTS_URL)
    except ReferenceFetchError as exc:
        logger.error('reference file fetch failed: %s', exc)
        return {'XETR': _incomplete('XETR'), 'XGAT': _incomplete('XGAT')}

    xetr_catalog = build_xetr_catalog(xetr_text, now)

    try:
        xetr_rows = parse_instruments_file(xetr_text, 'XETR', now)
        xfra_rows = parse_instruments_file(xfra_text, 'XFRA', now)
    except ReferenceDataError as exc:
        logger.error('reference enrichment refused: %s', exc)
        return {'XETR': xetr_catalog, 'XGAT': _incomplete('XGAT')}
    if len(xfra_rows) < XFRA_MIN_ROWS:
        logger.error('XFRA reference has %d rows, floor is %d',
                     len(xfra_rows), XFRA_MIN_ROWS)
        return {'XETR': xetr_catalog, 'XGAT': _incomplete('XGAT')}

    universe = {}
    try:
        for letter in TRADEGATE_LETTERS:
            universe[letter] = parse_tradegate_index(
                http.tradegate_page(letter))
    except ReferenceFetchError as exc:
        logger.error('tradegate crawl failed: %s', exc)
        return {'XETR': xetr_catalog, 'XGAT': _incomplete('XGAT')}

    xgat_catalog = build_xgat_catalog(universe, xetr_rows + xfra_rows)
    return {'XETR': xetr_catalog, 'XGAT': xgat_catalog}
