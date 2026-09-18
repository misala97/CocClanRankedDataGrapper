# personal_apps/features/radar/universe_reconcile.py
"""What the directory and the database disagree about, and the one safe fix.

The reconciler is pure and proposes exactly one action: insert a US primary
`RadarInstrument` for an active identity that has none. Every other
disagreement is a report -- observe, hold, quarantine or review -- because the
MIC participates in `uq_radar_quote_market` and `uq_radar_daily_close_market`
and every reader filters on it, so rewriting one orphans stored quotes and
closes that a US row cannot recover (the sibling basis needs an ISIN and US
rows have none).

Three owner decisions are visible here as code:

- **D1** keeps the stored MIC of every existing row and reports a directory
  difference as drift, classified T1/T2/T3 by whether the operating MIC and
  the operator change. Both sides of all seven measured drift rows are ACTIVE
  ISO MICs, so drift is a history-continuity question, not a repair.
- **D2** makes a name change report-only. No identity text, baseline,
  `first_seen` or mapping moves because a name moved.
- **D3** leaves warrants, rights, units, preferreds and notes as identities
  with no price mapping.
- **D8** quarantines an unknown or unmappable listing rather than inventing
  `XNAS` or `XXXX` for it.

The name-comparison helpers are the importer's own
(`features/radar/universe.py`), imported rather than reimplemented: whether
two names are one company is a judgement, and two implementations of one
judgement is how the same symbol gets classified differently depending on
which code path asked.
"""
from __future__ import annotations

import contextlib
import csv
import dataclasses
import datetime as dt
import re

import sqlalchemy as sa

from .universe import _issuer_of, _significant
from .universe_directory import (
    KNOWN_LISTING_MICS, SYMBOL_FORM, VENUE_RULES, venue_rule,
)

MARKET = 'us'
CURRENCY = 'USD'
MAPPING_STATUS = 'mapped'
#: `radar_instruments.mapping_source` is String(24).
MAX_MAPPING_SOURCE = 24
#: One named MySQL lock serializes every universe-maintenance write.
LOCK_NAME = 'radar_universe_maintenance'

APPROVAL_COLUMNS = ('symbol', 'mic', 'source_kind', 'exchange_code',
                    'directory_sha256')
SHA256 = re.compile(r'^[0-9a-f]{64}$')

#: Every MIC's ISO type and operator, reversed out of the authority table.
#: Each listing MIC appears exactly once, so the reverse map is unambiguous.
MIC_METADATA = {rule.mic: (rule.mic_type, rule.operating_mic)
                for rule in VENUE_RULES.values()}

# Name-based security-type hints. A hint, never an identity: the directory
# publishes no security-type column, so these only route rows away from the
# safe set.
_TYPE_HINTS = (
    ('warrant', re.compile(r'\bwarrants?\b', re.I)),
    ('right', re.compile(r'\brights?\b', re.I)),
    ('unit', re.compile(r'\bunits?\b', re.I)),
    ('preferred', re.compile(r'\bpreferred\b|\bdepositary shares?\b.*\bpreferred\b',
                             re.I)),
    ('note', re.compile(r'\bnotes?\b|\bdebentures?\b|\bbonds?\b', re.I)),
    ('adr', re.compile(r'\bamerican depositary\b|\bADS\b|\bADR\b', re.I)),
)
_DERIVATIVE_TYPES = frozenset({'warrant', 'right', 'unit'})
_NON_COMMON_TYPES = _DERIVATIVE_TYPES | {'preferred', 'note'}
_SUFFIX_TYPES = {'W': 'warrant', 'R': 'right', 'U': 'unit'}

COHORTS = ('safe_mapping_candidates', 'non_common', 'name_review', 'mic_drift',
           'absent', 'conflicts', 'quarantined')


class ApprovalError(ValueError):
    """A reviewed approval manifest that may not be used as it stands."""


@dataclasses.dataclass(frozen=True)
class CurrentIdentity:
    """One `radar_ticker_universe` row, without the ORM."""
    symbol: str
    name: str | None
    exchange: str | None
    is_etf: bool | None
    active: bool


