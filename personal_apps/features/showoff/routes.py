from flask import Blueprint, render_template
from auth import login_required

showoff_bp = Blueprint('showoff', __name__, url_prefix='/showoff')


@showoff_bp.route('/')
@login_required
def index():
    return render_template('showoff/index.html')
