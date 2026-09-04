"""The ECB adapter: one parser, and a refusal for everything it cannot read.

The daily file is 1.5 KB and the history file is 8 MB of the same shape, so
there is exactly one parser and the only difference is which URL fetched it.
"""
import datetime as dt
import decimal

import pytest

from features.radar.prices import PriceUnavailable
from features.radar.prices import ecb

DAILY = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time='2026-09-03'>
      <Cube currency='USD' rate='1.1615'/>
      <Cube currency='JPY' rate='171.02'/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""

HIST = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time='2026-09-03'><Cube currency='USD' rate='1.1615'/></Cube>
    <Cube time='2026-09-02'><Cube currency='USD' rate='1.1600'/></Cube>
    <Cube time='2026-09-01'><Cube currency='JPY' rate='171.02'/></Cube>
  </Cube>
</gesmes:Envelope>"""


class FakeHttp:
    def __init__(self, daily=DAILY, history=HIST):
        self._daily = daily
        self._history = history
        self.asked = []

    def get_daily(self):
        self.asked.append('daily')
        return self._daily

    def get_history(self):
        self.asked.append('history')
        return self._history


def test_parses_the_daily_file():
    assert ecb.parse_rates(DAILY) == [
        (dt.date(2026, 9, 3), decimal.Decimal('1.1615'))]


def test_parses_every_day_of_the_history_file():
    assert ecb.parse_rates(HIST) == [
        (dt.date(2026, 9, 3), decimal.Decimal('1.1615')),
        (dt.date(2026, 9, 2), decimal.Decimal('1.1600'))]


def test_a_day_without_the_pair_is_absent_not_zero():
    days = [day for day, _ in ecb.parse_rates(HIST)]
    assert dt.date(2026, 9, 1) not in days


def test_malformed_xml_is_unavailable_not_empty():
    with pytest.raises(PriceUnavailable):
        ecb.parse_rates(b'<not-xml')


def test_provider_reads_the_daily_file_by_default():
    http = FakeHttp()
    rates = ecb.EcbProvider(http).rates()
    assert http.asked == ['daily']
    assert rates == [(dt.date(2026, 9, 3), decimal.Decimal('1.1615'))]


def test_provider_reads_the_history_file_when_asked():
    http = FakeHttp()
    rates = ecb.EcbProvider(http).rates(historical=True)
    assert http.asked == ['history']
    assert len(rates) == 2


def test_provider_source_is_ecb():
    assert ecb.EcbProvider(FakeHttp()).source == 'ecb'
