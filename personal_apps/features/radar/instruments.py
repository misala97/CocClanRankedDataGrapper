"""Verified provider-catalog mappings for Radar's German instruments.

The social ticker is not a security identifier.  This module deliberately
joins listings only through ISIN and treats absent or ambiguous identifiers as
unavailable; it never falls back to symbols or company names.

Market-data v2 adds the VERSIONED generation machinery (spec §5): every
mapping change is a complete, hashed decision set persisted as a
``RadarMappingGeneration``, activated or rolled back atomically. The legacy
Twelve/Finnhub catalog path below it keeps running until the German
activation gate passes.
"""
import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import re
from collections import defaultdict
from collections.abc import Iterable

from extensions import db
from models import RadarInstrument, RadarMappingGeneration, TickerUniverse

from .prices import PriceUnavailable
from .prices.openfigi import is_supported_type


XETRA_MIC = 'XETR'
XETRA_VENUE = 'Xetra'

VENUE_BY_MIC = {'XGAT': 'Tradegate BSX', 'XETR': 'Xetra'}

REFUSAL_REASONS = frozenset({
    'no_us_share_class', 'ambiguous_us_share_class',
    'no_german_candidate', 'ambiguous_german_candidate',
    'official_reference_missing', 'currency_mismatch',
    'security_type_mismatch', 'override_invalid',
})

_OVERRIDES_PATH = (pathlib.Path(__file__).parent / 'data'
                   / 'german_instrument_overrides.json')
_OVERRIDE_KEYS = frozenset({
    'social_ticker', 'us_instrument_identifier', 'german_mic',
    'local_mnemonic', 'german_isin', 'currency', 'evidence_url',
    'reference_date', 'reviewer', 'reviewed_at',
})
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')


class IncompleteReference(Exception):
    """A reference universe could not be fetched completely.

    Deliberately NOT ``unavailable``: spec §5.4 forbids marking a mapping
    unavailable before both reference universes were fetched completely, so
    the generation build raises and writes nothing.
    """


@dataclasses.dataclass(frozen=True)
class VenueReferenceRow:
    """One row of an official venue reference universe (mini-capture R6)."""
    mic: str
    isin: str
    symbol: str
    name: str | None
    currency: str
    security_type: str


@dataclasses.dataclass(frozen=True)
class ReferenceCatalog:
    mic: str
    rows: tuple
    complete: bool
    content_sha256: str


@dataclasses.dataclass(frozen=True)
class Override:
    social_ticker: str
    us_instrument_identifier: str
    german_mic: str
    local_mnemonic: str
    german_isin: str
    currency: str
    evidence_url: str
    reference_date: str
    reviewer: str
    reviewed_at: str


@dataclasses.dataclass(frozen=True)
class MappingDecision:
    ticker: str
    status: str  # mapped | unavailable
    reason: str | None
    mic: str | None
    symbol: str | None
    isin: str | None
    currency: str | None
    mapping_source: str
    history_proxy_mic: str | None = None
    history_proxy_symbol: str | None = None
    history_proxy_isin: str | None = None
    history_proxy_currency: str | None = None


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


def parse_overrides(payload, now=None):
    """Strictly validated overrides keyed by social ticker.

    Overrides are exact data, not aliases: every key present, valid ISIN,
    known MIC, EUR, unique ticker, and a review no older than 366 days.
    """
    if not isinstance(payload, dict) or payload.get('version') != 1 or \
            not isinstance(payload.get('overrides'), list):
        raise ValueError('override file root must be '
                         '{"version": 1, "overrides": [...]}')
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    found = {}
    for entry in payload['overrides']:
        if not isinstance(entry, dict) or set(entry) != _OVERRIDE_KEYS:
            raise ValueError(f'override keys must be exactly '
                             f'{sorted(_OVERRIDE_KEYS)}')
        if entry['german_mic'] not in VENUE_BY_MIC:
            raise ValueError(f'unknown override MIC {entry["german_mic"]}')
        if not _ISIN_RE.match(entry['german_isin']):
            raise ValueError(f'invalid override ISIN {entry["german_isin"]}')
        if entry['currency'] != 'EUR':
            raise ValueError('override currency must be EUR')
        reviewed = dt.datetime.fromisoformat(
            entry['reviewed_at'].replace('Z', '+00:00')).replace(tzinfo=None)
        if now - reviewed > dt.timedelta(days=366):
            raise ValueError(
                f'override for {entry["social_ticker"]} was reviewed more '
                f'than 366 days ago')
        if entry['social_ticker'] in found:
            raise ValueError(
                f'duplicate override for {entry["social_ticker"]}')
        found[entry['social_ticker']] = Override(**entry)
    return found


