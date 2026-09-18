# personal_apps/tests/test_radar_universe_mapping_apply.py
"""The only write B1 owns: inserting a US primary that does not exist yet.

Every test here runs against an isolated in-memory SQLite database holding
only `radar_ticker_universe` and `radar_instruments`. No protected or
disposable MySQL database is bound, and the real 114-row apply is not executed
anywhere in this suite.

The writer is insert-only and all-or-nothing. It re-queries every precondition
inside its own transaction rather than trusting the dry-run report, because
the report was produced before the lock was taken and the database can have
moved underneath it.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from features.radar.universe_directory import DirectoryRow
from features.radar.universe_reconcile import (
    ApprovedMapping, CurrentIdentity, CurrentMapping, LockUnavailable,
    apply_approved_mappings, reconcile,
)

NOW_UTC = dt.datetime(2026, 9, 18, 9, 30, tzinfo=dt.timezone.utc)
SOURCE = 'nasdaqdir-20260915'
SHA = 'bd5524e05ab8530c482882df7f9eb109b9a9f96cf73dd67872ee911251262ddd'
OTHER_SHA = ('861023735ffebda2ede5059070f622d8ba2fb541'
             '75e78e5d73275b2701bd9b96')
DIGESTS = {'nasdaqlisted': SHA, 'otherlisted': OTHER_SHA}


class _NullLock:
    """The injected lock adapter the unit boundary permits for SQLite."""

    def __init__(self, available=True):
        self.available = available
        self.taken = 0
        self.released = 0

    def __call__(self, session):
        return self

    def __enter__(self):
        if not self.available:
            raise LockUnavailable('radar_universe_maintenance is held')
        self.taken += 1
        return self

    def __exit__(self, *exc):
        self.released += 1
        return False


def row(symbol, name=None, code='G', *, kind='nasdaqlisted', is_etf=False):
    return DirectoryRow(symbol=symbol,
                        name=name or f'{symbol} Corp. - Common Stock',
                        exchange_code=code, is_etf=is_etf, source_kind=kind)


def identity(symbol, name=None, code='G', *, is_etf=False, active=True):
    return CurrentIdentity(symbol=symbol,
                           name=name or f'{symbol} Corp. - Common Stock',
                           exchange=code, is_etf=is_etf, active=active)


def mapping(ticker, mic='XNMS', *, venue='Nasdaq Global Market',
            provider_symbol=None, currency='USD', is_primary=True,
            status='mapped', market='us'):
    return CurrentMapping(ticker=ticker, market=market, mic=mic, venue=venue,
                          provider_symbol=provider_symbol or ticker,
                          currency=currency, is_primary=is_primary,
                          mapping_status=status)


def approval(symbol, mic='XNMS', code='G', kind='nasdaqlisted', digest=SHA):
    return ApprovedMapping(symbol=symbol, mic=mic, source_kind=kind,
                           exchange_code=code, directory_sha256=digest)


def plan(rows, identities, mappings=()):
    return reconcile(rows, identities, mappings, mapping_source=SOURCE,
                     source_digests=DIGESTS)


@pytest.fixture()
def db_session():
    """One disposable SQLite database per test. Never a MySQL target."""
    from models import RadarInstrument, TickerUniverse

    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    for model in (TickerUniverse, RadarInstrument):
        model.__table__.create(engine)
    session = sa.orm.Session(engine)
    assert engine.url.get_backend_name() == 'sqlite'
    assert engine.url.database in (None, ''), engine.url
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed(session, identities=(), mappings=()):
    from models import RadarInstrument, TickerUniverse

    for index, item in enumerate(identities, start=1):
        session.add(TickerUniverse(
            id=index, symbol=item.symbol, name=item.name,
            exchange=item.exchange, is_etf=item.is_etf,
            first_seen=dt.datetime(2026, 8, 21, 8, 15),
            delisted_at=None if item.active else dt.datetime(2026, 9, 1)))
    for index, item in enumerate(mappings, start=1):
        session.add(RadarInstrument(
            id=index, ticker=item.ticker, market=item.market, venue=item.venue,
            mic=item.mic, provider_symbol=item.provider_symbol,
            currency=item.currency, is_primary=item.is_primary,
            mapping_status=item.mapping_status,
            mapping_source='nasdaq-directory',
            mapped_at=dt.datetime(2026, 8, 30, 14, 28)))
    session.commit()


def instruments(session):
    from models import RadarInstrument
    return session.query(RadarInstrument).order_by(
        RadarInstrument.ticker, RadarInstrument.mic).all()


# --- the successful insert -----------------------------------------------------

def test_one_approved_candidate_is_inserted_with_exactly_the_contract_row(
        db_session):
    seed(db_session, [identity('SAFE')])
    result = apply_approved_mappings(
        db_session, plan([row('SAFE')], [identity('SAFE')]),
        [approval('SAFE')], NOW_UTC, lock=_NullLock())

    assert result.inserted == ('SAFE',)
    assert result.skipped == ()
    assert result.refused == ()

    inserted = instruments(db_session)[0]
    assert inserted.ticker == 'SAFE'
    assert inserted.market == 'us'
    assert inserted.currency == 'USD'
    assert inserted.mic == 'XNMS'
    assert inserted.venue == 'Nasdaq Global Market'
    assert inserted.provider_symbol == inserted.ticker
    assert inserted.is_primary is True
    assert inserted.mapping_status == 'mapped'
    assert inserted.mapping_source == 'nasdaqdir-20260915'
    assert inserted.mapped_at == NOW_UTC.replace(tzinfo=None)
    assert inserted.isin is None
    assert inserted.mapping_generation_id is None
    assert inserted.history_due_at is None


def test_the_lock_is_taken_and_always_released(db_session):
    seed(db_session, [identity('SAFE')])
    lock = _NullLock()
    apply_approved_mappings(db_session, plan([row('SAFE')], [identity('SAFE')]),
                            [approval('SAFE')], NOW_UTC, lock=lock)
    assert (lock.taken, lock.released) == (1, 1)


def test_several_candidates_insert_together(db_session):
    rows = [row('AAA', code='Q'), row('BBB'), row('CCC', code='S')]
    ids = [identity('AAA', code='Q'), identity('BBB'),
           identity('CCC', code='S')]
    seed(db_session, ids)
    result = apply_approved_mappings(
        db_session, plan(rows, ids),
        [approval('AAA', 'XNGS', 'Q'), approval('BBB'),
         approval('CCC', 'XNCM', 'S')], NOW_UTC, lock=_NullLock())

    assert result.inserted == ('AAA', 'BBB', 'CCC')
    assert [i.mic for i in instruments(db_session)] == ['XNGS', 'XNMS', 'XNCM']


def test_a_rerun_skips_instead_of_inserting_again(db_session):
    seed(db_session, [identity('SAFE')])
    reconciliation = plan([row('SAFE')], [identity('SAFE')])
    apply_approved_mappings(db_session, reconciliation, [approval('SAFE')],
                            NOW_UTC, lock=_NullLock())
    first = instruments(db_session)[0].mapped_at

    later = NOW_UTC + dt.timedelta(days=1)
    result = apply_approved_mappings(db_session, reconciliation,
                                     [approval('SAFE')], later,
                                     lock=_NullLock())

    assert result.inserted == ()
    assert result.skipped == ('SAFE',)
    assert result.refused == ()
    assert len(instruments(db_session)) == 1
    assert instruments(db_session)[0].mapped_at == first


def test_a_rerun_against_a_freshly_reconciled_plan_also_skips(db_session):
    """The realistic rerun: the reconciler now sees the row as mapped, so the
    symbol is no longer a safe candidate at all."""
    seed(db_session, [identity('SAFE')])
    apply_approved_mappings(db_session, plan([row('SAFE')], [identity('SAFE')]),
                            [approval('SAFE')], NOW_UTC, lock=_NullLock())

    after = plan([row('SAFE')], [identity('SAFE')], [mapping('SAFE')])
    assert not after.safe_mapping_candidates
    result = apply_approved_mappings(db_session, after, [approval('SAFE')],
                                     NOW_UTC, lock=_NullLock())
    assert (result.inserted, result.skipped, result.refused) == (
        (), ('SAFE',), ())
    assert len(instruments(db_session)) == 1


# --- refusals: the whole batch or nothing --------------------------------------

def _refused(db_session, reconciliation, approvals, now=NOW_UTC, lock=None):
    before = len(instruments(db_session))
    result = apply_approved_mappings(db_session, reconciliation, approvals,
                                     now, lock=lock or _NullLock())
    assert result.inserted == ()
    assert len(instruments(db_session)) == before
    return result


def test_a_candidate_without_an_approval_is_never_inserted(db_session):
    rows = [row('SAFE'), row('NOPE')]
    ids = [identity('SAFE'), identity('NOPE')]
    seed(db_session, ids)
    result = apply_approved_mappings(db_session, plan(rows, ids),
                                     [approval('SAFE')], NOW_UTC,
                                     lock=_NullLock())
    assert result.inserted == ('SAFE',)
    assert [i.ticker for i in instruments(db_session)] == ['SAFE']


def test_an_approval_for_something_that_is_not_a_safe_candidate_is_refused(
        db_session):
    name = 'Alpha Acquisition Corp - Warrants'
    seed(db_session, [identity('AAAAW', name)])
    result = _refused(db_session, plan([row('AAAAW', name)],
                                       [identity('AAAAW', name)]),
                      [approval('AAAAW')])
    assert result.refused == ('AAAAW',)
    assert any('safe' in problem for problem in result.problems)


def test_a_directory_hash_mismatch_refuses_the_whole_batch(db_session):
    rows = [row('SAFE'), row('ALSO')]
    ids = [identity('SAFE'), identity('ALSO')]
    seed(db_session, ids)
    stale = SHA[:-1] + ('0' if SHA[-1] != '0' else '1')
    result = _refused(db_session, plan(rows, ids),
                      [approval('SAFE'), approval('ALSO', digest=stale)])
    assert result.refused == ('ALSO',)
    assert any('sha256' in problem for problem in result.problems)


def test_an_approval_naming_a_different_mic_is_refused(db_session):
    seed(db_session, [identity('SAFE')])
    result = _refused(db_session, plan([row('SAFE')], [identity('SAFE')]),
                      [approval('SAFE', 'XNCM', 'S')])
    assert result.refused == ('SAFE',)
    assert any('XNCM' in problem or 'code' in problem
               for problem in result.problems)


def test_an_identity_that_went_inactive_since_the_report_is_refused(db_session):
    from models import TickerUniverse

    seed(db_session, [identity('SAFE')])
    reconciliation = plan([row('SAFE')], [identity('SAFE')])
    db_session.query(TickerUniverse).filter_by(symbol='SAFE').update(
        {'delisted_at': dt.datetime(2026, 9, 17)})
    db_session.commit()

    result = _refused(db_session, reconciliation, [approval('SAFE')])
    assert result.refused == ('SAFE',)
    assert any('active' in problem for problem in result.problems)


def test_an_identity_that_disappeared_since_the_report_is_refused(db_session):
    from models import TickerUniverse

    seed(db_session, [identity('SAFE')])
    reconciliation = plan([row('SAFE')], [identity('SAFE')])
    db_session.query(TickerUniverse).filter_by(symbol='SAFE').delete()
    db_session.commit()

    result = _refused(db_session, reconciliation, [approval('SAFE')])
    assert result.refused == ('SAFE',)


def test_a_us_row_that_appeared_since_the_report_is_refused(db_session):
    """A different MIC arriving between the report and the apply is exactly
    what the in-transaction recheck exists for."""
    seed(db_session, [identity('SAFE')])
    reconciliation = plan([row('SAFE')], [identity('SAFE')])
    seed(db_session, [], [mapping('SAFE', 'XNCM', status='held',
                                  is_primary=False)])

    result = _refused(db_session, reconciliation, [approval('SAFE')])
    assert result.refused == ('SAFE',)
    assert any('US' in problem or 'us' in problem
               for problem in result.problems)
    assert [i.mic for i in instruments(db_session)] == ['XNCM']


def test_a_provider_symbol_taken_since_the_report_is_refused(db_session):
    seed(db_session, [identity('NEWX'), identity('OLDX')])
    reconciliation = plan([row('NEWX')],
                          [identity('NEWX'), identity('OLDX')])
    seed(db_session, [], [mapping('OLDX', provider_symbol='NEWX')])

    result = _refused(db_session, reconciliation, [approval('NEWX')])
    assert result.refused == ('NEWX',)
    assert any('provider symbol' in problem for problem in result.problems)


def test_a_second_mapped_primary_appearing_since_the_report_is_refused(
        db_session):
    seed(db_session, [identity('SAFE'), identity('DUPE')])
    reconciliation = plan([row('SAFE'), row('DUPE')],
                          [identity('SAFE'), identity('DUPE')])
    seed(db_session, [], [mapping('DUPE', 'XNMS'), mapping('DUPE', 'XNCM')])

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('DUPE')])
    assert result.refused == ('DUPE',)
    assert result.inserted == ()


# --- C2: a row is skipped only after every check an insert must pass ----------

def _already_mapped(db_session, *, venue='Nasdaq Global Market',
                    extra_ids=(), extra_maps=()):
    """SAFE mapped exactly as an earlier apply left it, beside NEWC: a valid
    new candidate that must not be inserted whenever the batch is refused."""
    ids = [identity('SAFE'), identity('NEWC'), *extra_ids]
    maps = [mapping('SAFE', venue=venue), *extra_maps]
    seed(db_session, ids, maps)
    return ids, maps


def _rerun_plan(ids, maps, rows=None):
    """The rerun as the CLI makes it: reconciled afresh from current state."""
    return plan(rows or [row('SAFE'), row('NEWC')], ids, maps)


def test_a_valid_exact_rerun_is_skipped_beside_a_new_insert(db_session):
    ids, maps = _already_mapped(db_session)
    reconciliation = _rerun_plan(ids, maps)
    assert [c.symbol for c in reconciliation.safe_mapping_candidates] == [
        'NEWC']

    result = apply_approved_mappings(db_session, reconciliation,
                                     [approval('SAFE'), approval('NEWC')],
                                     NOW_UTC, lock=_NullLock())

    assert (result.inserted, result.skipped, result.refused) == (
        ('NEWC',), ('SAFE',), ())
    assert [(i.ticker, i.mapping_source, i.mapped_at)
            for i in instruments(db_session)] == [
        ('NEWC', SOURCE, NOW_UTC.replace(tzinfo=None)),
        ('SAFE', 'nasdaq-directory', dt.datetime(2026, 8, 30, 14, 28))]


def test_a_stale_digest_refuses_an_already_applied_row_and_its_batch(
        db_session):
    ids, maps = _already_mapped(db_session)
    stale = SHA[:-1] + ('0' if SHA[-1] != '0' else '1')
    result = _refused(db_session, _rerun_plan(ids, maps),
                      [approval('SAFE', digest=stale), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('sha256' in problem for problem in result.problems)


def test_an_already_applied_row_whose_identity_is_gone_is_refused(db_session):
    from models import TickerUniverse

    ids, maps = _already_mapped(db_session)
    reconciliation = _rerun_plan(ids, maps)
    db_session.query(TickerUniverse).filter_by(symbol='SAFE').delete()
    db_session.commit()

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('identity' in problem for problem in result.problems)


def test_an_already_applied_row_whose_identity_went_inactive_is_refused(
        db_session):
    from models import TickerUniverse

    ids, maps = _already_mapped(db_session)
    reconciliation = _rerun_plan(ids, maps)
    db_session.query(TickerUniverse).filter_by(symbol='SAFE').update(
        {'delisted_at': dt.datetime(2026, 9, 17)})
    db_session.commit()

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('active' in problem for problem in result.problems)


def test_an_already_applied_row_at_the_wrong_venue_is_refused(db_session):
    """Same ticker, market, MIC and provider symbol is not the approved row
    when the venue differs: every field of the contract row must match."""
    ids, maps = _already_mapped(db_session, venue='Nasdaq Capital Market')
    result = _refused(db_session, _rerun_plan(ids, maps),
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('venue' in problem for problem in result.problems)


def test_an_already_applied_row_the_directory_now_disagrees_with_is_refused(
        db_session):
    """The directory now lists SAFE under another tier, so the current
    reconciliation reports drift for it: the approval no longer describes
    the listing, whatever row happens to exist."""
    ids, maps = _already_mapped(db_session)
    reconciliation = plan([row('SAFE', code='S'), row('NEWC')], ids, maps)
    assert [entry.symbol for entry in reconciliation.mic_drift] == ['SAFE']

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()


def test_an_already_applied_row_whose_provider_symbol_is_shared_is_refused(
        db_session):
    ids, maps = _already_mapped(
        db_session, extra_ids=[identity('OTHR')],
        extra_maps=[mapping('OTHR', provider_symbol='SAFE')])
    reconciliation = _rerun_plan(ids, maps,
                                 [row('SAFE'), row('NEWC'), row('OTHR')])

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('provider symbol' in problem for problem in result.problems)


# --- C3: D2 again at apply time ------------------------------------------------

@pytest.mark.parametrize('already_mapped', [False, True],
                         ids=['insert', 'skip'])
def test_an_identity_renamed_since_the_report_is_refused(db_session,
                                                         already_mapped):
    """The report saw SAFE under the name the directory lists. Renamed before
    the lock was taken, it is no longer the identity that was reviewed, so
    neither mapping it nor calling it already mapped is allowed (D2)."""
    from models import TickerUniverse

    maps = [mapping('SAFE')] if already_mapped else []
    ids = [identity('SAFE'), identity('NEWC')]
    seed(db_session, ids, maps)
    reconciliation = plan([row('SAFE'), row('NEWC')], ids, maps)
    db_session.query(TickerUniverse).filter_by(symbol='SAFE').update(
        {'name': 'Beta Holdings Inc. - Common Stock'})
    db_session.commit()

    result = _refused(db_session, reconciliation,
                      [approval('SAFE'), approval('NEWC')])
    assert result.refused == ('SAFE',)
    assert result.skipped == ()
    assert any('name' in problem for problem in result.problems)


def test_a_naive_timestamp_is_refused_before_anything_is_written(db_session):
    seed(db_session, [identity('SAFE')])
    with pytest.raises(ValueError, match='timezone|aware|UTC'):
        apply_approved_mappings(db_session,
                                plan([row('SAFE')], [identity('SAFE')]),
                                [approval('SAFE')],
                                dt.datetime(2026, 9, 18, 9, 30),
                                lock=_NullLock())
    assert instruments(db_session) == []


def test_a_non_utc_timestamp_is_stored_as_naive_utc(db_session):
    """Existing rows were stamped in Europe/Berlin local time by the one-off
    backfill; a new writer stamps naive UTC and the inconsistency is
    documented rather than repeated."""
    seed(db_session, [identity('SAFE')])
    berlin = dt.timezone(dt.timedelta(hours=2))
    apply_approved_mappings(db_session, plan([row('SAFE')], [identity('SAFE')]),
                            [approval('SAFE')],
                            NOW_UTC.astimezone(berlin), lock=_NullLock())
    assert instruments(db_session)[0].mapped_at == NOW_UTC.replace(tzinfo=None)


def test_an_empty_approval_set_writes_nothing(db_session):
    seed(db_session, [identity('SAFE')])
    result = apply_approved_mappings(
        db_session, plan([row('SAFE')], [identity('SAFE')]), [], NOW_UTC,
        lock=_NullLock())
    assert result == result.__class__((), (), (), result.problems)
    assert instruments(db_session) == []


# --- failure, contention and the archived lane ---------------------------------

def _failing_commit(monkeypatch, message):
    """Make every session's commit fail, whichever session the writer uses.

    The writer opens its own session once the lock is held, so the failure is
    injected on the class rather than on the caller's session object."""
    def explode(self):
        raise RuntimeError(message)

    monkeypatch.setattr(sa.orm.Session, 'commit', explode)