@dataclasses.dataclass(frozen=True)
class CurrentMapping:
    """One `radar_instruments` row, without the ORM."""
    ticker: str
    market: str
    mic: str
    venue: str
    provider_symbol: str
    currency: str
    is_primary: bool
    mapping_status: str

    @property
    def is_mapped_primary(self) -> bool:
        return (self.market == MARKET and self.is_primary
                and self.mapping_status == MAPPING_STATUS)


@dataclasses.dataclass(frozen=True)
class PlannedMapping:
    """Exactly the US primary row a safe candidate would receive."""
    ticker: str
    market: str
    venue: str
    mic: str
    provider_symbol: str
    currency: str
    isin: str | None
    is_primary: bool
    mapping_status: str
    mapping_source: str

    def as_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SafeCandidate:
    symbol: str
    action: str
    mapping: PlannedMapping
    source_kind: str
    exchange_code: str
    #: The directory's name for the listing, which the stored identity name
    #: matched when this was classified. Kept for the apply's D2 recheck and
    #: left out of the report, which is unchanged by it.
    name: str

    @property
    def market(self):
        return self.mapping.market

    @property
    def currency(self):
        return self.mapping.currency

    @property
    def provider_symbol(self):
        return self.mapping.provider_symbol

    @property
    def mic(self):
        return self.mapping.mic

    @property
    def venue(self):
        return self.mapping.venue

    def as_dict(self):
        return {'symbol': self.symbol, 'action': self.action,
                'source_kind': self.source_kind,
                'exchange_code': self.exchange_code,
                'mapping': self.mapping.as_dict()}


@dataclasses.dataclass(frozen=True)
class ReviewEntry:
    """A row that is reported and deliberately not acted on."""
    symbol: str
    action: str
    reason: str
    detail: str = ''
    mapping: None = None

    def as_dict(self):
        return {'symbol': self.symbol, 'action': self.action,
                'reason': self.reason, 'detail': self.detail}


@dataclasses.dataclass(frozen=True)
class DriftEntry:
    """A mapped row whose directory code now implies a different MIC."""
    symbol: str
    action: str
    reason: str
    detail: str
    stored_mic: str
    directory_mic: str
    stored_operating_mic: str | None
    directory_operating_mic: str
    mapping: None = None

    def as_dict(self):
        data = dataclasses.asdict(self)
        data.pop('mapping')
        return data


@dataclasses.dataclass(frozen=True)
class SyncedListing:
    """A listing whose one mapped US primary already matches the directory.

    Not a cohort and not in the report, because nothing is proposed for it.
    It is what lets a rerun recognise an approved row that is already present
    as this listing -- the one case in which an approval may be a no-op --
    instead of trusting that a row with the right ticker exists.
    """
    symbol: str
    source_kind: str
    exchange_code: str
    name: str


@dataclasses.dataclass(frozen=True)
class ApprovedMapping:
    """One reviewed row, bound to the exact directory bytes it was read from."""
    symbol: str
    mic: str
    source_kind: str
    exchange_code: str
    directory_sha256: str


@dataclasses.dataclass(frozen=True)
class Reconciliation:
    safe_mapping_candidates: tuple[SafeCandidate, ...]
    non_common: tuple[ReviewEntry, ...]
    name_review: tuple[ReviewEntry, ...]
    mic_drift: tuple[DriftEntry, ...]
    absent: tuple[ReviewEntry, ...]
    conflicts: tuple[ReviewEntry, ...]
    quarantined: tuple[ReviewEntry, ...]
    #: Listed symbols needing nothing: see `SyncedListing`.
    in_sync: tuple[SyncedListing, ...] = ()
    #: `(source_kind, sha256)` of the exact bytes this reconciliation was
    #: derived from. An approval manifest is bound to these, so a manifest
    #: reviewed against one publication cannot be applied against another.
    source_digests: tuple[tuple[str, str], ...] = ()

    def digest_for(self, source_kind):
        for kind, digest in self.source_digests:
            if kind == source_kind:
                return digest
        return None

    @property
    def cohorts(self):
        return {name: getattr(self, name) for name in COHORTS}

    @property
    def counts(self):
        return {name: len(getattr(self, name)) for name in COHORTS}

    def as_dict(self):
        return {name: [entry.as_dict() for entry in cohort]
                for name, cohort in self.cohorts.items()}


