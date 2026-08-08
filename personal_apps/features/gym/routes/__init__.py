"""Gym routes, split by domain.

Importing a module here is what registers its routes onto gym_bp, so every
module must be imported below even though the names look unused -- hence the
noqa markers.

The re-exports at the bottom are not decoration. Eleven test call sites and
scripts/make_chart_fixture.py import these private helpers from
`features.gym.routes`, and keeping that path working is what let this split
happen without touching a single caller.
"""
from ._blueprint import gym_bp

from . import _legacy          # noqa: F401

from ._legacy import (         # noqa: F401
    load_performed, _to_performed, _session_rest_entries,
    performed_from_session,
    _to_float, _to_increment, _to_int, _clean_muscle_group,
    _clean_equipment, _to_stack_steps, _clean_secondary_groups,
    _get_active_session,
    _live_context, _exercise_detail_payload, _chart_geometry,
    _default_position,
)
# Re-exported, not defined in the routes package: seeding.py owns it because
# sharing.py needs it too and cannot import a module that registers routes.
# Three tests import it from `features.gym.routes`, so the path has to survive.
from ..seeding import _last_full_performance             # noqa: F401

__all__ = ['gym_bp']
