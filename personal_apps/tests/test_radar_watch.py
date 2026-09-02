"""What one account is watching: per account, idempotent, shape-checked."""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from models import AppUser, RadarWatch
from features.radar import watch


@pytest.fixture()
def two_users():
    """Two throwaway accounts. Rows they write are deleted with them (FK
    cascade), so the fixture only has to delete the users."""
    with flask_app.app_context():
        for name in ('pytest watcher a', 'pytest watcher b'):
            AppUser.query.filter_by(username=name).delete()
        db.session.commit()
        a = AppUser(username='pytest watcher a', password_hash='x')
        b = AppUser(username='pytest watcher b', password_hash='x')
        db.session.add_all([a, b])
        db.session.commit()
        yield a.id, b.id
        for name in ('pytest watcher a', 'pytest watcher b'):
            AppUser.query.filter_by(username=name).delete()
        db.session.commit()


def test_marks_are_per_account(two_users):
    a, b = two_users
    with flask_app.app_context():
        watch.add(a, 'nvda')
        watch.add(b, 'TSLA')

        assert watch.tickers_for(a) == ['NVDA']
        assert watch.tickers_for(b) == ['TSLA']


def test_add_is_idempotent_and_keeps_first_seen_order(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'TSLA', now=dt.datetime(2026, 9, 2, 10, 0))
        watch.add(a, 'NVDA', now=dt.datetime(2026, 9, 2, 10, 1))
        watch.add(a, 'TSLA', now=dt.datetime(2026, 9, 2, 10, 2))

        assert watch.tickers_for(a) == ['TSLA', 'NVDA']
        assert RadarWatch.query.filter_by(user_id=a).count() == 2


def test_marks_made_in_the_same_instant_keep_insertion_order(two_users):
    a, _ = two_users
    same = dt.datetime(2026, 9, 2, 10, 0)
    with flask_app.app_context():
        for ticker in ('TSLA', 'NVDA', 'AMD'):
            watch.add(a, ticker, now=same)

        assert watch.tickers_for(a) == ['TSLA', 'NVDA', 'AMD']


def test_remove_of_an_unwatched_ticker_is_not_an_error(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'NVDA')

        assert watch.remove(a, 'TSLA') == ['NVDA']
        assert watch.remove(a, 'NVDA') == []


def test_a_malformed_ticker_is_refused(two_users):
    a, _ = two_users
    with flask_app.app_context():
        for bad in ('', '1ABC', 'TOO-LONG-TICKER', 'a b', 'NV;DA'):
            with pytest.raises(watch.BadTicker):
                watch.add(a, bad)
            with pytest.raises(watch.BadTicker):
                watch.remove(a, bad)
        assert watch.tickers_for(a) == []


def test_deleting_the_account_deletes_its_marks(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'NVDA')
        AppUser.query.filter_by(id=a).delete()
        db.session.commit()

        assert RadarWatch.query.filter_by(user_id=a).count() == 0


def test_a_mark_for_an_account_that_does_not_exist_is_an_error(two_users):
    """The duplicate race is forgiven; nothing else is. An account id with
    no row behind it fails the foreign key, and that must surface -- not
    come back as an empty list."""
    a, _ = two_users
    with flask_app.app_context():
        nobody = db.session.query(sa.func.max(AppUser.id)).scalar() + 1000
        with pytest.raises(sa.exc.IntegrityError):
            watch.add(nobody, 'NVDA')
        # The session is usable afterwards, and nothing leaked in.
        assert watch.tickers_for(a) == []
        assert RadarWatch.query.filter_by(user_id=nobody).count() == 0