def reconcile(snapshot_rows, current_identities, current_mappings=(), *,
              mapping_source: str, source_digests=None) -> Reconciliation:
    """Compare one validated directory against current state. Pure.

    Nothing here reads a session, a file or a clock, and nothing mutates its
    inputs. `current_mappings` may contain non-US rows; they are ignored
    rather than reported, because the archived DE lane has no active writer
    and is none of this contract's business.
    """
    if len(mapping_source) > MAX_MAPPING_SOURCE:
        raise ValueError(f'mapping source is longer than '
                         f'{MAX_MAPPING_SOURCE} characters: {mapping_source}')

    rows = {row.symbol: row for row in snapshot_rows}
    identities = {item.symbol: item for item in current_identities}
    us_rows: dict[str, list[CurrentMapping]] = {}
    for item in current_mappings:
        if item.market == MARKET:
            us_rows.setdefault(item.ticker, []).append(item)

    primaries = {ticker: [row for row in items if row.is_mapped_primary]
                 for ticker, items in us_rows.items()}
    owners = {}
    for ticker, items in primaries.items():
        for item in items:
            owners.setdefault(item.provider_symbol, set()).add(ticker)

    absent_symbols = sorted(symbol for symbol, item in identities.items()
                            if item.active and symbol not in rows)
    absent_keys = {symbol: _pair_key(identities[symbol].name,
                                     identities[symbol].is_etf)
                   for symbol in absent_symbols}

    buckets = {name: [] for name in COHORTS}
    in_sync = []

    for symbol in sorted(rows):
        row = rows[symbol]
        rule = venue_rule(row.source_kind, row.exchange_code)
        if rule is None:
            buckets['quarantined'].append(ReviewEntry(
                symbol, 'quarantine_no_mapping', 'unknown_listing_code',
                f'{row.source_kind} code {row.exchange_code!r} is not a '
                f'documented listing value'))
            continue

        item = identities.get(symbol)
        if item is None:
            buckets['quarantined'].append(ReviewEntry(
                symbol, 'quarantine_no_mapping', 'identity_missing',
                'the directory lists a symbol with no radar identity'))
            continue

        mapped = primaries.get(symbol, [])
        if mapped:
            _classify_mapped(buckets, in_sync, row, item, mapped, rule)
            continue
        _classify_unmapped(buckets, row, item, rule, us_rows, owners,
                           absent_keys, mapping_source)

    for symbol in absent_symbols:
        mapped = primaries.get(symbol, [])
        buckets['absent'].append(ReviewEntry(
            symbol, 'observe_only', 'directory_absent',
            'mapped and absent from this directory'
            if mapped else 'unmapped and absent from this directory'))

    return Reconciliation(
        **{name: tuple(buckets[name]) for name in COHORTS},
        in_sync=tuple(in_sync),
        source_digests=tuple(sorted((source_digests or {}).items())))


def _classify_mapped(buckets, in_sync, row, item, mapped, rule):
    """A ticker that already has a mapped US primary. Nothing may be written."""
    if len(mapped) > 1:
        buckets['conflicts'].append(ReviewEntry(
            row.symbol, 'review_conflict', 'multiple_mapped_primaries',
            f'{len(mapped)} mapped primaries: '
            f'{", ".join(sorted(m.mic for m in mapped))}'))
        return
    if not item.active:
        buckets['conflicts'].append(ReviewEntry(
            row.symbol, 'review_conflict', 'identity_inactive',
            'a mapped primary on an inactive identity'))
        return

    stored = mapped[0]
    if stored.mic != rule.mic:
        buckets['mic_drift'].append(_drift(row, stored, rule))
        return

    kind = _name_change(item.name, row.name)
    if kind != 'none':
        buckets['name_review'].append(ReviewEntry(
            row.symbol, 'review_no_mutation', kind,
            'the directory name differs from the stored identity name'))
        return
    in_sync.append(SyncedListing(row.symbol, row.source_kind,
                                 row.exchange_code, row.name))