def test_an_injected_commit_failure_leaves_no_row_behind(db_session,
                                                          monkeypatch):
    seed(db_session, [identity('SAFE'), identity('ALSO')])
    rows = [row('SAFE'), row('ALSO')]
    ids = [identity('SAFE'), identity('ALSO')]

    _failing_commit(monkeypatch, 'injected failure')
    with pytest.raises(RuntimeError, match='injected failure'):
        apply_approved_mappings(db_session, plan(rows, ids),
                                [approval('SAFE'), approval('ALSO')],
                                NOW_UTC, lock=_NullLock())
    monkeypatch.undo()

    assert instruments(db_session) == []


def test_the_lock_is_released_after_an_injected_failure(db_session,
                                                        monkeypatch):
    seed(db_session, [identity('SAFE')])
    lock = _NullLock()
    _failing_commit(monkeypatch, 'boom')
    with pytest.raises(RuntimeError):
        apply_approved_mappings(db_session,
                                plan([row('SAFE')], [identity('SAFE')]),
                                [approval('SAFE')], NOW_UTC, lock=lock)
    monkeypatch.undo()
    assert (lock.taken, lock.released) == (1, 1)


def test_lock_contention_refuses_without_touching_the_database(db_session):
    seed(db_session, [identity('SAFE')])
    with pytest.raises(LockUnavailable):
        apply_approved_mappings(db_session,
                                plan([row('SAFE')], [identity('SAFE')]),
                                [approval('SAFE')], NOW_UTC,
                                lock=_NullLock(available=False))
    assert instruments(db_session) == []


