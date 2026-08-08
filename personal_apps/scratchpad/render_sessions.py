"""Dump every session page's HTML, for before/after comparison.

    python scratchpad/render_sessions.py out.html

Used to prove a refactor of session_detail changed nothing the browser sees.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))

from app import app as flask_app          # noqa: E402
from conftest import _admin_id            # noqa: E402
from models import WorkoutSession         # noqa: E402

flask_app.config['TESTING'] = True
with flask_app.app_context():
    user_id = _admin_id()
    ids = [s.id for s in WorkoutSession.query.filter_by(user_id=user_id)
           .order_by(WorkoutSession.id).all()]

out = []
with flask_app.test_client() as client:
    with client.session_transaction() as session:
        session['user_id'] = user_id
    for session_id in ids:
        response = client.get(f'/gym/session/{session_id}')
        out.append(f'===== {session_id} status={response.status_code} =====')
        out.append(response.get_data(as_text=True))

pathlib.Path(sys.argv[1]).write_text('\n'.join(out), encoding='utf-8')
print(f'wrote {sys.argv[1]}: {len(ids)} sessions')