def _classify_unmapped(buckets, row, item, rule, us_rows, owners, absent_keys,
                       mapping_source):
    """A ticker with no mapped US primary: the only insert candidate there is."""
    symbol = row.symbol
    if not item.active:
        buckets['conflicts'].append(ReviewEntry(
            symbol, 'review_conflict', 'identity_inactive',
            'the directory lists an identity marked delisted'))
        return
    if us_rows.get(symbol):
        buckets['conflicts'].append(ReviewEntry(
            symbol, 'review_conflict', 'us_instrument_row_exists',
            f'{len(us_rows[symbol])} existing US row(s) that are not a '
            f'mapped primary'))
        return

    holders = owners.get(symbol, set()) - {symbol}
    if holders:
        buckets['conflicts'].append(ReviewEntry(
            symbol, 'review_conflict', 'provider_symbol_taken',
            f'provider symbol already mapped to '
            f'{", ".join(sorted(holders))}'))
        return

    paired = _pairs(_pair_key(row.name, row.is_etf), absent_keys)
    if paired:
        buckets['name_review'].append(ReviewEntry(
            symbol, 'review_no_mutation', 'corporate_action_pair',
            f'shares an issuer with absent {", ".join(paired)}'))
        return

    hint = _type_hint(row.name, symbol, row.source_kind == 'nasdaqlisted')
    if hint.startswith('uncorroborated_'):
        buckets['quarantined'].append(ReviewEntry(
            symbol, 'quarantine_no_mapping', 'security_type_unclear',
            f'the name suggests a {hint.split("_", 1)[1]} that the symbol '
            f'form does not corroborate'))
        return
    if hint in _NON_COMMON_TYPES:
        buckets['non_common'].append(ReviewEntry(
            symbol, 'identity_only', hint,
            'kept as an identity; D3 leaves non-common listings unmapped'))
        return

    # D2 before admission, exactly as for a mapped row: only an identity whose
    # stored name is the name the directory lists may be mapped without a
    # review. A changed first token can be a different company on a reused
    # symbol, and the other kinds are review-only under the same policy.
    kind = _name_change(item.name, row.name)
    if kind != 'none':
        buckets['name_review'].append(ReviewEntry(
            symbol, 'review_no_mutation', kind,
            'the directory name differs from the stored identity name'))
        return

    buckets['safe_mapping_candidates'].append(SafeCandidate(
        symbol, 'insert_us_primary',
        PlannedMapping(ticker=symbol, market=MARKET, venue=rule.venue,
                       mic=rule.mic, provider_symbol=symbol,
                       currency=CURRENCY, isin=None, is_primary=True,
                       mapping_status=MAPPING_STATUS,
                       mapping_source=mapping_source),
        source_kind=row.source_kind, exchange_code=row.exchange_code,
        name=row.name))


def _drift(row, stored, rule):
    """Classify a MIC difference the way the ISO register splits it.

    T1 a listing-tier move inside Nasdaq, T2 a move inside one operator's
    group, T3 a change of operating MIC and legal entity. All three preserve
    the stored MIC; only the review each needs differs.
    """
    stored_meta = MIC_METADATA.get(stored.mic)
    stored_operating = stored_meta[1] if stored_meta else None
    if stored_operating is None:
        reason = 'unknown_stored_mic'
    elif stored_operating != rule.operating_mic:
        reason = 'T3'
    elif stored_operating == 'XNAS':
        reason = 'T1'
    else:
        reason = 'T2'
    return DriftEntry(
        symbol=row.symbol, action='preserve_existing_mic', reason=reason,
        detail=f'stored {stored.mic}; directory code {row.exchange_code!r} in '
               f'{row.source_kind} implies {rule.mic}',
        stored_mic=stored.mic, directory_mic=rule.mic,
        stored_operating_mic=stored_operating,
        directory_operating_mic=rule.operating_mic)


def _name_change(old, new):
    """Which kind of name change this is, in the importer's own terms."""
    if (old or '') == (new or ''):
        return 'none'
    old_significant, new_significant = _significant(old or ''), _significant(new or '')
    if _alnum(old_significant) == _alnum(new_significant):
        return 'cosmetic'
    old_issuer = _significant(_issuer_of(old or ''))
    if old_issuer and old_issuer == _significant(_issuer_of(new or '')):
        return 'security_description'
    # Exactly `universe._is_reassignment`'s test, without its `delisted_at`
    # precondition -- which production never satisfies, because nothing calls
    # `mark_delisted` (finding F4).
    if old_significant.split()[:1] == new_significant.split()[:1]:
        return 'rename_same_first_token'
    return 'first_token_changed'


def _alnum(value):
    return re.findall(r'[a-z0-9]+', value)