def test_an_archived_de_eur_row_is_never_read_written_or_disturbed(db_session):
    from models import RadarInstrument

    seed(db_session, [identity('SAFE'), identity('XETRA')],
         [mapping('XETRA', 'XETR', venue='Xetra', currency='EUR',
                  market='de')])
    before = [(r.id, r.ticker, r.market, r.mic, r.venue, r.provider_symbol,
               r.currency, r.is_primary, r.mapping_status, r.mapping_source,
               r.mapped_at)
              for r in db_session.query(RadarInstrument).all()]

    apply_approved_mappings(db_session, plan([row('SAFE')], [identity('SAFE')]),
                            [approval('SAFE')], NOW_UTC, lock=_NullLock())

    after = [(r.id, r.ticker, r.market, r.mic, r.venue, r.provider_symbol,
              r.currency, r.is_primary, r.mapping_status, r.mapping_source,
              r.mapped_at)
             for r in db_session.query(RadarInstrument)
             .filter(RadarInstrument.market == 'de').all()]
    assert after == before
    assert db_session.query(RadarInstrument).filter(
        RadarInstrument.currency != 'USD').count() == 1


def test_a_us_ticker_sharing_its_symbol_with_an_archived_de_row_is_inserted(
        db_session):
    """The DE archive holds thousands of instruments. A new US listing whose
    symbol happens to match one is not a conflict: the archived row is a
    different market, is never read by this writer, and stays untouched."""
    from models import RadarInstrument

    seed(db_session, [identity('SAFE')],
         [mapping('SAFE', 'XETR', venue='Xetra', currency='EUR',
                  market='de')])
    archived_before = [
        (r.id, r.market, r.mic, r.currency, r.is_primary, r.mapping_status,
         r.mapped_at)
        for r in db_session.query(RadarInstrument).filter_by(market='de')]

    result = apply_approved_mappings(
        db_session, plan([row('SAFE')], [identity('SAFE')]),
        [approval('SAFE')], NOW_UTC, lock=_NullLock())

    assert result.inserted == ('SAFE',)
    assert result.refused == ()
    assert sorted((r.ticker, r.market, r.mic)
                  for r in instruments(db_session)) == [
        ('SAFE', 'de', 'XETR'), ('SAFE', 'us', 'XNMS')]
    archived_after = [
        (r.id, r.market, r.mic, r.currency, r.is_primary, r.mapping_status,
         r.mapped_at)
        for r in db_session.query(RadarInstrument).filter_by(market='de')]
    assert archived_after == archived_before