def load_overrides(now=None):
    with open(_OVERRIDES_PATH, encoding='utf-8') as handle:
        return parse_overrides(json.load(handle), now=now)


def _reference_by_symbol(catalog):
    return {row.symbol: row for row in catalog.rows}


def _reference_supported(row):
    return is_supported_type(row.security_type)


def decide_mapping(instrument, provider, references_by_mic, overrides):
    """One deterministic decision: XGAT, then XETR, then an exact override.

    ``unavailable`` is allowed only when both official references say
    ``complete=True``; otherwise the whole generation build raises.
    """
    for mic in ('XGAT', 'XETR'):
        catalog = references_by_mic.get(mic)
        if catalog is None or not catalog.complete:
            raise IncompleteReference(
                f'{mic}: official reference universe is not complete')

    ticker = instrument.ticker
    share_classes = provider.us_share_classes([instrument]).get(ticker, ())
    reason = None
    if not share_classes:
        reason = 'no_us_share_class'
    elif len(share_classes) > 1:
        reason = 'ambiguous_us_share_class'
    elif not is_supported_type(share_classes[0].security_type):
        reason = 'security_type_mismatch'

    if reason is None:
        share_class = share_classes[0]
        venue_reason = 'no_german_candidate'
        verified_by_mic = {}
        for mic in ('XGAT', 'XETR'):
            candidates = provider.venue_candidates(
                {ticker: share_class}, mic).get(ticker, ())
            supported = [candidate for candidate in candidates
                         if is_supported_type(candidate.security_type)]
            if not supported:
                continue
            if len(supported) > 1:
                venue_reason = 'ambiguous_german_candidate'
                continue
            candidate = supported[0]
            row = _reference_by_symbol(
                references_by_mic[mic]).get(candidate.symbol)
            if row is None:
                venue_reason = 'official_reference_missing'
                continue
            if row.currency != 'EUR':
                venue_reason = 'currency_mismatch'
                continue
            if not _reference_supported(row):
                venue_reason = 'security_type_mismatch'
                continue
            verified_by_mic[mic] = row
        primary = (verified_by_mic.get('XGAT') or
                   verified_by_mic.get('XETR'))
        if primary is not None:
            proxy = verified_by_mic.get('XETR')
            if primary.mic != 'XGAT' or proxy is None or \
                    proxy.isin != primary.isin:
                proxy = None
            return MappingDecision(
                ticker=ticker, status='mapped', reason=None,
                mic=primary.mic, symbol=primary.symbol, isin=primary.isin,
                currency='EUR', mapping_source='openfigi',
                history_proxy_mic=proxy.mic if proxy else None,
                history_proxy_symbol=proxy.symbol if proxy else None,
                history_proxy_isin=proxy.isin if proxy else None,
                history_proxy_currency=proxy.currency if proxy else None)
        reason = venue_reason

    override = overrides.get(ticker)
    if override is not None:
        row = _reference_by_symbol(
            references_by_mic[override.german_mic]).get(
                override.local_mnemonic)
        if (row is not None and row.isin == override.german_isin and
                row.currency == override.currency):
            return MappingDecision(
                ticker=ticker, status='mapped', reason=None,
                mic=override.german_mic, symbol=override.local_mnemonic,
                isin=override.german_isin, currency=override.currency,
                mapping_source='override')
        reason = 'override_invalid'

    return MappingDecision(
        ticker=ticker, status='unavailable', reason=reason, mic=None,
        symbol=None, isin=None, currency=None, mapping_source='openfigi')


