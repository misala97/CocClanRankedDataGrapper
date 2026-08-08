"""Regenerate the golden-master fixture for the exercise chart.

    python scripts/make_chart_fixture.py

Writes static/gym/src/components/__fixtures__/chart-golden.json: real chart
geometry from the dev database, plus the SVG the Jinja template rendered from
that same geometry. ExerciseChart.golden.test.tsx renders the React component
from the geometry and asserts it draws the identical shapes.

Run this only when _chart_geometry legitimately changes shape. Do NOT run it to
make a failing golden test pass -- a diff there means the drawing moved, which
is the thing the test exists to catch.

Once templates/gym/exercise_detail.html becomes a React shell (Task 6 of the
step-1 plan) the Jinja side is gone, and the committed fixture becomes the only
record of what the original drew. That is deliberate: it is the baseline the
port is held to.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))

from app import app as flask_app                       # noqa: E402
from conftest import _admin_id                          # noqa: E402
from features.gym.routes import _exercise_detail_payload  # noqa: E402
from features.gym.scope import my_exercises, owned_exercise  # noqa: E402
from flask import session as flask_session              # noqa: E402

DEST = (pathlib.Path(__file__).resolve().parent.parent
        / 'static' / 'gym' / 'src' / 'components' / '__fixtures__'
        / 'chart-golden.json')


def main():
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        user_id = _admin_id()
        with flask_app.test_request_context():
            flask_session['user_id'] = user_id
            chosen = None
            for exercise in my_exercises().all():
                payload = _exercise_detail_payload(owned_exercise(exercise.id), None)
                if payload.chart and payload.chart.series and len(payload.table) >= 3:
                    chosen = (exercise.id, payload)
                    # Prefer a multi-series exercise: it is the only case that
                    # exercises the per-slot P-labels and the opacity ramp.
                    if len(payload.chart.series) > 1:
                        break
        if chosen is None:
            raise SystemExit('no exercise in the dev database has a plottable chart')
        exercise_id, payload = chosen

    with flask_app.test_client() as client:
        with client.session_transaction() as session:
            session['user_id'] = user_id
        html = client.get(f'/gym/exercises/{exercise_id}').get_data(as_text=True)

    match = re.search(r'<svg viewBox.*?</svg>', html, re.S)
    if not match:
        raise SystemExit(
            'no <svg> in the rendered page -- the template is already a React '
            'shell, so the Jinja baseline can no longer be captured. Restore '
            'the committed fixture instead of regenerating it.')

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        'exercise_id': exercise_id,
        'chart': payload.model_dump(mode='json')['chart'],
        'session_count': len(payload.table),
        'first_date': payload.table[-1].started_at.strftime('%d.%m.%Y'),
        'last_date': payload.table[0].started_at.strftime('%d.%m.%Y'),
        'jinja_svg': match.group(0),
    }, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'wrote {DEST.name}: exercise {exercise_id}, '
          f'{len(payload.chart.series)} series, {len(match.group(0))} chars of SVG')


if __name__ == '__main__':
    main()
