# personal_apps/features/radar/prices/openfigi.py
"""The one module that knows OpenFIGI's mapping JSON.

Share-class linkage is the ONLY automatic bridge between a US listing and a
German venue listing (spec §5.2): exact US ticker+exchange to one unique
share class, then that share-class FIGI to venue candidates on XGAT/XETR.
Company-name search is never a mapping source.

A transport failure, 429, or malformed response raises PriceUnavailable and
aborts the WHOLE generation build -- turning every ticker 'unavailable'
because the provider was down would erase verified mappings, which spec
§5.4 forbids.
"""
import dataclasses
import os
import threading
import time

import requests

from . import PriceUnavailable

API_URL = 'https://api.openfigi.com/v3/mapping'

# Without a key: at most ten jobs per request, 25 requests per minute.
# An optional key raises the batch size; it is never required.
UNKEYED_BATCH = 10
KEYED_BATCH = 100
REQUESTS_PER_MINUTE = 25

# The only security types the mapping may produce (spec §5.2 step 1).
SUPPORTED_TYPES = frozenset({
    'common stock', 'common shares', 'etf', 'exchange traded fund',
    'exchange-traded fund', 'etp',
})


@dataclasses.dataclass(frozen=True)
class ShareClass:
    ticker: str
    share_class_figi: str
    security_type: str


@dataclasses.dataclass(frozen=True)
class VenueCandidate:
    share_class_figi: str
    mic: str
    symbol: str
    name: str | None
    security_type: str


def is_supported_type(security_type):
    return (security_type or '').strip().casefold() in SUPPORTED_TYPES


class OpenFigiHttp:
    """POST /v3/mapping with pacing; the key is optional and never logged."""

    def __init__(self, timeout=(3.05, 20), clock=time.monotonic,
                 sleep=time.sleep):
        self._session = requests.Session()
        self._timeout = timeout
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._recent = []

    def mapping(self, jobs):
        with self._lock:
            now = self._clock()
            self._recent = [stamp for stamp in self._recent
                            if now - stamp < 60]
            if len(self._recent) >= REQUESTS_PER_MINUTE:
                wait = 60 - (now - self._recent[0])
                if wait > 0:
                    self._sleep(wait)
            self._recent.append(self._clock())

        headers = {'Content-Type': 'application/json'}
        key = os.getenv('OPENFIGI_API_KEY')
        if key:
            headers['X-OPENFIGI-APIKEY'] = key
        try:
            response = self._session.post(
                API_URL, json=jobs, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f'openfigi mapping: {exc}') from exc
        return payload


class OpenFigiProvider:
    def __init__(self, http):
        self._http = http

    def _batch_size(self):
        return KEYED_BATCH if os.getenv('OPENFIGI_API_KEY') else UNKEYED_BATCH

    def _mapped(self, jobs):
        """One result list per job, in order; anything else is a failure."""
        results = []
        size = self._batch_size()
        for start in range(0, len(jobs), size):
            batch = jobs[start:start + size]
            payload = self._http.mapping(batch)
            if not isinstance(payload, list) or len(payload) != len(batch):
                raise PriceUnavailable(
                    'openfigi mapping: response shape does not match jobs')
            results.extend(payload)
        return results

    def us_share_classes(self, instruments):
        """Every normalized share-class candidate per US ticker.

        A response warning ('No identifier found.') is an EMPTY candidate
        set -- a fact about the ticker. Transport problems raise instead.
        """
        instruments = list(instruments)
        jobs = [{'idType': 'TICKER', 'idValue': entry.ticker,
                 'exchCode': 'US'} for entry in instruments]
        results = self._mapped(jobs)
        found = {}
        for entry, result in zip(instruments, results):
            candidates = []
            if isinstance(result, dict):
                for row in result.get('data') or []:
                    if not isinstance(row, dict):
                        continue
                    figi = row.get('shareClassFIGI')
                    if not figi:
                        continue
                    candidates.append(ShareClass(
                        ticker=entry.ticker, share_class_figi=figi,
                        security_type=row.get('securityType') or ''))
            # Distinct share classes only: multiple LISTINGS of one class
            # are one identity, not an ambiguity.
            unique = {}
            for candidate in candidates:
                unique.setdefault(candidate.share_class_figi, candidate)
            found[entry.ticker] = tuple(unique.values())
        return found

    def venue_candidates(self, share_classes, mic):
        """Venue candidates per ticker for one German MIC, EUR only."""
        items = list(share_classes.items())
        jobs = [{'idType': 'ID_BB_GLOBAL_SHARE_CLASS_LEVEL',
                 'idValue': share_class.share_class_figi,
                 'micCode': mic, 'currency': 'EUR'}
                for _, share_class in items]
        results = self._mapped(jobs)
        found = {}
        for (ticker, share_class), result in zip(items, results):
            candidates = []
            if isinstance(result, dict):
                for row in result.get('data') or []:
                    if not isinstance(row, dict):
                        continue
                    symbol = row.get('ticker')
                    if not symbol:
                        continue
                    candidates.append(VenueCandidate(
                        share_class_figi=share_class.share_class_figi,
                        mic=row.get('micCode') or mic, symbol=symbol,
                        name=row.get('name'),
                        security_type=row.get('securityType') or ''))
            found[ticker] = tuple(candidates)
        return found