# --- C1: every recheck runs in a transaction begun under the lock --------------

@pytest.fixture()
def snapshot_engine(tmp_path):
    """A file SQLite database whose transactions really read a snapshot.

    The in-memory target above shares one connection between every session,
    so it cannot show what a stale transaction would see. Here each session
    gets its own connection, WAL lets a reader and a writer overlap, and every
    transaction opens with an explicit BEGIN: a transaction's first read fixes
    its snapshot until it ends, as MySQL's REPEATABLE READ does for the real
    writer. Never a MySQL target.
    """
    import pathlib

    from models import RadarInstrument, TickerUniverse

    engine = sa.create_engine(f'sqlite:///{tmp_path / "snapshot.db"}')

    @sa.event.listens_for(engine, 'connect')
    def connect(dbapi_connection, _):
        # pysqlite would otherwise defer BEGIN to the first write, so a
        # read-only transaction would hold no snapshot at all.
        dbapi_connection.isolation_level = None
        dbapi_connection.execute('PRAGMA journal_mode=WAL')
        dbapi_connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right))

    @sa.event.listens_for(engine, 'begin')
    def begin(connection):
        connection.exec_driver_sql('BEGIN')

    for model in (TickerUniverse, RadarInstrument):
        model.__table__.create(engine)
    assert engine.url.get_backend_name() == 'sqlite'
    assert pathlib.Path(engine.url.database).parent == tmp_path
    try:
        yield engine
    finally:
        engine.dispose()


