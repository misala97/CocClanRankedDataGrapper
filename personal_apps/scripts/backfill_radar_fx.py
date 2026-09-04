# personal_apps/scripts/backfill_radar_fx.py
"""Load the ECB's full euro reference-rate history into radar_fx_rates.

One request, about 8 MB, roughly 7000 business days back to 1999. Run once
after the migration; the daily job keeps it current from then on.

    python scripts/backfill_radar_fx.py
"""
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                      # noqa: E402
from features.radar import fx            # noqa: E402
from features.radar.prices import ecb    # noqa: E402


def main():
    provider = ecb.EcbProvider(ecb.EcbHttp())
    rates = provider.rates(historical=True)
    if not rates:
        print('ecb returned no rates -- nothing written')
        return 1
    with app.app_context():
        written = fx.record_rates(rates, dt.datetime.utcnow())
    oldest = min(day for day, _ in rates)
    newest = max(day for day, _ in rates)
    print(f'radar fx backfill: {written} rates, {oldest} .. {newest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