def _type_hint(name, symbol, nasdaq):
    """A routing hint from the name, corroborated where Nasdaq allows it.

    Warrants, rights and units reach this universe only as five-letter Nasdaq
    symbols -- every NYSE-family form carries a dot or a space and never
    becomes an identity -- so those three need the fifth letter to agree with
    the name. 'Limited Partnership Units' alone is ordinary equity.
    """
    hints = [label for label, pattern in _TYPE_HINTS if pattern.search(name or '')]
    suffix = _SUFFIX_TYPES.get(symbol[-1]) if nasdaq and len(symbol) == 5 else None
    if suffix and suffix in hints:
        return suffix
    for hint in hints:
        if hint in _DERIVATIVE_TYPES:
            return 'uncorroborated_' + hint
    return hints[0] if hints else 'common_or_fund'


def _pair_key(name, is_etf):
    """(issuer key, first-token key) for cross-cohort corporate-action pairing.

    Funds pair on the full issuer key only: every new iShares or ProShares
    fund would otherwise pair with every closed one from the same sponsor.
    """
    key = _significant(_issuer_of(name or ''))
    first = key.split()[0] if key else ''
    if is_etf or len(first) < 4:
        first = ''
    return key, first


def _pairs(keys, other_keys):
    full, first = keys
    return sorted(symbol for symbol, (other_full, other_first)
                  in other_keys.items()
                  if (full and full == other_full)
                  or (first and first == other_first))


def load_approved_mappings(path) -> tuple[ApprovedMapping, ...]:
    """Read a reviewed manifest, or refuse it whole.

    The manifest is the only way the apply mode becomes reachable, so every
    value is checked here rather than trusted: the header is exact, the MIC
    must be one the confirmed table can produce, and it must be the MIC that
    this file's code actually implies. A manifest that disagrees with the
    contract is a review error, not a mapping instruction.
    """
    with open(path, newline='', encoding='utf-8') as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise ApprovalError(f'{path}: the manifest is empty')
        if tuple(header) != APPROVAL_COLUMNS:
            raise ApprovalError(
                f'{path}: expected exactly the columns '
                f'{",".join(APPROVAL_COLUMNS)}, found {",".join(header)}')

        approvals = {}
        for number, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(APPROVAL_COLUMNS):
                raise ApprovalError(f'{path}: line {number} has '
                                    f'{len(cells)} columns, expected '
                                    f'{len(APPROVAL_COLUMNS)}')
            approval = _approval(path, number, dict(zip(APPROVAL_COLUMNS,
                                                        cells)))
            if approval.symbol in approvals:
                raise ApprovalError(f'{path}: line {number} repeats the '
                                    f'duplicate symbol {approval.symbol}')
            approvals[approval.symbol] = approval

    if not approvals:
        raise ApprovalError(f'{path}: no approved rows')
    return tuple(approvals[symbol] for symbol in sorted(approvals))


def _approval(path, number, values):
    where = f'{path}: line {number}'
    symbol = values['symbol'].strip()
    if not SYMBOL_FORM.match(symbol):
        raise ApprovalError(f'{where}: {values["symbol"]!r} is not a plain '
                            f'one-to-five-letter symbol')
    source_kind = values['source_kind'].strip()
    code = values['exchange_code'].strip()
    mic = values['mic'].strip()
    if mic not in KNOWN_LISTING_MICS:
        raise ApprovalError(f'{where}: {mic!r} is not a confirmed US listing '
                            f'MIC')
    rule = venue_rule(source_kind, code)
    if rule is None:
        raise ApprovalError(f'{where}: {code!r} is not a documented '
                            f'{source_kind!r} listing code')
    if rule.mic != mic:
        raise ApprovalError(f'{where}: {mic} does not match {source_kind} '
                            f'code {code}, which is {rule.mic}')
    digest = values['directory_sha256'].strip()
    if not SHA256.match(digest):
        raise ApprovalError(f'{where}: {digest!r} is not a lowercase hex '
                            f'sha256 digest')
    return ApprovedMapping(symbol=symbol, mic=mic, source_kind=source_kind,
                           exchange_code=code, directory_sha256=digest)


class LockUnavailable(RuntimeError):
    """The maintenance lock is held, or this bind cannot provide one."""


class MappingInvariantError(RuntimeError):
    """A post-write invariant did not hold; the transaction is rolled back."""