_HISTORY_PROXY_FIELDS = (
    'history_proxy_mic', 'history_proxy_symbol',
    'history_proxy_isin', 'history_proxy_currency',
)


def _decision_payload(decision):
    item = dataclasses.asdict(decision)
    for field in _HISTORY_PROXY_FIELDS:
        if item[field] is None:
            item.pop(field)
    return item


def _canonical_payload(decisions):
    ordered = sorted((_decision_payload(decision)
                      for decision in decisions),
                     key=lambda item: item['ticker'])
    return json.dumps({'decisions': ordered}, sort_keys=True,
                      separators=(',', ':'))


def persist_generation(decisions, now, *, market='de', source='openfigi'):
    """One shadow generation for a complete decision set; hash-deduplicated."""
    payload = _canonical_payload(decisions)
    sha = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    existing = RadarMappingGeneration.query.filter_by(
        payload_sha256=sha).one_or_none()
    if existing is not None:
        return existing
    mapped = sum(1 for decision in decisions if decision.status == 'mapped')
    generation = RadarMappingGeneration(
        market=market, status='shadow', source=source, payload_sha256=sha,
        payload_json=payload,
        summary_json=json.dumps({
            'decisions': len(decisions), 'mapped': mapped,
            'unavailable': len(decisions) - mapped}, sort_keys=True),
        created_at=now)
    db.session.add(generation)
    db.session.commit()
    return generation


def _generation_decisions(generation):
    payload = json.loads(generation.payload_json)
    sha = hashlib.sha256(
        _canonical_payload([MappingDecision(**item)
                            for item in payload['decisions']])
        .encode('utf-8')).hexdigest()
    if sha != generation.payload_sha256:
        raise ValueError(
            f'generation {generation.id}: payload hash does not verify')
    return [MappingDecision(**item) for item in payload['decisions']]


def _snapshot_legacy_generation(tickers, now):
    """The pre-activation German rows as a real rollback target."""
    rows = (RadarInstrument.query
            .filter(RadarInstrument.ticker.in_(tickers),
                    RadarInstrument.market == 'de')
            .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())
    decisions = []
    for ticker in sorted(tickers):
        primary = next((row for row in rows
                        if row.ticker == ticker and row.is_primary), None)
        if primary is not None and primary.mapping_status == 'mapped':
            decisions.append(MappingDecision(
                ticker=ticker, status='mapped', reason=None,
                mic=primary.mic, symbol=primary.provider_symbol,
                isin=primary.isin, currency=primary.currency,
                mapping_source=primary.mapping_source or 'legacy'))
        else:
            decisions.append(MappingDecision(
                ticker=ticker, status='unavailable', reason=None, mic=None,
                symbol=None, isin=None, currency=None,
                mapping_source='legacy'))
    return persist_generation(decisions, now, source='legacy')


def _apply_decision(decision, generation_id, now):
    """Upsert one ticker's German rows for an activation. Returns changes."""
    changed = 0
    RadarInstrument.query.filter_by(
        ticker=decision.ticker, market='de').update(
        {RadarInstrument.is_primary: False}, synchronize_session=False)
    if decision.status != 'mapped':
        # Refusals are recorded without inventing venue rows: only rows
        # that already exist flip to unavailable.
        RadarInstrument.query.filter_by(
            ticker=decision.ticker, market='de').update(
            {RadarInstrument.mapping_status: 'unavailable',
             RadarInstrument.mapped_at: now,
             RadarInstrument.mapping_generation_id: generation_id},
            synchronize_session=False)
        return 1
    row = RadarInstrument.query.filter_by(
        ticker=decision.ticker, market='de', mic=decision.mic).one_or_none()
    if row is None:
        row = RadarInstrument(
            ticker=decision.ticker, market='de',
            venue=VENUE_BY_MIC[decision.mic], mic=decision.mic,
            provider_symbol=decision.symbol, currency=decision.currency,
            is_primary=False, mapping_status='mapped', mapped_at=now)
        db.session.add(row)
    row.venue = VENUE_BY_MIC[decision.mic]
    row.provider_symbol = decision.symbol
    row.currency = decision.currency
    row.isin = decision.isin
    row.is_primary = True
    row.mapping_status = 'mapped'
    row.mapping_source = decision.mapping_source
    row.mapped_at = now
    row.mapping_generation_id = generation_id
    return changed + 1


