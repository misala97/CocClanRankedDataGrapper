from flask import Blueprint, render_template, request

from models import Player
from features.player.routes import calculate_activity_score, calculate_skill_score

compare_bp = Blueprint('compare', __name__)


@compare_bp.route('/compare')
def compare():
    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()

    tag1 = request.args.get('p1', '').strip()
    tag2 = request.args.get('p2', '').strip()

    p1 = p2 = None
    act1 = act2 = skill1 = skill2 = None

    if tag1:
        p1 = Player.query.get(tag1)
    if tag2:
        p2 = Player.query.get(tag2)

    if p1 and p2 and tag1 != tag2:
        act1   = calculate_activity_score(p1.tag, period='month')
        act2   = calculate_activity_score(p2.tag, period='month')
        skill1 = calculate_skill_score(p1.tag, period='month')
        skill2 = calculate_skill_score(p2.tag, period='month')

    return render_template(
        'compare/compare.html',
        players=players,
        p1=p1, p2=p2,
        tag1=tag1, tag2=tag2,
        act1=act1, act2=act2,
        skill1=skill1, skill2=skill2,
    )
