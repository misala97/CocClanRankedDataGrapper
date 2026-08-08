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


def _capture(client, exercise_id, raw_position, payload):
    """One case: the geometry, and the SVG Jinja drew from it."""
    query = f'?position={raw_position}' if raw_position else ''
    html = client.get(f'/gym/exercises/{exercise_id}{query}').get_data(as_text=True)
    match = re.search(r'<svg viewBox.*?</svg>', html, re.S)
    if not match:
        raise SystemExit(
            'no <svg> in the rendered page -- the template is already a React '
            'shell, so the Jinja baseline can no longer be captured. Restore '
            'the committed fixture instead of regenerating it.')
    return {
        'exercise_id': exercise_id,
        'query': query,
        'chart': payload.model_dump(mode='json')['chart'],
        'session_count': len(payload.table),
        'first_date': payload.table[-1].started_at.strftime('%d.%m.%Y'),
        'last_date': payload.table[0].started_at.strftime('%d.%m.%Y'),
        'jinja_svg': match.group(0),
    }


def main():
    """Captures two cases.

    The default view resolves to a single position slot, so it only ever plots
    one series -- the per-slot P-labels, the opacity ramp and the stroke-width
    ramp are unreachable there. ?position=all is the comparison view and is the
    only way to get a multi-series chart, so both are captured.
    """
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        user_id = _admin_id()
        with flask_app.test_request_context():
            flask_session['user_id'] = user_id
            single = multi = None
            for exercise in my_exercises().all():
                default = _exercise_detail_payload(owned_exercise(exercise.id), None)
                if not (default.chart and default.chart.series and len(default.table) >= 3):
                    continue
                if single is None:
                    single = (exercise.id, default)
                every = _exercise_detail_payload(owned_exercise(exercise.id), 'all')
                if every.chart and len(every.chart.series) > 1 and multi is None:
                    multi = (exercise.id, every)
                if single and multi:
                    break
        if single is None:
            raise SystemExit('no exercise in the dev database has a plottable chart')

    with flask_app.test_client() as client:
        with client.session_transaction() as session:
            session['user_id'] = user_id
        cases = {'single_series': _capture(client, single[0], None, single[1])}
        if multi is not None:
            cases['multi_series'] = _capture(client, multi[0], 'all', multi[1])
        else:
            print('WARNING: no exercise plotted in two positions -- the '
                  'multi-series case is not covered by the golden master.')

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding='utf-8')

    for name, case in cases.items():
        print(f'  {name}: exercise {case["exercise_id"]}{case["query"]}, '
              f'{len(case["chart"]["series"])} series, '
              f'{len(case["jinja_svg"])} chars of SVG')


if __name__ == '__main__':
    main()