def _apply_generation(generation, now):
    decisions = _generation_decisions(generation)
    mapped = [decision for decision in decisions
              if decision.status == 'mapped']
    identities = {(decision.mic, decision.isin) for decision in mapped}
    if len(identities) != len(mapped):
        raise ValueError(
            f'generation {generation.id}: duplicate venue identities')
    changed = 0
    for decision in decisions:
        changed += _apply_decision(decision, generation.id, now)
    return changed


def activate_generation(generation_id, now):
    """Make one shadow generation the active mapping, atomically."""
    generation = RadarMappingGeneration.query.get(generation_id)
    if generation is None:
        raise ValueError(f'no generation {generation_id}')
    tickers = [decision.ticker
               for decision in _generation_decisions(generation)]
    try:
        _snapshot_legacy_generation(tickers, now)
        RadarMappingGeneration.query.filter(
            RadarMappingGeneration.market == generation.market,
            RadarMappingGeneration.status == 'active',
            RadarMappingGeneration.id != generation.id).update(
            {RadarMappingGeneration.status: 'retired'},
            synchronize_session=False)
        changed = _apply_generation(generation, now)
        generation.status = 'active'
        generation.activated_at = now
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return changed


def rollback_generation(generation_id, now):
    """Re-apply a previously persisted generation, atomically."""
    generation = RadarMappingGeneration.query.get(generation_id)
    if generation is None:
        raise ValueError(f'no generation {generation_id}')
    try:
        RadarMappingGeneration.query.filter(
            RadarMappingGeneration.market == generation.market,
            RadarMappingGeneration.status == 'active',
            RadarMappingGeneration.id != generation.id).update(
            {RadarMappingGeneration.status: 'retired'},
            synchronize_session=False)
        changed = _apply_generation(generation, now)
        generation.status = 'active'
        generation.activated_at = now
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return changed


class _PrefetchedOpenFigi:
    """Batch every OpenFIGI lookup up front, answer per-ticker after.

    ``decide_mapping`` asks one ticker at a time; feeding it the raw
    provider makes one HTTP request PER TICKER and turns a 12.6k-ticker
    universe into a day of paced calls (observed in production
    2026-09-01). This wrapper runs the provider's real batching — one
    ``us_share_classes`` pass over all instruments, one
    ``venue_candidates`` pass per MIC over the tickers that can reach
    the venue step — and then serves ``decide_mapping`` from memory.

    The eligibility filter MUST mirror ``decide_mapping``'s gate exactly
    (exactly one share class of a supported type): those are the only
    tickers whose venue lookup is ever consulted.
    """

    def __init__(self, provider, instruments):
        self._share = provider.us_share_classes(instruments)
        eligible = {
            ticker: candidates[0]
            for ticker, candidates in self._share.items()
            if len(candidates) == 1 and
            is_supported_type(candidates[0].security_type)}
        self._venues = {mic: provider.venue_candidates(eligible, mic)
                        for mic in ('XGAT', 'XETR')}

    def us_share_classes(self, instruments):
        return {row.ticker: self._share.get(row.ticker, ())
                for row in instruments}

    def venue_candidates(self, share_classes, mic):
        return {ticker: self._venues[mic].get(ticker, ())
                for ticker in share_classes}


def build_generation(openfigi_provider, references_by_mic, overrides, now):
    """Decide every active US ticker and persist one shadow generation.

    A transport failure inside the provider raises PriceUnavailable and
    nothing is written; an incomplete reference raises IncompleteReference.
    """
    rows = _active_us_instruments()
    prefetched = _PrefetchedOpenFigi(openfigi_provider, rows)
    decisions = [
        decide_mapping(row, prefetched, references_by_mic, overrides)
        for row in rows]
    return persist_generation(decisions, now)


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
