import datetime as dt
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from extensions import db
from models import AppUser, PendingPush, WorkoutSession
from features.gym import stats
from features.gym.push import send_push_to_user


def check_pending_pushes():
    with app.app_context():
        due = (
            PendingPush.query
            .join(WorkoutSession, PendingPush.session_id == WorkoutSession.id)
            .filter(
                PendingPush.sent == False,  # noqa: E712 (SQLAlchemy comparison, not a real bool check)
                PendingPush.fire_at <= dt.datetime.utcnow(),
                # A rest push for a workout that is over is never right. Every
                # route that ends a session cancels its pending rows
                # (_cancel_pending_push), but that only covers rows the app
                # itself retires -- a session finished any other way (a manual
                # database edit, a restore) leaves them behind, and without
                # this the daemon buzzed the phone for a workout that ended
                # hours ago. Marked sent rather than deleted: the row is
                # evidence of a rest that was scheduled, and swallowing it
                # silently would hide the state it came from.
                WorkoutSession.finished_at.is_(None),
            )
            .add_columns(WorkoutSession.user_id)
            .all()
        )
        for pending, user_id in due:
            # A rest timer belongs to whoever started the session it came from.
            send_push_to_user(user_id, {'title': 'Rest complete', 'body': 'Time for your next set.'})
            pending.sent = True

        # Retire the orphans in the same pass, so they stop being scanned
        # every 20 seconds for the life of the database.
        orphaned = (
            PendingPush.query
            .join(WorkoutSession, PendingPush.session_id == WorkoutSession.id)
            .filter(
                PendingPush.sent == False,  # noqa: E712
                WorkoutSession.finished_at.isnot(None),
            )
            .all()
        )
        for pending in orphaned:
            pending.sent = True

        if due or orphaned:
            db.session.commit()


def _weekly_digest_for(user_id, now):
    """The week's payload for one user, or None for a week with no workouts.

    Silence over nagging: an empty week sends nothing, because "you didn't
    train" arriving as a push notification is a scold, not a stat.

    Runs inside a faked request context so load_performed() and its scope
    machinery work exactly as they do for the page -- current_user_id() reads
    the flask session, which a bare app context does not have. Duplicating
    the bulk-load outside scope.py would be the drifting copy this codebase
    keeps refusing to create.
    """
    from flask import session as flask_session
    from features.gym.routes.history import load_performed

    week_start = (now - dt.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)

    with app.test_request_context():
        flask_session['user_id'] = user_id
        performed = load_performed()

    this_week = [row for row in performed if row.started_at >= week_start]
    if not this_week:
        return None

    session_ids = {row.session_id for row in this_week}
    volume = sum(stats.row_volume(row) for row in this_week)
    records_by_session = stats.session_record_counts(performed)
    records = sum(count for session_id, count in records_by_session.items()
                  if session_id in session_ids)

    workouts = len(session_ids)
    parts = [
        f"{workouts} {'Workout' if workouts == 1 else 'Workouts'}",
        f"{format(round(volume), ',d').replace(',', '.')} kg",
    ]
    if records:
        parts.append(f"{records} {'Rekord' if records == 1 else 'Rekorde'}")
    return {'title': 'Deine Trainingswoche', 'body': ' · '.join(parts)}


def send_weekly_digests():
    """Sunday evening: the week, added up, to every device that opted into
    push. send_push_to_user is a no-op for a user with no subscription, so
    there is nothing to filter here."""
    now = dt.datetime.utcnow()
    with app.app_context():
        for user in AppUser.query.all():
            payload = _weekly_digest_for(user.id, now)
            if payload is not None:
                send_push_to_user(user.id, payload)


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_pending_pushes, trigger="interval", seconds=10, max_instances=1)
    # 17:00 UTC Sunday = 18:00/19:00 Berlin depending on DST -- evening either
    # way, which is what matters for a week-in-review. misfire_grace_time lets
    # a deploy-restart around the hour still fire instead of silently skipping
    # the week.
    scheduler.add_job(send_weekly_digests, trigger="cron",
                      day_of_week="sun", hour=17, minute=0,
                      max_instances=1, misfire_grace_time=3600)
    scheduler.start()

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