@dataclasses.dataclass(frozen=True)
class ApplyResult:
    """What one apply did, by symbol. Carries no connection detail."""
    inserted: tuple[str, ...]
    skipped: tuple[str, ...]
    refused: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.refused


@contextlib.contextmanager
def named_lock(session):
    """Serialize maintenance on MySQL, and refuse anywhere else.

    A MySQL named lock belongs to the *connection* that took it. The lock is
    therefore taken and released on one dedicated connection held for the
    whole block, never through the ORM session: the session hands its
    connection back to the pool at commit, and a release issued afterwards can
    land on a different connection, leaving the real lock held for as long as
    the pooled one lives.

    `GET_LOCK(..., 0)` returns immediately rather than queueing, so a second
    run reports contention instead of waiting behind one. The release is in a
    `finally` because the lock is not transactional.
    """
    engine = session.get_bind()
    backend = engine.dialect.name
    if backend not in ('mysql', 'mariadb'):
        raise LockUnavailable(
            f'no named lock is available on {backend}; inject a lock adapter '
            f'for an isolated test target')
    with engine.connect() as connection:
        acquired = connection.execute(sa.text('SELECT GET_LOCK(:name, 0)'),
                                      {'name': LOCK_NAME}).scalar()
        if acquired != 1:
            raise LockUnavailable(f'{LOCK_NAME} is held by another run')
        try:
            yield
        finally:
            connection.execute(sa.text('SELECT RELEASE_LOCK(:name)'),
                               {'name': LOCK_NAME})


def apply_approved_mappings(session, reconciliation, approvals, now_utc, *,
                            lock=None) -> ApplyResult:
    """Insert the approved US primary rows, all of them or none.

    Every precondition is re-read inside the transaction. The dry-run report
    was produced before the lock was taken, so it is a proposal and never
    evidence about the database's current contents.

    `session` supplies the database and nothing else. The transaction the
    writer reads and writes in is begun on a session of its own only once
    the lock is held, and ends -- committed or rolled back -- before the lock
    is let go. A caller's session may still be inside the transaction its
    report read, and on MySQL a transaction's first read fixes its snapshot:
    rechecking there would re-read the state from before the lock, which is
    exactly the state the lock exists to move past.

    A symbol that already carries exactly the approved identity is skipped, so
    a repeated run is a no-op rather than a refusal -- but only after it has
    passed every check an insert must pass. Anything else about a symbol -- a
    missing approval, a manifest bound to different directory bytes, a
    listing the current reconciliation does not bind to the approval, a
    different MIC or venue, an identity that is gone or no longer active, a
    conflicting US row, a provider symbol another mapped primary owns --
    refuses the whole batch. There is no partial success, no rewrite of an
    existing row and no removal of one.
    """
    from models import RadarInstrument

    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError('now_utc must be a timezone-aware UTC datetime')
    # Naive UTC, which is what every reader compares against. The one-off
    # backfill stamped Europe/Berlin local time instead; that inconsistency is
    # recorded in the B evidence and deliberately not repeated here.
    stamped = now_utc.astimezone(dt.timezone.utc).replace(tzinfo=None)

    candidates = {item.symbol: item
                  for item in reconciliation.safe_mapping_candidates}
    synced = {item.symbol: item for item in reconciliation.in_sync}
    take_lock = named_lock if lock is None else lock

    inserted, skipped, refused, problems = [], [], [], []
    with take_lock(session):
        # No autobegin: nothing below may read outside the one transaction
        # begun here, under the lock.
        with sa.orm.Session(bind=session.get_bind(),
                            autobegin=False) as writer:
            writer.begin()
            try:
                pending = []
                for approval in sorted(approvals,
                                       key=lambda item: item.symbol):
                    problem, planned = _recheck(
                        writer, approval, reconciliation,
                        candidates.get(approval.symbol),
                        synced.get(approval.symbol))
                    if problem is not None:
                        refused.append(approval.symbol)
                        problems.append(problem)
                        continue
                    if planned is None:
                        skipped.append(approval.symbol)
                        continue

                    pending.append(RadarInstrument(
                        ticker=planned.ticker, market=planned.market,
                        venue=planned.venue, mic=planned.mic,
                        provider_symbol=planned.provider_symbol,
                        currency=planned.currency, isin=planned.isin,
                        is_primary=planned.is_primary,
                        mapping_status=planned.mapping_status,
                        mapping_source=planned.mapping_source,
                        mapped_at=stamped))

                if refused or not pending:
                    writer.rollback()
                else:
                    writer.add_all(pending)
                    writer.flush()
                    _assert_invariants(writer, pending)
                    tickers = [row.ticker for row in pending]
                    writer.commit()
                    inserted = tickers
            except Exception:
                writer.rollback()
                raise

    return ApplyResult(tuple(sorted(inserted)), tuple(sorted(skipped)),
                       tuple(sorted(refused)), tuple(problems))


