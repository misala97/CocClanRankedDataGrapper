"""One-time: remove an account that has no training history.

    python scripts/delete_user.py <username>
    python scripts/delete_user.py <username> --commit

Without --commit it only reports what it would remove. Nothing is written.

Written for the per-user-exercises rollout, where an account created with
nothing in it is deleted so the migration runs against a single-user database
and never has to duplicate an exercise or repoint a live foreign key.

It refuses a user with any logged session. That guard is the point: it
separates removing an empty placeholder from silently destroying a training
history because a username was mistyped. Deleting someone who has actually
trained is a deliberate act and can be a deliberate SQL statement.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (needs the path insert above)
from extensions import db  # noqa: E402
from models import AppUser, Exercise, PushSubscription, WorkoutSession, WorkoutTemplate  # noqa: E402


def delete_user(username, commit):
    """Remove `username`. Returns the report lines. Exits on a refusal."""
    user = AppUser.query.filter_by(username=username).first()
    if user is None:
        existing = ', '.join(u.username for u in AppUser.query.order_by(AppUser.username))
        sys.exit(f'no user named {username!r}. Accounts that exist: {existing}')

    sessions = WorkoutSession.query.filter_by(user_id=user.id).count()
    if sessions:
        sys.exit(f'{username} has {sessions} logged session(s) — refusing. This script is '
                 f'only for accounts with no training history.')

    templates = WorkoutTemplate.query.filter_by(user_id=user.id).all()
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    exercises = Exercise.query.filter_by(user_id=user.id).all()

    lines = [f'{username} (id {user.id})',
             f'  {len(templates)} template(s)',
             f'  {len(subscriptions)} push subscription(s)',
             f'  {len(exercises)} exercise(s)',
             '  0 sessions']
    for line in lines:
        print(line)

    if commit:
        # Templates first: their TemplateExercise rows cascade with them, and
        # those rows are what reference the exercises below. Deleting an
        # exercise while a template still points at it would hit the same
        # class of foreign-key violation this ordering exists to avoid.
        # Exercises next, since the catalogue became per-user: the user row
        # cannot go while anything -- template, subscription, or now
        # exercise -- still references it.
        for template in templates:
            db.session.delete(template)
        for subscription in subscriptions:
            db.session.delete(subscription)
        for exercise in exercises:
            db.session.delete(exercise)
        db.session.flush()
        db.session.delete(user)
        db.session.commit()
        print('\ndeleted.')
    else:
        print('\ndry run — nothing written. Re-run with --commit to do it.')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username', help='the account to remove')
    parser.add_argument('--commit', action='store_true',
                        help='actually delete; without it this is a dry run')
    args = parser.parse_args()
    with app.app_context():
        delete_user(args.username, args.commit)


if __name__ == '__main__':
    main()
