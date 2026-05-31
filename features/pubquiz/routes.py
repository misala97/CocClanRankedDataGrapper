import datetime as dt

from flask import Blueprint, render_template, request, session, redirect, url_for

from extensions import db
from models import PubQuizRounds, PubQuizTeams
from features.auth.routes import require_admin_login

pubquiz_bp = Blueprint('pubquiz', __name__)


def _team_scores(team):
    r1p = team.round1_points or 0
    r2p = team.round2_points or 0
    r3p = team.round3_points or 0
    r4p = team.round4_points or 0
    r1s = team.round1_size or 1
    r2s = team.round2_size or 1
    r3s = team.round3_size or 1
    r4s = team.round4_size or 1
    total      = r1p + r2p + r3p + r4p
    per_capita = round(r1p / r1s + r2p / r2s + r3p / r3s + r4p / r4s, 2)
    return total, per_capita


@pubquiz_bp.route('/pubquiz')
def pubquiz():
    rounds      = PubQuizRounds.query.order_by(PubQuizRounds.datum.desc()).all()
    selected_id = request.args.get('round_id', type=int)
    if not selected_id and rounds:
        selected_id = rounds[0].id

    selected_round = PubQuizRounds.query.filter_by(id=selected_id).first() if selected_id else None

    team_data      = []
    round_rankings = {1: [], 2: [], 3: [], 4: []}
    overall_avg    = None
    round_avgs     = {1: None, 2: None, 3: None, 4: None}

    if selected_round:
        for t in selected_round.teams:
            total, per_capita = _team_scores(t)
            team_data.append({
                'id': t.id,
                'name': t.name or '—',
                'round1_points': t.round1_points,
                'round2_points': t.round2_points,
                'round3_points': t.round3_points,
                'round4_points': t.round4_points,
                'round1_size': t.round1_size,
                'round2_size': t.round2_size,
                'round3_size': t.round3_size,
                'round4_size': t.round4_size,
                'total': total,
                'per_capita': per_capita,
            })
        team_data.sort(key=lambda x: x['total'], reverse=True)

        for rnum, key in [(1, 'round1_points'), (2, 'round2_points'), (3, 'round3_points'), (4, 'round4_points')]:
            pts         = [t[key] for t in team_data if t[key] is not None]
            round_avgs[rnum] = round(sum(pts) / len(pts), 2) if pts else None
            with_pts    = sorted([t for t in team_data if t[key] is not None], key=lambda x: x[key], reverse=True)
            without_pts = [t for t in team_data if t[key] is None]
            round_rankings[rnum] = with_pts + without_pts

        totals      = [t['total'] for t in team_data]
        overall_avg = round(sum(totals) / len(totals), 2) if totals else None

    return render_template('pubquiz/pubquiz.html',
                           rounds=rounds,
                           selected_round=selected_round,
                           selected_id=selected_id,
                           team_data=team_data,
                           round_rankings=round_rankings,
                           overall_avg=overall_avg,
                           round_avgs=round_avgs)


@pubquiz_bp.route('/pubquiz/admin/logout')
def pubquiz_admin_logout():
    session.clear()
    return redirect(url_for('pubquiz.pubquiz'))


@pubquiz_bp.route('/pubquiz/admin')
@require_admin_login
def pubquiz_admin():
    rounds      = PubQuizRounds.query.order_by(PubQuizRounds.datum.desc()).all()
    selected_id = request.args.get('round_id', type=int)
    if not selected_id and rounds:
        selected_id = rounds[0].id
    selected_round = PubQuizRounds.query.filter_by(id=selected_id).first() if selected_id else None
    return render_template('pubquiz/pubquiz_admin.html',
                           rounds=rounds,
                           selected_round=selected_round,
                           selected_id=selected_id)