class _LockAfterAnotherRun(_NullLock):
    """Taking the lock means the run that held it has just committed.

    `write` runs on a connection of its own before the lock is granted, so
    everything it commits is state the lock serializes. It also records
    whether the caller still held a transaction open when it asked."""

    def __init__(self, engine, write):
        super().__init__()
        self.engine = engine
        self.write = write
        self.caller_in_transaction = None

    def __call__(self, session):
        self.caller_in_transaction = session.in_transaction()
        return self

    def __enter__(self):
        with self.engine.begin() as connection:
            self.write(connection)
        return super().__enter__()


def _another_run_maps(ticker, mic):
    """What a run holding the lock before this one committed: a US row."""
    from models import RadarInstrument

    def write(connection):
        connection.execute(sa.insert(RadarInstrument.__table__).values(
            ticker=ticker, market='us', venue='Nasdaq Capital Market',
            mic=mic, provider_symbol=ticker, currency='USD', is_primary=True,
            mapping_status='mapped', mapping_source='another-run',
            mapped_at=dt.datetime(2026, 9, 18, 9, 29)))

    return write


def _us_rows(engine):
    from models import RadarInstrument

    with sa.orm.Session(engine) as reader:
        return [(r.ticker, r.mic, r.mapping_source)
                for r in reader.query(RadarInstrument)
                .filter(RadarInstrument.market == 'us')
                .order_by(RadarInstrument.ticker, RadarInstrument.mic)]


