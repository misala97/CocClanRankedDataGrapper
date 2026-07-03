import datetime as dt
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from extensions import db
from models import PendingPush
from features.gym.push import send_push_to_all


def check_pending_pushes():
    with app.app_context():
        due = PendingPush.query.filter(
            PendingPush.sent == False,  # noqa: E712 (SQLAlchemy comparison, not a real bool check)
            PendingPush.fire_at <= dt.datetime.utcnow(),
        ).all()
        for pending in due:
            send_push_to_all({'title': 'Rest complete', 'body': 'Time for your next set.'})
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