def _contract_row(symbol, rule):
    """Every field of the one US primary row an approval may create or find."""
    return {'ticker': symbol, 'market': MARKET, 'venue': rule.venue,
            'mic': rule.mic, 'provider_symbol': symbol, 'currency': CURRENCY,
            'is_primary': True, 'mapping_status': MAPPING_STATUS}


def _differences(expected, row):
    """The contract fields on which `row` differs from `expected`, sorted."""
    return sorted(field for field, value in expected.items()
                  if (bool(getattr(row, field)) if field == 'is_primary'
                      else getattr(row, field)) != value)


def _recheck(session, approval, reconciliation, candidate, synced):
    """Refuse, skip or insert one approved symbol, against current state.

    Returns `(problem, None)` to refuse it, `(None, None)` when exactly the
    approved row is already present, and `(None, planned)` to insert. Both
    outcomes that do not refuse run through every check below: a row that
    happens to exist proves nothing about whether the approval still
    describes it, so a skip is earned exactly the way an insert is.

    `candidate` is the symbol's safe candidate in this reconciliation and
    `synced` its unchanged mapped listing; a symbol is bound by at most one.
    """
    from models import RadarInstrument, TickerUniverse

    symbol = approval.symbol
    rule = venue_rule(approval.source_kind, approval.exchange_code)
    if rule is None or rule.mic != approval.mic:
        return (f'{symbol}: approved {approval.mic} for '
                f'{approval.source_kind} code {approval.exchange_code!r}, '
                f'which the confirmed code table does not give'), None

    digest = reconciliation.digest_for(approval.source_kind)
    if digest != approval.directory_sha256:
        return (f'{symbol}: the manifest was reviewed against sha256 '
                f'{approval.directory_sha256[:16]}..., this run parsed '
                f'{"none" if digest is None else digest[:16] + "..."}'), None

    listing = candidate or synced
    if listing is None:
        return (f'{symbol}: neither a safe mapping candidate nor an '
                f'unchanged mapping in this reconciliation'), None
    if listing.source_kind != approval.source_kind:
        return (f'{symbol}: approved as {approval.source_kind}, but the '
                f'directory lists it in {listing.source_kind}'), None
    if listing.exchange_code != approval.exchange_code:
        return (f'{symbol}: approved for code {approval.exchange_code}, but '
                f'the directory says {listing.exchange_code}'), None

    expected = _contract_row(symbol, rule)
    planned = None
    if candidate is not None:
        planned = candidate.mapping
        wrong = _differences(expected, planned)
        if planned.isin is not None:
            wrong.append('isin')
        if wrong:
            return (f'{symbol}: the planned row differs from the contract in '
                    f'{", ".join(wrong)}'), None
        if len(planned.mapping_source) > MAX_MAPPING_SOURCE:
            return (f'{symbol}: mapping source is longer than '
                    f'{MAX_MAPPING_SOURCE} characters'), None

    identity = (session.query(TickerUniverse.name, TickerUniverse.delisted_at)
                .filter(TickerUniverse.symbol == symbol).one_or_none())
    if identity is None:
        return f'{symbol}: no radar identity exists for this symbol', None
    name, delisted_at = identity
    if delisted_at is not None:
        return f'{symbol}: the identity is no longer active', None
    # D2 again, now under the lock: an identity renamed since the report is
    # not the identity that was classified and reviewed.
    kind = _name_change(name, listing.name)
    if kind != 'none':
        return (f'{symbol}: the identity name no longer matches the '
                f'directory name ({kind}); D2 holds it for review'), None

    owner = (session.query(RadarInstrument.ticker)
             .filter(RadarInstrument.market == MARKET,
                     RadarInstrument.is_primary.is_(True),
                     RadarInstrument.mapping_status == MAPPING_STATUS,
                     RadarInstrument.provider_symbol == symbol,
                     RadarInstrument.ticker != symbol)
             .order_by(RadarInstrument.ticker).first())
    if owner is not None:
        return (f'{symbol}: provider symbol {symbol} is already mapped to '
                f'{owner[0]}'), None

    existing = (session.query(RadarInstrument)
                .filter(RadarInstrument.ticker == symbol,
                        RadarInstrument.market == MARKET).all())
    if not existing:
        if planned is None:
            return (f'{symbol}: its mapped US row is gone, and this '
                    f'reconciliation proposed no insert for it'), None
        return None, planned
    if len(existing) > 1:
        return (f'{symbol}: {len(existing)} existing US instrument rows; '
                f'only one exact row may be skipped'), None
    wrong = _differences(expected, existing[0])
    if wrong:
        return (f'{symbol}: its existing US row differs from the approved '
                f'identity in {", ".join(wrong)}'), None
    return None, None


