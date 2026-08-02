"""Ownership of gym data.

The IDOR table test at the bottom of this file is the durable guarantee that
no gym route leaks another user's data: it loops over every route that takes an
object id, so a new unscoped route fails the moment it is added.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import pytest

from app import app as flask_app


def test_the_three_roots_carry_an_owner():
    from models import PushSubscription, WorkoutSession, WorkoutTemplate
    for model in (WorkoutSession, WorkoutTemplate, PushSubscription):
        assert hasattr(model, 'user_id'), f'{model.__name__} has no user_id'
        # __table__.c, not the mapped attribute: an InstrumentedAttribute has
        # no .nullable of its own.
        assert model.__table__.c.user_id.nullable is False, \
            f'{model.__name__}.user_id must be NOT NULL'


def test_every_pre_existing_row_was_backfilled_to_the_admin():
    """Rows created by this suite's own fixtures are excluded by name -- they
    are deliberately owned by throwaway users, and this assertion is about what
    the migration did to the data that already existed."""
    import sqlalchemy as sa
    from models import AppUser, WorkoutSession, WorkoutTemplate
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None
        for model in (WorkoutSession, WorkoutTemplate):
            orphans = model.query.filter(
                model.user_id != admin.id,
                # WorkoutSession.name is nullable, and NOT LIKE is NULL (not
                # true) for a NULL -- without the is_(None) arm an unnamed row
                # owned by someone else would slip past this check.
                sa.or_(model.name.is_(None), model.name.notlike('pytest%')),
            ).count()
            assert orphans == 0, f'{model.__name__} has rows not owned by the admin'
