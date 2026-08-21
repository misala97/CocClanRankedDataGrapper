"""The radar blueprint, alone in its own module.

Same pattern as the gym blueprint: every routes/ module imports radar_bp from
here rather than from the package, so importing one never pulls in the others.
That is the whole reason this file exists.
"""
from flask import Blueprint

radar_bp = Blueprint('radar', __name__, url_prefix='/radar')