@pubquiz_bp.route('/pubquiz/admin/round/create', methods=['POST'])
@require_admin_login
def pubquiz_create_round():
    datum_str   = request.form.get('datum', '').strip()
    bilderrunde = request.form.get('bilderrunde', '').strip() or None
    quizmaster  = request.form.get('quizmaster', '').strip() or None
    try:
        datum = dt.datetime.fromisoformat(datum_str) if datum_str else dt.datetime.now()
    except ValueError:
        datum = dt.datetime.now()
    new_round = PubQuizRounds(datum=datum, bilderrunde=bilderrunde, quizmaster=quizmaster)
    db.session.add(new_round)
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=new_round.id))


@pubquiz_bp.route('/pubquiz/admin/round/<int:round_id>/delete', methods=['POST'])
@require_admin_login
def pubquiz_delete_round(round_id):
    r = db.get_or_404(PubQuizRounds,round_id)
    db.session.delete(r)
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin'))


@pubquiz_bp.route('/pubquiz/admin/round/<int:round_id>/update', methods=['POST'])
@require_admin_login
def pubquiz_update_round(round_id):
    r         = db.get_or_404(PubQuizRounds,round_id)
    datum_str = request.form.get('datum', '').strip()
    if datum_str:
        try:
            r.datum = dt.datetime.fromisoformat(datum_str)
        except ValueError:
            pass
    r.bilderrunde = request.form.get('bilderrunde', '').strip() or None
    r.quizmaster  = request.form.get('quizmaster', '').strip() or None
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))


@pubquiz_bp.route('/pubquiz/admin/team/add', methods=['POST'])
@require_admin_login
def pubquiz_add_team():
    round_id = request.form.get('round_id', type=int)
    name     = request.form.get('name', '').strip()
    if not round_id or not name:
        return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))
    if PubQuizTeams.query.filter(PubQuizTeams.round_id == round_id, db.func.lower(PubQuizTeams.name) == name.lower()).first():
        return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id, error='duplicate', error_name=name))
    team = PubQuizTeams(name=name, round_id=round_id)
    db.session.add(team)
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))


@pubquiz_bp.route('/pubquiz/admin/round/<int:round_id>/scores/<int:round_num>', methods=['POST'])
@require_admin_login
def pubquiz_save_round_scores(round_id, round_num):
    if round_num not in (1, 2, 3, 4):
        return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))
    teams = PubQuizTeams.query.filter_by(round_id=round_id).all()
    for team in teams:
        pts_str  = request.form.get(f'team_{team.id}_points', '').strip()
        size_str = request.form.get(f'team_{team.id}_size', '').strip()
        try:
            pts = float(pts_str)
        except ValueError:
            pts = None
        size = int(size_str) if size_str.isdigit() and int(size_str) > 0 else None
        if round_num == 1:   team.round1_points, team.round1_size = pts, size
        elif round_num == 2: team.round2_points, team.round2_size = pts, size
        elif round_num == 3: team.round3_points, team.round3_size = pts, size
        else:                team.round4_points, team.round4_size = pts, size
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))


@pubquiz_bp.route('/pubquiz/admin/team/<int:team_id>/update', methods=['POST'])
@require_admin_login
def pubquiz_update_team(team_id):
    team = db.get_or_404(PubQuizTeams,team_id)
    team.name = request.form.get('name', team.name).strip()

    def _float_pts(key, fallback):
        v = request.form.get(key, '').strip()
        try: return float(v)
        except ValueError: return fallback

    def _int(key, fallback):
        v = request.form.get(key, '').strip()
        return int(v) if v.isdigit() else fallback

    team.round1_points = _float_pts('round1_points', team.round1_points)
    team.round2_points = _float_pts('round2_points', team.round2_points)
    team.round3_points = _float_pts('round3_points', team.round3_points)
    team.round1_size   = _int('round1_size', team.round1_size)
    team.round2_size   = _int('round2_size', team.round2_size)
    team.round3_size   = _int('round3_size', team.round3_size)
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=team.round_id))


@pubquiz_bp.route('/pubquiz/admin/team/<int:team_id>/delete', methods=['POST'])
@require_admin_login
def pubquiz_delete_team(team_id):
    team     = db.get_or_404(PubQuizTeams,team_id)
    round_id = team.round_id
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for('pubquiz.pubquiz_admin', round_id=round_id))
