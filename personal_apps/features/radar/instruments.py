"""Verified provider-catalog mappings for Radar's German instruments.

The social ticker is not a security identifier.  This module deliberately
joins listings only through ISIN and treats absent or ambiguous identifiers as
unavailable; it never falls back to symbols or company names.
"""
import dataclasses
import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from extensions import db
from models import RadarInstrument, TickerUniverse

from .prices import PriceUnavailable


XETRA_MIC = 'XETR'
XETRA_VENUE = 'Xetra'


@dataclasses.dataclass(frozen=True)
class CatalogInstrument:
    """The stable identity fields reference-data adapters are allowed to expose."""
    symbol: str
    name: str | None
    mic: str | None
    currency: str | None
    isin: str | None
    figi: str | None


@dataclasses.dataclass(frozen=True)
class MappingResult:
    """Counts safe to show in an operator probe; no provider payload is retained."""
    catalog_reachable: bool
    xetra_rows: int
    isin_rows: int
    mapped_active_tickers: int
    unavailable_active_tickers: int


class CatalogFallbackProvider:
    """Use Finnhub reference rows only to complete a permitted catalog record.

    Listings are merged on the provider-supplied `(symbol, MIC, currency)`
    identity, never on their company name.  If a catalog lacks stable IDs and
    its fallback cannot be read, the caller receives a failure and preserves
    old mappings instead of mistaking limited entitlement for no listing.
    """
    mapping_source = 'twelvedata+finnhub'

    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback

    @staticmethod
    def _key(row: CatalogInstrument):
        return row.symbol, row.mic, row.currency

    def stock_catalog(self, mic_code: str) -> list[CatalogInstrument]:
        try:
            primary_rows = self._primary.stock_catalog(mic_code)
        except PriceUnavailable:
            # A fully successful Finnhub directory is an independent provider
            # response. It is sufficient evidence; do not combine it with a
            # failed Twelve Data request.
            return self._fallback.stock_catalog(mic_code)

        # Avoid an unnecessary directory call when the primary catalog already
        # has every stable join key needed for a verified result.
        if primary_rows and all(_is_stable_isin(row.isin) for row in primary_rows):
            return primary_rows

        fallback_rows = self._fallback.stock_catalog(mic_code)
        fallback_by_key = {self._key(row): row for row in fallback_rows}
        merged = []
        seen = set()
        for row in primary_rows:
            supplemental = fallback_by_key.get(self._key(row))
            isin = row.isin
            figi = row.figi
            if supplemental is not None:
                if isin and supplemental.isin and isin != supplemental.isin:
                    isin = None
                else:
                    isin = isin or supplemental.isin
                if figi and supplemental.figi and figi != supplemental.figi:
                    figi = None
                else:
                    figi = figi or supplemental.figi
            merged.append(CatalogInstrument(
                symbol=row.symbol, name=row.name or
                (supplemental.name if supplemental else None), mic=row.mic,
                currency=row.currency, isin=isin, figi=figi))
            seen.add(self._key(row))
        # A fallback-only row remains a provider directory row with its actual
        # MIC and stable ID. It can map only if it independently satisfies the
        # Xetra/ISIN checks below.
        merged.extend(row for row in fallback_rows if self._key(row) not in seen)
        return merged


def _is_stable_isin(value: str | None) -> bool:
    # An ISIN is exactly twelve alphanumeric characters.  Keeping the check
    # here makes a provider's blank/error placeholder unable to create a map.
    return bool(value and len(value) == 12 and value.isalnum())


def map_xetra(us_rows: Iterable[CatalogInstrument],
              de_rows: Iterable[CatalogInstrument]) -> dict[str, CatalogInstrument]:
    """Return unambiguous EUR/Xetra matches, keyed by existing US ticker.

    FIGI remains in the normalized record for operational inspection, but it
    is not a cross-venue join key: provider FIGIs can identify a listing rather
    than an issuer.  ISIN is the verified identity agreed for this mapping.
    """
    xetra_by_isin: dict[str, list[CatalogInstrument]] = defaultdict(list)
    for row in de_rows:
        if (row.mic == XETRA_MIC and row.currency == 'EUR' and
                _is_stable_isin(row.isin)):
            xetra_by_isin[row.isin.upper()].append(row)

    isins_by_ticker: dict[str, set[str]] = defaultdict(set)
    for row in us_rows:
        if row.symbol and _is_stable_isin(row.isin):
            isins_by_ticker[row.symbol].add(row.isin.upper())

    mappings = {}
    for ticker, isins in isins_by_ticker.items():
        # A ticker with conflicting catalog identities is just as ambiguous as
        # duplicate Xetra candidates.  Do not choose the first response row.
        if len(isins) != 1:
            continue
        candidates = xetra_by_isin[next(iter(isins))]
        if len(candidates) == 1:
            mappings[ticker] = candidates[0]
    return mappings