def _assert_invariants(session, inserted):
    """Re-check the contract after the flush and before the commit.

    Only US rows are read. A new US ticker may share its symbol with an
    archived DE instrument; that row is neither touched nor a conflict, and
    reading it here would refuse a legitimate batch.
    """
    from models import RadarInstrument

    for row in inserted:
        if row.market != MARKET or row.currency != CURRENCY:
            raise MappingInvariantError(
                f'{row.ticker}: an inserted row is {row.market}/{row.currency}')

    tickers = sorted({row.ticker for row in inserted})
    rows = (session.query(RadarInstrument)
            .filter(RadarInstrument.ticker.in_(tickers),
                    RadarInstrument.market == MARKET).all())
    primaries = {ticker: [] for ticker in tickers}
    for row in rows:
        if row.is_primary and row.mapping_status == MAPPING_STATUS:
            primaries[row.ticker].append(row)
    for ticker, found in primaries.items():
        if len(found) != 1:
            raise MappingInvariantError(
                f'{ticker}: {len(found)} mapped US primaries after the write')

    symbols = sorted({row.provider_symbol for row in inserted})
    clashes = (session.query(RadarInstrument.provider_symbol,
                             sa.func.count(RadarInstrument.id))
               .filter(RadarInstrument.market == MARKET,
                       RadarInstrument.is_primary.is_(True),
                       RadarInstrument.mapping_status == MAPPING_STATUS,
                       RadarInstrument.provider_symbol.in_(symbols))
               .group_by(RadarInstrument.provider_symbol)
               .having(sa.func.count(RadarInstrument.id) > 1).all())
    if clashes:
        raise MappingInvariantError(
            f'provider symbols shared after the write: '
            f'{", ".join(sorted(symbol for symbol, _ in clashes))}')


def load_current_state(session):
    """Current identities and US instrument rows, by bounded read only.

    Two `SELECT`s, ordered for determinism, and nothing else. Archived non-US
    instrument rows are never selected.
    """
    from models import RadarInstrument, TickerUniverse

    identities = tuple(
        CurrentIdentity(symbol=symbol, name=name, exchange=exchange,
                        is_etf=None if is_etf is None else bool(is_etf),
                        active=delisted_at is None)
        for symbol, name, exchange, is_etf, delisted_at in
        session.query(TickerUniverse.symbol, TickerUniverse.name,
                      TickerUniverse.exchange, TickerUniverse.is_etf,
                      TickerUniverse.delisted_at)
        .order_by(TickerUniverse.symbol).all())

    mappings = tuple(
        CurrentMapping(ticker=ticker, market=market, mic=mic, venue=venue,
                       provider_symbol=provider_symbol, currency=currency,
                       is_primary=bool(is_primary),
                       mapping_status=mapping_status)
        for ticker, market, mic, venue, provider_symbol, currency,
        is_primary, mapping_status in
        session.query(RadarInstrument.ticker, RadarInstrument.market,
                      RadarInstrument.mic, RadarInstrument.venue,
                      RadarInstrument.provider_symbol,
                      RadarInstrument.currency, RadarInstrument.is_primary,
                      RadarInstrument.mapping_status)
        .filter(RadarInstrument.market == MARKET)
        .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())

    return identities, mappings
