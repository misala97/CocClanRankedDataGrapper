"""Radar routes, split by surface.

Importing a module here registers its routes onto radar_bp, so each must be
imported below even though the names look unused.
"""
from ._blueprint import radar_bp     # noqa: F401

from . import api                    # noqa: F401
from . import views                  # noqa: F401
