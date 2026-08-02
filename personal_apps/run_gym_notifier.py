import datetime as dt
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from extensions import db
from models import PendingPush, WorkoutSession
from features.gym.push import send_push_to_user


def check_pending_pushes():
    with app.app_context():
        due = (
            PendingPush.query
            .join(WorkoutSession, PendingPush.session_id == WorkoutSession.id)
            .filter(
                PendingPush.sent == False,  # noqa: E712 (SQLAlchemy comparison, not a real bool check)
                PendingPush.fire_at <= dt.datetime.utcnow(),
            )
            .add_columns(WorkoutSession.user_id)
            .all()
        )
        for pending, user_id in due:
            # A rest timer belongs to whoever started the session it came from.
            send_push_to_user(user_id, {'title': 'Rest complete', 'body': 'Time for your next set.'})
            pending.sent = True
        if due:
            db.session.commit()


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_pending_pushes, trigger="interval", seconds=10, max_instances=1)
    scheduler.start()

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
