# extensions.py
from flask_sqlalchemy import SQLAlchemy

# WICHTIG: Keine App hier übergeben!
db = SQLAlchemy()

# Set by run_scheduler.py at startup so tasks can reschedule themselves
scheduler = None