def test_a_snapshot_read_before_the_lock_cannot_satisfy_the_rechecks(
        snapshot_engine):
    """The caller read the state before the lock existed. Its transaction
    still sees that state after another run commits, so the rechecks must run
    in a transaction the apply begins only once the lock is held."""
    from features.radar.universe_reconcile import load_current_state

    with sa.orm.Session(snapshot_engine) as setup:
        seed(setup, [identity('SAFE')])
    report = sa.orm.Session(snapshot_engine)
    identities, mappings = load_current_state(report)
    assert report.in_transaction()
    reconciliation = reconcile([row('SAFE')], identities, mappings,
                               mapping_source=SOURCE, source_digests=DIGESTS)
    assert [c.symbol for c in reconciliation.safe_mapping_candidates] == [
        'SAFE']

    lock = _LockAfterAnotherRun(snapshot_engine,
                                _another_run_maps('SAFE', 'XNCM'))
    try:
        result = apply_approved_mappings(report, reconciliation,
                                         [approval('SAFE')], NOW_UTC,
                                         lock=lock)
    finally:
        report.close()

    assert result.refused == ('SAFE',)
    assert result.inserted == ()
    assert _us_rows(snapshot_engine) == [('SAFE', 'XNCM', 'another-run')]
    assert (lock.taken, lock.released) == (1, 1)


