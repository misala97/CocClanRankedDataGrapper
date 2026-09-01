"""Verified Xetra mapping uses provider catalog identifiers, never names."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from features.radar.prices import PriceUnavailable


PREFIX = 'T4MAP'
NOW = dt.datetime(2026, 8, 28, 12, 0)
APPLE_ISIN = 'US0378331005'


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        return self.payload


class CatalogProvider:
    """A complete in-memory provider boundary; it cannot make HTTP requests."""
    def __init__(self, rows_by_mic):
        self.rows_by_mic = rows_by_mic

    def stock_catalog(self, mic_code):
        rows = self.rows_by_mic[mic_code]
        if isinstance(rows, Exception):
            raise rows
        return rows


@pytest.fixture()
def mapping_rows():
    from models import RadarInstrument, TickerUniverse

    def clean():
        RadarInstrument.query.filter(
            RadarInstrument.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        clean()
        yield
        clean()


def catalog(symbol, mic, currency, isin, *, name='Example Inc', figi=None):
    from features.radar.instruments import CatalogInstrument
    return CatalogInstrument(symbol=symbol, name=name, mic=mic,
                             currency=currency, isin=isin, figi=figi)


def test_twelve_data_catalog_keeps_stable_identity_fields():
    """Dropping ISIN/FIGI would make a later mapping use unsafe name matching."""
    from features.radar.prices.twelvedata import TwelveDataProvider

    http = FakeHttp({'data': [{
        # Twelve Data names the FIGI field figi_code in its /stocks response.
        'symbol': 'APC', 'name': 'Apple Inc', 'mic_code': 'XETR',
        'currency': 'EUR', 'isin': APPLE_ISIN, 'figi_code': 'BBG000B9XRY4',
        'type': 'Common Stock',
    }], 'meta': {'total_count': 1}})

    rows = TwelveDataProvider(http).stock_catalog('XETR')

    assert rows == [catalog('APC', 'XETR', 'EUR', APPLE_ISIN,
                            name='Apple Inc', figi='BBG000B9XRY4')]
    assert http.calls == [('/stocks', {'mic_code': 'XETR', 'show_plan': 'true',
                                       'offset': 0})]


def test_twelve_data_catalog_reads_every_page_declared_by_total_count():
    """Stopping after page one can turn an unreturned ISIN into unavailable."""
    from features.radar.prices.twelvedata import TwelveDataProvider

    class PagedHttp:
        def __init__(self):
            self.calls = []

        def get(self, path, params):
            self.calls.append((path, dict(params)))
            if params['offset'] == 0:
                return {'data': [{
                    'symbol': 'FIRST', 'name': 'First', 'mic_code': 'XETR',
                    'currency': 'EUR', 'isin': 'DE0000000001',
                    'type': 'Common Stock',
                }], 'meta': {'total_count': 2}}
            if params['offset'] == 1:
                return {'data': [{
                    'symbol': 'APC', 'name': 'Apple Inc', 'mic_code': 'XETR',
                    'currency': 'EUR', 'isin': APPLE_ISIN,
                    'type': 'Common Stock',
                }], 'meta': {'total_count': 2}}
            raise AssertionError('unexpected page')

    http = PagedHttp()

    assert TwelveDataProvider(http).stock_catalog('XETR') == [
        catalog('FIRST', 'XETR', 'EUR', 'DE0000000001', name='First'),
        catalog('APC', 'XETR', 'EUR', APPLE_ISIN, name='Apple Inc'),
    ]
    assert [call[1]['offset'] for call in http.calls] == [0, 1]


def test_finnhub_catalog_rejects_rows_without_a_recognized_instrument_type():
    """An untyped directory row is not evidence that it is an eligible stock."""
    from features.radar.prices.finnhub import FinnhubProvider

    rows = FinnhubProvider(FakeHttp([{
        'symbol': 'APC', 'description': 'Apple Inc', 'mic': 'XETR',
        'currency': 'EUR', 'isin': APPLE_ISIN,
    }])).stock_catalog('XETR')

    assert rows == []


def test_mapping_joins_same_isin_and_prefers_xetra():
    """Choosing the Frankfurt duplicate would violate the Xetra venue contract."""
    from features.radar.instruments import map_xetra

    result = map_xetra([catalog('AAPL', 'XNAS', 'USD', APPLE_ISIN)], [
        catalog('APC', 'XFRA', 'EUR', APPLE_ISIN),
        catalog('APC', 'XETR', 'EUR', APPLE_ISIN),
    ])

    assert result == {'AAPL': catalog('APC', 'XETR', 'EUR', APPLE_ISIN)}


def test_mapping_does_not_guess_from_company_name():
    """A same-name listing without a stable identifier must never be mapped."""
    from features.radar.instruments import map_xetra

    assert map_xetra([
        catalog('AAA', 'XNAS', 'USD', None, name='Same Name Ltd'),
    ], [
        catalog('AAA', 'XETR', 'EUR', None, name='Same Name Ltd'),
    ]) == {}


def test_mapping_rejects_ambiguous_xetra_isin():
    """Picking one of two Xetra candidates would turn an ambiguity into a lie."""
    from features.radar.instruments import map_xetra

    assert map_xetra([catalog('AAPL', 'XNAS', 'USD', APPLE_ISIN)], [
        catalog('APC', 'XETR', 'EUR', APPLE_ISIN),
        catalog('APC2', 'XETR', 'EUR', APPLE_ISIN),
    ]) == {}


def test_catalog_fallback_enriches_the_same_listing_with_finnhub_isin():
    """A missing Twelve Data entitlement must not force a name-based join."""
    from features.radar.instruments import CatalogFallbackProvider

    twelve = CatalogProvider({
        'XETR': [catalog('APC', 'XETR', 'EUR', None,
                          figi='BBG000B9XRY4')],
    })
    finnhub = CatalogProvider({
        'XETR': [catalog('APC', 'XETR', 'EUR', APPLE_ISIN,
                          figi='BBG000B9XRY4')],
    })

    assert CatalogFallbackProvider(twelve, finnhub).stock_catalog('XETR') == [
        catalog('APC', 'XETR', 'EUR', APPLE_ISIN, figi='BBG000B9XRY4')]


def test_refresh_persists_one_primary_xetra_mapping(mapping_rows, monkeypatch):
    """Leaving a previous German primary enabled would make quote choice unstable."""
    from features.radar import instruments
    from models import RadarInstrument, TickerUniverse

    ticker = f'{PREFIX}A'
    with flask_app.app_context():
        db.session.add(TickerUniverse(
            symbol=ticker, name='Apple-like', exchange='Q',
            first_seen=NOW))
        us = RadarInstrument(
            ticker=ticker, market='us', venue='Nasdaq', mic='XNAS',
            provider_symbol=ticker, currency='USD', is_primary=True,
            mapping_status='mapped', mapped_at=NOW)
        db.session.add(us)
        db.session.add(RadarInstrument(
            ticker=ticker, market='de', venue='Frankfurt', mic='XFRA',
            provider_symbol='OLD', currency='EUR', isin=APPLE_ISIN,
            is_primary=True, mapping_status='mapped', mapped_at=NOW))
        db.session.commit()
        monkeypatch.setattr(instruments, '_active_us_instruments', lambda: [us])

        result = instruments.refresh_mappings(CatalogProvider({
            'XNAS': [catalog(ticker, 'XNAS', 'USD', APPLE_ISIN)],
            'XETR': [catalog('APC', 'XETR', 'EUR', APPLE_ISIN)],
        }), NOW)

        assert (result.catalog_reachable, result.mapped_active_tickers) == (True, 1)
        mapped = RadarInstrument.query.filter_by(
            ticker=ticker, market='de', mic='XETR').one()
        old = RadarInstrument.query.filter_by(
            ticker=ticker, market='de', mic='XFRA').one()
        assert (mapped.provider_symbol, mapped.is_primary,
                mapped.mapping_status, mapped.mapping_source) == (
                    'APC', True, 'mapped', 'catalog')
        assert old.is_primary is False


def test_refresh_marks_unmatched_active_ticker_unavailable_only_after_success(
        mapping_rows, monkeypatch):
    """An absent stable join after a complete catalog read is durable information."""
    from features.radar import instruments
    from models import RadarInstrument, TickerUniverse

    ticker = f'{PREFIX}B'
    with flask_app.app_context():
        db.session.add(TickerUniverse(
            symbol=ticker, name='No German listing', exchange='Q',
            first_seen=NOW))
        us = RadarInstrument(
            ticker=ticker, market='us', venue='Nasdaq', mic='XNAS',
            provider_symbol=ticker, currency='USD', is_primary=True,
            mapping_status='mapped', mapped_at=NOW)
        db.session.add(us)
        db.session.commit()
        monkeypatch.setattr(instruments, '_active_us_instruments', lambda: [us])

        result = instruments.refresh_mappings(CatalogProvider({
            'XNAS': [catalog(ticker, 'XNAS', 'USD', APPLE_ISIN)],
            'XETR': [],
        }), NOW)

        stored = RadarInstrument.query.filter_by(
            ticker=ticker, market='de', mic='XETR').one()
        assert (result.unavailable_active_tickers, stored.mapping_status,
                stored.is_primary) == (1, 'unavailable', False)


def test_refresh_preserves_existing_mapping_when_catalog_transport_fails(
        mapping_rows, monkeypatch):
    """A timeout is not evidence that a verified German listing disappeared."""
    from features.radar import instruments
    from models import RadarInstrument, TickerUniverse

    ticker = f'{PREFIX}C'
    with flask_app.app_context():
        db.session.add(TickerUniverse(
            symbol=ticker, name='Previously mapped', exchange='Q',
            first_seen=NOW))
        us = RadarInstrument(
                ticker=ticker, market='us', venue='Nasdaq', mic='XNAS',
                provider_symbol=ticker, currency='USD', is_primary=True,
                mapping_status='mapped', mapped_at=NOW)
        db.session.add_all([
            us,
            RadarInstrument(
                ticker=ticker, market='de', venue='Xetra', mic='XETR',
                provider_symbol='APC', currency='EUR', isin=APPLE_ISIN,
                is_primary=True, mapping_status='mapped', mapping_source='catalog',
                mapped_at=NOW),
        ])
        db.session.commit()
        monkeypatch.setattr(instruments, '_active_us_instruments', lambda: [us])

        result = instruments.refresh_mappings(CatalogProvider({
            'XNAS': PriceUnavailable('catalog timeout'),
            'XETR': [],
        }), NOW + dt.timedelta(days=7))

        stored = RadarInstrument.query.filter_by(
            ticker=ticker, market='de', mic='XETR').one()
        assert result.catalog_reachable is False
        assert (stored.provider_symbol, stored.mapping_status,
                stored.mapped_at) == ('APC', 'mapped', NOW)


def test_german_probe_reports_counts_without_provider_payload_or_key(
        monkeypatch, capsys):
    """A diagnostic that echoes credentials or catalog rows turns support into leakage."""
    import run_radar_ingest as daemon
    from features.radar.instruments import MappingResult

    class NoNetworkProvider:
        api_key = 'private-key-must-not-print'

        def stock_catalog(self, mic_code):
            raise AssertionError(f'network attempted for {mic_code}')

    monkeypatch.setattr(daemon.instruments, 'mapping_preview', lambda provider:
                        MappingResult(True, 42, 17, 3, 9))
    monkeypatch.setattr(daemon, '_german_quote_sample',
                        lambda now: (120, 'delayed'))

    result = daemon.probe_german_data(NoNetworkProvider(), NOW)
    output = capsys.readouterr().out

    assert result == MappingResult(True, 42, 17, 3, 9)
    assert 'xetra_rows=42' in output
    assert 'quote_sample_age_seconds=120' in output
    assert 'private-key-must-not-print' not in output


# --- Market data v2: versioned generations (plan Task 6) ---------------------

def _decision(ticker, status='mapped', mic='XGAT', symbol=None,
              isin=None, reason=None, source='openfigi'):
    from features.radar.instruments import MappingDecision
    return MappingDecision(
        ticker=ticker, status=status, reason=reason,
        mic=mic if status == 'mapped' else None,
        symbol=(symbol or ticker + 'D') if status == 'mapped' else None,
        isin=(isin or 'US00000%05d' % abs(hash(ticker)) % 100000)
        if status == 'mapped' else None,
        currency='EUR' if status == 'mapped' else None,
        mapping_source=source)


@pytest.fixture()
def generation_rows(mapping_rows):
    from models import RadarMappingGeneration
    from models import RadarInstrument

    def clean():
        RadarInstrument.query.filter(
            RadarInstrument.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        generations = RadarMappingGeneration.query.all()
        for generation in generations:
            if f'{PREFIX}' in generation.payload_json:
                db.session.delete(generation)
        db.session.commit()

    clean()
    yield
    clean()


def test_identical_payload_returns_the_existing_generation(generation_rows):
    from features.radar import instruments as mod
    now = dt.datetime(2027, 1, 4, 12, 0)
    decisions = [_decision(f'{PREFIX}AA', isin='US0000000017')]
    first = mod.persist_generation(decisions, now)
    second = mod.persist_generation(decisions, now + dt.timedelta(hours=1))
    assert first.id == second.id
    assert first.status == 'shadow'


def test_activation_upserts_primaries_and_retires_the_previous_generation(
        generation_rows):
    from features.radar import instruments as mod
    from models import RadarInstrument, RadarMappingGeneration
    now = dt.datetime(2027, 1, 4, 12, 0)
    ticker = f'{PREFIX}AA'
    db.session.add(RadarInstrument(
        ticker=ticker, market='de', venue='Xetra', mic='XETR',
        provider_symbol='OLD', currency='EUR', is_primary=True,
        mapping_status='mapped', mapping_source='twelvedata+finnhub',
        mapped_at=now - dt.timedelta(days=30)))
    db.session.commit()

    generation = mod.persist_generation(
        [_decision(ticker, mic='XGAT', symbol='ZZAPC',
                   isin='US0000000017')], now)
    changed = mod.activate_generation(generation.id, now)
    assert changed >= 1

    rows = {row.mic: row for row in RadarInstrument.query.filter_by(
        ticker=ticker, market='de')}
    assert rows['XGAT'].is_primary is True
    assert rows['XGAT'].provider_symbol == 'ZZAPC'
    assert rows['XGAT'].venue == 'Tradegate BSX'
    assert rows['XGAT'].mapping_generation_id == generation.id
    assert rows['XETR'].is_primary is False
    active = RadarMappingGeneration.query.get(generation.id)
    assert active.status == 'active'
    assert active.activated_at is not None
    # The pre-activation state was snapshotted for rollback.
    legacy = RadarMappingGeneration.query.filter_by(source='legacy').all()
    assert any(ticker in generation.payload_json
               for generation in legacy)


def test_rollback_restores_the_previous_primary(generation_rows):
    from features.radar import instruments as mod
    from models import RadarInstrument
    now = dt.datetime(2027, 1, 4, 12, 0)
    ticker = f'{PREFIX}AB'
    db.session.add(RadarInstrument(
        ticker=ticker, market='de', venue='Xetra', mic='XETR',
        provider_symbol='OLDSYM', currency='EUR', is_primary=True,
        mapping_status='mapped', mapping_source='twelvedata+finnhub',
        isin='DE000ZZTST09', mapped_at=now - dt.timedelta(days=30)))
    db.session.commit()

    generation = mod.persist_generation(
        [_decision(ticker, mic='XGAT', symbol='ZZAPB',
                   isin='DE000ZZTST09')], now)
    mod.activate_generation(generation.id, now)
    from models import RadarMappingGeneration
    legacy = next(g for g in RadarMappingGeneration.query.filter_by(
        source='legacy') if ticker in g.payload_json)

    mod.rollback_generation(legacy.id, now + dt.timedelta(hours=1))
    rows = {row.mic: row for row in RadarInstrument.query.filter_by(
        ticker=ticker, market='de')}
    assert rows['XETR'].is_primary is True
    assert rows['XGAT'].is_primary is False


def test_a_failed_activation_leaves_the_previous_state_untouched(
        generation_rows, monkeypatch):
    from features.radar import instruments as mod
    from models import RadarInstrument, RadarMappingGeneration
    now = dt.datetime(2027, 1, 4, 12, 0)
    ticker = f'{PREFIX}AC'
    db.session.add(RadarInstrument(
        ticker=ticker, market='de', venue='Xetra', mic='XETR',
        provider_symbol='KEEP', currency='EUR', is_primary=True,
        mapping_status='mapped', mapping_source='twelvedata+finnhub',
        mapped_at=now - dt.timedelta(days=30)))
    db.session.commit()

    generation = mod.persist_generation(
        [_decision(ticker, mic='XGAT', symbol='ZZAPX',
                   isin='US0000000018'),
         _decision(f'{PREFIX}AD', mic='XGAT', symbol='ZZAPY',
                   isin='US0000000019')], now)

    original = mod._apply_decision
    calls = {'n': 0}

    def exploding(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 2:
            raise RuntimeError('forced mid-transaction failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(mod, '_apply_decision', exploding)
    with pytest.raises(RuntimeError):
        mod.activate_generation(generation.id, now)

    row = RadarInstrument.query.filter_by(
        ticker=ticker, market='de', mic='XETR').one()
    assert row.is_primary is True
    assert row.provider_symbol == 'KEEP'
    assert RadarMappingGeneration.query.get(generation.id).status == 'shadow'


def test_override_file_loads_strictly():
    from features.radar import instruments as mod
    overrides = mod.load_overrides()
    assert overrides == {}

    with pytest.raises(ValueError):
        mod.parse_overrides({'version': 1, 'overrides': [
            {'social_ticker': 'SAP'}]})  # missing required keys
    with pytest.raises(ValueError):
        mod.parse_overrides({'version': 1, 'overrides': [
            _override_entry(), _override_entry()]})  # duplicate ticker
    with pytest.raises(ValueError):
        stale = _override_entry()
        stale['reviewed_at'] = '2020-01-01T00:00:00Z'
        mod.parse_overrides({'version': 1, 'overrides': [stale]},
                            now=dt.datetime(2027, 1, 4))


def _override_entry():
    return {
        'social_ticker': 'SAP',
        'us_instrument_identifier': 'SAP:XNYS',
        'german_mic': 'XGAT',
        'local_mnemonic': 'SAP',
        'german_isin': 'DE0007164600',
        'currency': 'EUR',
        'evidence_url': 'https://example.invalid/evidence',
        'reference_date': '2026-08-31',
        'reviewer': 'Michi',
        'reviewed_at': '2026-08-31T20:00:00Z',
    }
