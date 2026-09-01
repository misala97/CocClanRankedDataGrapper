# personal_apps/tests/test_radar_openfigi.py
"""OpenFIGI share-class mapping: exact identities, refusal over guessing.

The automatic path (spec §5.2): unique US share class -> XGAT candidate ->
XETR fallback -> reviewed override, every step matched exactly against the
complete official reference universe. Any ambiguity stays unverified.
"""
import datetime as dt
from types import SimpleNamespace

import pytest

from features.radar.prices import PriceUnavailable
from features.radar.prices import openfigi
from features.radar import instruments as instruments_mod
from features.radar.instruments import (
    ReferenceCatalog, VenueReferenceRow, decide_mapping)


def instrument(ticker='AAPL', mic='XNAS'):
    return SimpleNamespace(ticker=ticker, market='us', mic=mic,
                           provider_symbol=ticker, currency='USD')


def us_result(ticker, share_class_figi, security_type='Common Stock'):
    return {'ticker': ticker, 'shareClassFIGI': share_class_figi,
            'securityType': security_type}


def de_result(symbol, mic, security_type='Common Stock'):
    return {'ticker': symbol, 'micCode': mic, 'securityType': security_type,
            'shareClassFIGI': 'BBG001S5N8V8'}


class FakeOpenFigi:
    """Keyed fake: ('TICKER', value, exchange) or ('SHARE', figi, mic)."""

    def __init__(self, answers, fail_with=None):
        self.answers = answers
        self.fail_with = fail_with

    def us_share_classes(self, instruments):
        if self.fail_with is not None:
            raise self.fail_with
        found = {}
        for entry in instruments:
            rows = self.answers.get(('TICKER', entry.ticker, 'US'), [])
            found[entry.ticker] = tuple(
                openfigi.ShareClass(
                    ticker=entry.ticker,
                    share_class_figi=row['shareClassFIGI'],
                    security_type=row['securityType'])
                for row in rows)
        return found

    def venue_candidates(self, share_classes, mic):
        if self.fail_with is not None:
            raise self.fail_with
        found = {}
        for ticker, share_class in share_classes.items():
            rows = self.answers.get(
                ('SHARE', share_class.share_class_figi, mic), [])
            found[ticker] = tuple(
                openfigi.VenueCandidate(
                    share_class_figi=row['shareClassFIGI'], mic=row['micCode'],
                    symbol=row['ticker'], name=None,
                    security_type=row['securityType'])
                for row in rows)
        return found


def reference(symbol, mic, isin, currency='EUR',
              security_type='common stock'):
    return VenueReferenceRow(mic=mic, isin=isin, symbol=symbol, name=None,
                             currency=currency, security_type=security_type)


def reference_catalog(mic, rows, complete=True):
    return ReferenceCatalog(mic=mic, rows=tuple(rows), complete=complete,
                            content_sha256='f' * 64)


BOTH_REFERENCES = {
    'XGAT': reference_catalog(
        'XGAT', [reference('APC', 'XGAT', 'US0378331005')]),
    'XETR': reference_catalog(
        'XETR', [reference('APC', 'XETR', 'US0378331005')]),
}


def test_share_class_maps_to_xgat_before_xetr():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): [de_result('APC', 'XETR')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert (decision.status, decision.mic, decision.symbol) == (
        'mapped', 'XGAT', 'APC')
    assert decision.isin == 'US0378331005'
    assert decision.currency == 'EUR'


def test_xgat_absence_falls_back_to_xetr():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): [de_result('APC', 'XETR')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert (decision.status, decision.mic) == ('mapped', 'XETR')


def test_no_us_share_class_refuses():
    decision = decide_mapping(instrument('AAPL'), FakeOpenFigi({}),
                              BOTH_REFERENCES, {})
    assert (decision.status, decision.reason) == (
        'unavailable', 'no_us_share_class')


def test_multiple_us_share_classes_refuse():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001'),
                                   us_result('AAPL', 'BBG002')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert decision.reason == 'ambiguous_us_share_class'


def test_unsupported_security_type_refuses():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [
            us_result('AAPL', 'BBG001S5N8V8', security_type='Warrant')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert decision.reason == 'security_type_mismatch'


def test_multiple_venue_candidates_refuse():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT'),
                                            de_result('APC2', 'XGAT')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert decision.reason == 'ambiguous_german_candidate'


def test_missing_official_reference_row_refuses():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('ZZZ', 'XGAT')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, BOTH_REFERENCES, {})
    assert decision.reason == 'official_reference_missing'


def test_wrong_reference_currency_refuses():
    references = {
        'XGAT': reference_catalog(
            'XGAT', [reference('APC', 'XGAT', 'US0378331005',
                               currency='USD')]),
        'XETR': reference_catalog('XETR', []),
    }
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT')],
    })
    decision = decide_mapping(instrument('AAPL'), provider, references, {})
    assert decision.reason == 'currency_mismatch'