def _active_us_instruments() -> list[RadarInstrument]:
    """Mapped US primary rows for companies still in Radar's active universe."""
    return (RadarInstrument.query.join(
        TickerUniverse, TickerUniverse.symbol == RadarInstrument.ticker)
        .filter(RadarInstrument.market == 'us',
                RadarInstrument.is_primary.is_(True),
                TickerUniverse.delisted_at.is_(None))
        .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())


def _load_catalogs(provider, us_instruments: Iterable[RadarInstrument]):
    """Fetch every required catalog before changing persistence.

    A failed call must not look like an empty, successful reference response:
    callers use that distinction to preserve previously verified mappings.
    """
    us_mics = sorted({row.mic for row in us_instruments if row.mic and
                      row.mic != 'XXXX'})
    try:
        us_catalog = []
        for mic in us_mics:
            us_catalog.extend(provider.stock_catalog(mic))
        xetra_catalog = provider.stock_catalog(XETRA_MIC)
    except Exception:
        # Provider adapters normalize transport and malformed-provider failures
        # as PriceUnavailable.  This boundary is deliberately broader: an
        # unexpected catalog implementation is also not proof a listing ended.
        return None, None
    return us_catalog, xetra_catalog


def _upsert_de_row(ticker: str, candidate: CatalogInstrument | None,
                   now: dt.datetime, source: str) -> bool:
    """Write one ticker's result. Returns whether it is a verified mapping."""
    # This enforces the application invariant before setting the selected
    # primary. It includes legacy non-Xetra German rows from any earlier probe.
    RadarInstrument.query.filter_by(ticker=ticker, market='de').update(
        {RadarInstrument.is_primary: False}, synchronize_session=False)

    row = RadarInstrument.query.filter_by(
        ticker=ticker, market='de', mic=XETRA_MIC).one_or_none()
    if row is None:
        row = RadarInstrument(
            ticker=ticker, market='de', venue=XETRA_VENUE, mic=XETRA_MIC,
            provider_symbol=ticker, currency='EUR', is_primary=False,
            mapping_status='unavailable', mapped_at=now)
        db.session.add(row)

    if candidate is None:
        # This is written only after every catalog request completed. Retain
        # the old identifier as audit context, but never keep it primary.
        row.venue = XETRA_VENUE
        row.currency = 'EUR'
        row.is_primary = False
        row.mapping_status = 'unavailable'
        row.mapping_source = source
        row.mapped_at = now
        return False

    row.venue = XETRA_VENUE
    row.provider_symbol = candidate.symbol
    row.currency = candidate.currency
    row.isin = candidate.isin
    row.is_primary = True
    row.mapping_status = 'mapped'
    row.mapping_source = source
    row.mapped_at = now
    return True


def mapping_preview(provider) -> MappingResult:
    """Fetch catalog counts and stable matches without changing any database row."""
    us_instruments = _active_us_instruments()
    us_catalog, xetra_catalog = _load_catalogs(provider, us_instruments)
    if us_catalog is None:
        return MappingResult(False, 0, 0, 0, 0)

    active_tickers = {row.ticker for row in us_instruments}
    us_rows = [row for row in us_catalog if row.symbol in active_tickers]
    xetra_rows = [row for row in xetra_catalog if row.mic == XETRA_MIC and
                  row.currency == 'EUR']
    matches = map_xetra(us_rows, xetra_rows)
    return MappingResult(
        catalog_reachable=True,
        xetra_rows=len(xetra_rows),
        isin_rows=sum(1 for row in xetra_rows if _is_stable_isin(row.isin)),
        mapped_active_tickers=len(matches),
        unavailable_active_tickers=len(active_tickers - set(matches)),
    )


def refresh_mappings(provider, now: dt.datetime) -> MappingResult:
    """Persist a complete catalog result, preserving rows on any provider failure."""
    us_instruments = _active_us_instruments()
    us_catalog, xetra_catalog = _load_catalogs(provider, us_instruments)
    if us_catalog is None:
        return MappingResult(False, 0, 0, 0, 0)

    active_tickers = {row.ticker for row in us_instruments}
    us_rows = [row for row in us_catalog if row.symbol in active_tickers]
    xetra_rows = [row for row in xetra_catalog if row.mic == XETRA_MIC and
                  row.currency == 'EUR']
    matches = map_xetra(us_rows, xetra_rows)
    source = getattr(provider, 'mapping_source', 'catalog')

    try:
        mapped = 0
        unavailable = 0
        for ticker in sorted(active_tickers):
            if _upsert_de_row(ticker, matches.get(ticker), now, source):
                mapped += 1
            else:
                unavailable += 1
        # Every write is made after catalog completion and becomes visible in
        # this one commit.  Failure rolls the whole result back.
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return MappingResult(
        catalog_reachable=True,
        xetra_rows=len(xetra_rows),
        isin_rows=sum(1 for row in xetra_rows if _is_stable_isin(row.isin)),
        mapped_active_tickers=mapped,
        unavailable_active_tickers=unavailable,
    )
