"""The set of symbols extraction is allowed to match.

Seeded from a symbol listing and refreshed weekly. The interesting logic is
reassignment: a symbol that was delisted and later reappears under a different
company name is a different instrument, and continuing its baseline would make
every subsequent spike wrong with nothing to show for it in the logs.
"""
from extensions import db
from models import TickerUniverse


def _significant(name):
    """A comparable form of a company name.

    Legal-form suffixes are dropped so 'Acme Inc' and 'Acme Holdings Inc' can
    be recognized as the same company renaming itself rather than a new one.
    """
    if not name:
        return ''
    noise = {'inc', 'inc.', 'corp', 'corp.', 'corporation', 'co', 'co.',
             'ltd', 'ltd.', 'limited', 'plc', 'holdings', 'group', 'the',
             'company', 'sa', 'ag', 'nv'}
    words = [w for w in name.lower().replace(',', ' ').split() if w not in noise]
    return ' '.join(words)


def _is_reassignment(row, incoming_name):
    """A different company on a symbol that had been delisted.

    Both halves are required. A name change while listed is a rename; a
    delisting followed by the same name returning is a relisting.
    """
    if row.delisted_at is None:
        return False
    old = _significant(row.name)
    new = _significant(incoming_name)
    if not old or not new:
        return False
    return old.split()[:1] != new.split()[:1]


def upsert_symbols(rows, now):
    """Add or refresh universe rows. Returns counts of what happened."""
    counts = {'added': 0, 'updated': 0, 'reassigned': 0}

    for row in rows:
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol:
            continue
        name = row.get('name')
        exchange = row.get('exchange')

        existing = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if existing is None:
            db.session.add(TickerUniverse(symbol=symbol, name=name,
                                          exchange=exchange, first_seen=now))
            counts['added'] += 1
            continue

        if _is_reassignment(existing, name):
            existing.first_seen = now
            existing.delisted_at = None
            counts['reassigned'] += 1
        elif existing.delisted_at is not None:
            existing.delisted_at = None

        if existing.name != name or existing.exchange != exchange:
            counts['updated'] += 1
        existing.name = name
        existing.exchange = exchange

    db.session.commit()
    return counts


def mark_delisted(symbols, now):
    """Stamp delisted_at. The rows stay -- a delisted ticker still gets
    talked about, and dropping it would turn those mentions into silent
    misses rather than into recorded ones."""
    marked = 0
    for symbol in symbols:
        row = TickerUniverse.query.filter_by(
            symbol=symbol.strip().upper()).one_or_none()
        if row is not None and row.delisted_at is None:
            row.delisted_at = now
            marked += 1
    db.session.commit()
    return marked


def load_lookup():
    """Every symbol, keyed uppercase. Extraction uppercases candidates before
    it gets here -- the column is utf8mb4_bin and will not do it for us."""
    return {
        row.symbol: {'name': row.name, 'exchange': row.exchange}
        for row in TickerUniverse.query.all()
    }
