"""One-time: copy one user's workout templates to another user.

Written for the multi-user rollout, where the author's training partner starts
with an empty account and wants the split they already train together. Run it
once, after creating his account.

    python scripts/copy_templates.py <from-username> <to-username>
    python scripts/copy_templates.py michi buddy --commit

Without --commit it only reports what it would do. Nothing is written.

Why a script and not two INSERT ... SELECT statements: pairing source rows to
their new copies in SQL means joining on `name`, and WorkoutTemplate.name is
not unique -- two templates called "Push" would cross-join and silently give
the destination duplicated exercise rows. Carrying each new id in a variable
avoids the question entirely.

The exercise catalogue is per user, so each referenced exercise is recreated in
the destination's own catalogue and the new template rows point at those copies.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (needs the path insert above)
from extensions import db  # noqa: E402
from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate  # noqa: E402


def _user(username):
    user = AppUser.query.filter_by(username=username).first()
    if user is None:
        existing = ', '.join(u.username for u in AppUser.query.order_by(AppUser.username))
        sys.exit(f"no user named {username!r}. Accounts that exist: {existing}")
    return user


def copy_templates(source_username, destination_username, commit):
    """Copy source's templates to destination, forking the exercises they use."""
    source, destination = _user(source_username), _user(destination_username)
    if source.id == destination.id:
        sys.exit('source and destination are the same account')

    templates = (WorkoutTemplate.query
                 .filter_by(user_id=source.id)
                 .order_by(WorkoutTemplate.name).all())
    if not templates:
        sys.exit(f'{source.username} has no templates to copy')

    already = WorkoutTemplate.query.filter_by(user_id=destination.id).count()
    if already:
        sys.exit(f'{destination.username} already has {already} template(s) — '
                 f'refusing to add more. Delete them first if you meant to redo this.')

    # The catalogue is per user, so a copied template row cannot point at the
    # source's exercises. Find-or-create, not create: the source's templates
    # overlap, and creating blindly would give the destination a duplicate of
    # every exercise appearing in more than one template.
    forked = {}

    def _destination_exercise(source_exercise):
        if source_exercise.id in forked:
            return forked[source_exercise.id]
        mine = Exercise.query.filter_by(user_id=destination.id,
                                        name=source_exercise.name).first()
        if mine is None:
            mine = Exercise(
                name=source_exercise.name,
                previous_name=source_exercise.previous_name,
                muscle_group=source_exercise.muscle_group,
                default_rest_seconds=source_exercise.default_rest_seconds,
                weight_increment=source_exercise.weight_increment,
                is_unilateral=source_exercise.is_unilateral,
                user_id=destination.id,
            )
            db.session.add(mine)
            db.session.flush()
        forked[source_exercise.id] = mine
        return mine

    print(f'{source.username} -> {destination.username}')
    for t in templates:
        print(f'  {t.name} ({len(t.exercises)} exercises)')
        if not commit:
            continue
        copy = WorkoutTemplate(name=t.name, user_id=destination.id)
        db.session.add(copy)
        db.session.flush()          # need copy.id before the children
        for te in t.exercises:
            db.session.add(TemplateExercise(
                template_id=copy.id,
                exercise_id=_destination_exercise(te.exercise).id,
                position=te.position,
                rest_seconds=te.rest_seconds,
            ))

    if commit:
        db.session.commit()
        print(f'\ncopied {len(templates)} template(s) and '
              f'{len(forked)} exercise(s).')
    else:
        print('\ndry run — nothing written. Re-run with --commit to do it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='username to copy templates FROM')
    parser.add_argument('destination', help='username to copy templates TO')
    parser.add_argument('--commit', action='store_true',
                        help='actually write; without it this is a dry run')
    args = parser.parse_args()
    with app.app_context():
        copy_templates(args.source, args.destination, args.commit)


if __name__ == '__main__':
    main()
