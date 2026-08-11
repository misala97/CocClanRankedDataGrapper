"""The gym blueprint, alone in its own module.

Every routes/ module imports gym_bp from here rather than from the package, so
importing one module never pulls in the others. That is the whole reason this
file exists and the only thing it may ever contain -- adding a helper here
would reintroduce the cycle it was created to break.
"""
from flask import Blueprint

gym_bp = Blueprint('gym', __name__)