def test_incomplete_reference_catalog_raises_rather_than_unavailable():
    references = {
        'XGAT': reference_catalog('XGAT', [], complete=False),
        'XETR': reference_catalog('XETR', []),
    }
    with pytest.raises(instruments_mod.IncompleteReference):
        decide_mapping(instrument('AAPL'), FakeOpenFigi({}), references, {})


def test_the_sap_adr_case_refuses_automatic_mapping():
    """SAP's US listing is a sponsored ADR whose share class does not link
    to the German ordinary share -- the reviewed override exists for exactly
    this, and loosening automatic matching would be wrong."""
    provider = FakeOpenFigi({
        ('TICKER', 'SAP', 'US'): [us_result('SAP', 'BBG001SADR11')],
        # No German venue candidates for the ADR share class.
    })
    references = {
        'XGAT': reference_catalog(
            'XGAT', [reference('SAP', 'XGAT', 'DE0007164600')]),
        'XETR': reference_catalog(
            'XETR', [reference('SAP', 'XETR', 'DE0007164600')]),
    }
    decision = decide_mapping(instrument('SAP'), provider, references, {})
    assert decision.status == 'unavailable'
    assert decision.reason == 'no_german_candidate'


def test_an_exact_override_maps_after_the_automatic_path_refuses():
    provider = FakeOpenFigi({
        ('TICKER', 'SAP', 'US'): [us_result('SAP', 'BBG001SADR11')],
    })
    references = {
        'XGAT': reference_catalog(
            'XGAT', [reference('SAP', 'XGAT', 'DE0007164600')]),
        'XETR': reference_catalog('XETR', []),
    }
    override = {'SAP': instruments_mod.Override(
        social_ticker='SAP', us_instrument_identifier='SAP:XNYS',
        german_mic='XGAT', local_mnemonic='SAP',
        german_isin='DE0007164600', currency='EUR',
        evidence_url='https://example.invalid/zz', reference_date='2026-08-31',
        reviewer='Michi', reviewed_at='2026-08-31T20:00:00Z')}
    decision = decide_mapping(instrument('SAP'), provider, references,
                              override)
    assert (decision.status, decision.mic, decision.symbol,
            decision.mapping_source) == ('mapped', 'XGAT', 'SAP', 'override')


def test_an_override_whose_reference_row_disappeared_is_invalid():
    provider = FakeOpenFigi({
        ('TICKER', 'SAP', 'US'): [us_result('SAP', 'BBG001SADR11')],
    })
    references = {
        'XGAT': reference_catalog('XGAT', []),
        'XETR': reference_catalog('XETR', []),
    }
    override = {'SAP': instruments_mod.Override(
        social_ticker='SAP', us_instrument_identifier='SAP:XNYS',
        german_mic='XGAT', local_mnemonic='SAP',
        german_isin='DE0007164600', currency='EUR',
        evidence_url='https://example.invalid/zz', reference_date='2026-08-31',
        reviewer='Michi', reviewed_at='2026-08-31T20:00:00Z')}
    decision = decide_mapping(instrument('SAP'), provider, references,
                              override)
    assert decision.reason == 'override_invalid'


# --- transport batching --------------------------------------------------

def test_unauthenticated_batches_hold_at_most_ten_jobs(monkeypatch):
    monkeypatch.delenv('OPENFIGI_API_KEY', raising=False)
    batches = []

    class FakeHttp:
        def mapping(self, jobs):
            batches.append(len(jobs))
            return [{'data': [{'ticker': job['idValue'],
                               'shareClassFIGI': 'BBG%09d' % index,
                               'securityType': 'Common Stock'}]}
                    for index, job in enumerate(jobs)]

    provider = openfigi.OpenFigiProvider(FakeHttp())
    provider.us_share_classes([instrument(f'ZZ{i}') for i in range(23)])
    assert batches == [10, 10, 3]


def test_transport_failure_aborts_the_generation_not_every_ticker():
    class FailingHttp:
        def mapping(self, jobs):
            raise PriceUnavailable('429')

    provider = openfigi.OpenFigiProvider(FailingHttp())
    with pytest.raises(PriceUnavailable):
        provider.us_share_classes([instrument('AAPL')])


def test_a_response_warning_is_an_empty_candidate_set():
    class WarningHttp:
        def mapping(self, jobs):
            return [{'warning': 'No identifier found.'}]

    provider = openfigi.OpenFigiProvider(WarningHttp())
    assert provider.us_share_classes([instrument('AAPL')]) == {'AAPL': ()}


def test_malformed_response_is_price_unavailable():
    class MalformedHttp:
        def mapping(self, jobs):
            return {'not': 'a list'}

    with pytest.raises(PriceUnavailable):
        openfigi.OpenFigiProvider(MalformedHttp()).us_share_classes(
            [instrument('AAPL')])