class _LockThatLooksOnRelease(_NullLock):
    """Reads the committed state, on a connection of its own, at release."""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.committed_at_release = None

    def __exit__(self, *exc):
        self.committed_at_release = _us_rows(self.engine)
        return super().__exit__(*exc)


def test_the_lock_is_held_until_the_writer_has_committed(snapshot_engine):
    """Released any earlier, the next run could take the lock and recheck
    before this run's rows were visible to it."""
    with sa.orm.Session(snapshot_engine) as setup:
        seed(setup, [identity('SAFE')])
    lock = _LockThatLooksOnRelease(snapshot_engine)

    with sa.orm.Session(snapshot_engine) as caller:
        result = apply_approved_mappings(
            caller, plan([row('SAFE')], [identity('SAFE')]),
            [approval('SAFE')], NOW_UTC, lock=lock)

    assert result.inserted == ('SAFE',)
    assert lock.committed_at_release == [('SAFE', 'XNMS', SOURCE)]


def test_the_cli_ends_its_report_read_before_it_asks_for_the_lock(
        tmp_path, snapshot_engine):
    """The dry-run report and the apply are one command. The report's read
    transaction is over before the lock is requested, and what the previous
    lock holder committed is what the apply rechecks against."""
    import hashlib
    import json

    from scripts import reconcile_radar_universe as cli

    with sa.orm.Session(snapshot_engine) as setup:
        seed(setup, [identity('SAFE', 'Safe Corp. - Common Stock'),
                     identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True)])
    nasdaq, other = _cli_fixture_pair(tmp_path)
    digest = hashlib.sha256(nasdaq.read_bytes()).hexdigest()
    manifest = _manifest(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{digest}\n')
    report = tmp_path / 'apply.json'
    session = sa.orm.Session(snapshot_engine)
    lock = _LockAfterAnotherRun(snapshot_engine,
                                _another_run_maps('SAFE', 'XNCM'))

    try:
        code = cli.main([str(nasdaq), str(other), '--report', str(report),
                         '--apply-mappings', '--approved-mappings',
                         str(manifest)],
                        session_factory=lambda: session, lock=lock)
    finally:
        session.close()

    assert lock.caller_in_transaction is False
    assert code == 1
    payload = json.loads(report.read_text(encoding='utf-8'))
    assert payload['apply']['inserted'] == []
    assert payload['apply']['refused'] == ['SAFE']
    assert _us_rows(snapshot_engine) == [('SAFE', 'XNCM', 'another-run')]


class _FakeConnection:
    def __init__(self, log, acquired):
        self.log = log
        self.acquired = acquired

    def execute(self, statement, params):
        self.log.append((id(self), str(statement), params['name']))
        value = self.acquired if 'GET_LOCK' in str(statement) else 1
        return type('Result', (), {'scalar': lambda _self: value})()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.log.append((id(self), 'closed', None))
        return False


class _FakeEngine:
    def __init__(self, backend='mysql', acquired=1):
        self.dialect = type('Dialect', (), {'name': backend})()
        self.log = []
        self.acquired = acquired
        self.connections = []

    def connect(self):
        connection = _FakeConnection(self.log, self.acquired)
        self.connections.append(connection)
        return connection


class _FakeSession:
    def __init__(self, engine):
        self.engine = engine

    def get_bind(self):
        return self.engine


def test_the_named_lock_is_taken_and_released_on_one_dedicated_connection():
    """A MySQL named lock belongs to a connection. Taking it through the ORM
    session and releasing it after a commit can release on a different pooled
    connection and strand the real lock; one dedicated connection cannot."""
    from features.radar.universe_reconcile import LOCK_NAME, named_lock

    engine = _FakeEngine()
    with named_lock(_FakeSession(engine)):
        pass

    assert len(engine.connections) == 1
    connection_ids = {entry[0] for entry in engine.log}
    assert len(connection_ids) == 1
    statements = [entry[1] for entry in engine.log]
    assert statements == ['SELECT GET_LOCK(:name, 0)',
                          'SELECT RELEASE_LOCK(:name)', 'closed']
    assert {entry[2] for entry in engine.log if entry[2]} == {LOCK_NAME}


def test_the_named_lock_is_released_when_the_block_raises():
    from features.radar.universe_reconcile import named_lock

    engine = _FakeEngine()
    with pytest.raises(RuntimeError, match='inside'):
        with named_lock(_FakeSession(engine)):
            raise RuntimeError('inside the lock')
    assert [entry[1] for entry in engine.log] == [
        'SELECT GET_LOCK(:name, 0)', 'SELECT RELEASE_LOCK(:name)', 'closed']


def test_a_held_named_lock_refuses_without_entering_the_block():
    from features.radar.universe_reconcile import named_lock

    engine = _FakeEngine(acquired=0)
    entered = []
    with pytest.raises(LockUnavailable, match='held'):
        with named_lock(_FakeSession(engine)):
            entered.append(True)
    assert entered == []
    assert 'SELECT RELEASE_LOCK(:name)' not in [e[1] for e in engine.log]


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_the_named_lock_refuses_a_bind_that_cannot_provide_one(backend):
    """Silently skipping serialization on an unexpected bind would be worse
    than refusing: the default lock is MySQL's or nothing."""
    from features.radar.universe_reconcile import named_lock

    engine = _FakeEngine(backend=backend)
    with pytest.raises(LockUnavailable):
        with named_lock(_FakeSession(engine)):
            pass
    assert engine.connections == []


def test_the_default_lock_refuses_the_isolated_sqlite_target(db_session):
    """Without an injected adapter the apply refuses on SQLite and writes
    nothing: serialization is never silently skipped."""
    seed(db_session, [identity('SAFE')])
    with pytest.raises(LockUnavailable):
        apply_approved_mappings(db_session,
                                plan([row('SAFE')], [identity('SAFE')]),
                                [approval('SAFE')], NOW_UTC)
    assert instruments(db_session) == []


def test_the_writer_never_updates_or_deletes_an_existing_row(db_session):
    """Whatever happens, an existing instrument row is untouched: the
    reconciler emits no update action and the writer implements none."""
    import inspect

    from features.radar import universe_reconcile

    source = inspect.getsource(universe_reconcile.apply_approved_mappings)
    for forbidden in ('delete(', '.update(', 'upsert_symbols', 'DELETE',
                      'UPDATE'):
        assert forbidden not in source


# --- the CLI apply branch ------------------------------------------------------

def _cli_fixture_pair(tmp_path):
    from tests.test_radar_universe_directory import (
        NASDAQ_HEADER, OTHER_HEADER, _write,
    )
    nasdaq = _write(tmp_path, 'nasdaqlisted.txt', NASDAQ_HEADER, (
        'SAFE|Safe Corp. - Common Stock|G|N|N|100|N|N',
    ))
    other = _write(tmp_path, 'otherlisted.txt', OTHER_HEADER, (
        'ARCA|Arca Fund ETF|P|ARCA|Y|100|N|ARCA',
    ), trailing_pipes=6)
    return nasdaq, other


def _manifest(tmp_path, body):
    path = tmp_path / 'approved.csv'
    path.write_text('symbol,mic,source_kind,exchange_code,directory_sha256\n'
                    + body, encoding='utf-8')
    return path


def test_the_cli_apply_branch_inserts_only_the_reviewed_rows(tmp_path,
                                                             db_session):
    import hashlib
    import json

    from scripts import reconcile_radar_universe as cli

    seed(db_session, [identity('SAFE', 'Safe Corp. - Common Stock'),
                      identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True)])
    nasdaq, other = _cli_fixture_pair(tmp_path)
    digest = hashlib.sha256(nasdaq.read_bytes()).hexdigest()
    manifest = _manifest(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{digest}\n')
    report = tmp_path / 'apply.json'

    code = cli.main([str(nasdaq), str(other), '--report', str(report),
                     '--apply-mappings', '--approved-mappings', str(manifest)],
                    session_factory=lambda: db_session, lock=_NullLock())

    assert code == 0
    payload = json.loads(report.read_text(encoding='utf-8'))
    assert payload['mode'] == 'apply'
    assert payload['apply'] == {'inserted': ['SAFE'], 'skipped': [],
                                'refused': [], 'problems': []}
    assert [(i.ticker, i.mic) for i in instruments(db_session)] == [
        ('SAFE', 'XNMS')]


def test_the_cli_apply_branch_writes_nothing_when_the_batch_is_refused(
        tmp_path, db_session):
    import json

    from scripts import reconcile_radar_universe as cli

    seed(db_session, [identity('SAFE', 'Safe Corp. - Common Stock'),
                      identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True)])
    nasdaq, other = _cli_fixture_pair(tmp_path)
    manifest = _manifest(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{SHA}\n')
    report = tmp_path / 'apply.json'

    code = cli.main([str(nasdaq), str(other), '--report', str(report),
                     '--apply-mappings', '--approved-mappings', str(manifest)],
                    session_factory=lambda: db_session, lock=_NullLock())

    assert code == 1
    payload = json.loads(report.read_text(encoding='utf-8'))
    assert payload['apply']['inserted'] == []
    assert payload['apply']['refused'] == ['SAFE']
    assert instruments(db_session) == []


def test_the_apply_result_carries_no_connection_detail(db_session):
    seed(db_session, [identity('SAFE')])
    result = apply_approved_mappings(
        db_session, plan([row('SAFE')], [identity('SAFE')]),
        [approval('SAFE')], NOW_UTC, lock=_NullLock())
    text = repr(result)
    for forbidden in ('sqlite', 'mysql', 'password', '@', 'Engine', 'Session'):
        assert forbidden not in text
