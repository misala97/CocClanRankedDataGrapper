import datetime as dt
import os
import uuid

from flask import Blueprint, current_app, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    ArchivedQuiz, ArchivedQuizRound, ArchivedQuizQuestion, ArchivedQuizSong,
    ROUND_TYPES, DEFAULT_ROUND_TEMPLATE, TRIVIA_CATEGORIES,
)
from features.quizbank.llm import reconstruct_question
from auth import login_required

quizbank_bp = Blueprint('quizbank', __name__)

UPLOAD_SUBDIR = 'quizbank_uploads'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value):
    try:
        return dt.datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _upload_dir():
    path = os.path.join(current_app.static_folder, UPLOAD_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _save_round_image(round_, file_storage):
    if not file_storage or not file_storage.filename:
        return
    ext = secure_filename(file_storage.filename).rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return
    _delete_round_image(round_)
    filename = f'{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(_upload_dir(), filename))
    round_.image_filename = filename


def _delete_round_image(round_):
    if not round_.image_filename:
        return
    path = os.path.join(_upload_dir(), round_.image_filename)
    if os.path.exists(path):
        os.remove(path)
    round_.image_filename = None


def _quiz_row(quiz):
    return {
        'id': quiz.id,
        'event_date': quiz.event_date,
        'venue': quiz.venue,
        'quizmaster': quiz.quizmaster,
        'notes': quiz.notes,
        'rounds': quiz.rounds,
        'question_count': sum(len(r.questions) for r in quiz.rounds if r.round_type == 'trivia'),
    }


def _all_trivia_questions(quizzes):
    for quiz in quizzes:
        for r in quiz.rounds:
            if r.round_type == 'trivia':
                for q in r.questions:
                    yield q


def _category_breakdown(quizzes):
    groups = {}
    for q in _all_trivia_questions(quizzes):
        key = q.category or 'Unkategorisiert'
        groups.setdefault(key, []).append(q)
    result = []
    for label, questions in groups.items():
        points = [q.points for q in questions if q.points is not None]
        result.append({
            'label': label,
            'question_count': len(questions),
            'avg_points': round(sum(points) / len(points), 2) if points else None,
        })
    result.sort(key=lambda g: g['question_count'], reverse=True)
    return result


def _quiz_group_breakdown(quizzes, key_func):
    groups = {}
    for quiz in quizzes:
        key = key_func(quiz) or 'Unbekannt'
        groups.setdefault(key, []).append(quiz)
    result = []
    for label, group_quizzes in groups.items():
        result.append({
            'label': label,
            'quiz_count': len(group_quizzes),
        })
    result.sort(key=lambda g: g['quiz_count'], reverse=True)
    return result


@quizbank_bp.route('/quizbank')
@login_required
def quizbank_dashboard():
    quizzes = ArchivedQuiz.query.order_by(
        ArchivedQuiz.event_date.is_(None), ArchivedQuiz.event_date.desc(), ArchivedQuiz.id.desc()
    ).all()
    rows = [_quiz_row(q) for q in quizzes]

    return render_template(
        'quizbank/quizbank.html',
        rows=rows,
        round_types=ROUND_TYPES,
        trivia_categories=TRIVIA_CATEGORIES,
        llm_error=request.args.get('llm_error'),
        open_quiz_id=request.args.get('open', type=int),
        category_breakdown=_category_breakdown(quizzes),
        quizmaster_breakdown=_quiz_group_breakdown(quizzes, lambda q: q.quizmaster),
        venue_breakdown=_quiz_group_breakdown(quizzes, lambda q: q.venue),
    )


@quizbank_bp.route('/quizbank/add', methods=['POST'])
@login_required
def quizbank_add_quiz():
    quiz = ArchivedQuiz(
        event_date=_to_date(request.form.get('event_date', '')),
        venue=request.form.get('venue', '').strip() or None,
        quizmaster=request.form.get('quizmaster', '').strip() or None,
        notes=request.form.get('notes', '').strip() or None,
    )
    for i, round_type in enumerate(DEFAULT_ROUND_TEMPLATE, start=1):
        quiz.rounds.append(ArchivedQuizRound(position=i, round_type=round_type))
    db.session.add(quiz)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz.id))


@quizbank_bp.route('/quizbank/<int:quiz_id>/update', methods=['POST'])
@login_required
def quizbank_update_quiz(quiz_id):
    quiz = db.get_or_404(ArchivedQuiz, quiz_id)
    quiz.event_date = _to_date(request.form.get('event_date', ''))
    quiz.venue = request.form.get('venue', '').strip() or None
    quiz.quizmaster = request.form.get('quizmaster', '').strip() or None
    quiz.notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz.id))


@quizbank_bp.route('/quizbank/<int:quiz_id>/delete', methods=['POST'])
@login_required
def quizbank_delete_quiz(quiz_id):
    quiz = db.get_or_404(ArchivedQuiz, quiz_id)
    for r in quiz.rounds:
        _delete_round_image(r)
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard'))


@quizbank_bp.route('/quizbank/<int:quiz_id>/rounds/add', methods=['POST'])
@login_required
def quizbank_add_round(quiz_id):
    quiz = db.get_or_404(ArchivedQuiz, quiz_id)
    round_type = request.form.get('round_type', '')
    if round_type not in ROUND_TYPES:
        return redirect(url_for('quizbank.quizbank_dashboard', open=quiz.id))
    next_position = max([r.position for r in quiz.rounds], default=0) + 1
    db.session.add(ArchivedQuizRound(quiz_id=quiz.id, position=next_position, round_type=round_type))
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz.id))


@quizbank_bp.route('/quizbank/rounds/<int:round_id>/update', methods=['POST'])
@login_required
def quizbank_update_round(round_id):
    round_ = db.get_or_404(ArchivedQuizRound, round_id)
    round_type = request.form.get('round_type', '')
    if round_type in ROUND_TYPES:
        round_.round_type = round_type
    round_.topic = request.form.get('topic', '').strip() or None
    image = request.files.get('image')
    if image and image.filename:
        _save_round_image(round_, image)
    if request.form.get('remove_image') == '1':
        _delete_round_image(round_)
    quiz_id = round_.quiz_id
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/rounds/<int:round_id>/delete', methods=['POST'])
@login_required
def quizbank_delete_round(round_id):
    round_ = db.get_or_404(ArchivedQuizRound, round_id)
    quiz_id = round_.quiz_id
    _delete_round_image(round_)
    db.session.delete(round_)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/rounds/<int:round_id>/questions/add', methods=['POST'])
@login_required
def quizbank_add_question(round_id):
    round_ = db.get_or_404(ArchivedQuizRound, round_id)
    next_position = max([q.position for q in round_.questions], default=0) + 1
    category = request.form.get('category', '').strip() or None
    question_text = request.form.get('question_text', '').strip()
    answer = request.form.get('answer', '').strip() or None
    is_ai_reconstructed = False
    confidence = None

    if request.form.get('use_ai') == '1':
        try:
            question_text, answer, category, confidence = reconstruct_question(category, question_text, answer)
            is_ai_reconstructed = True
        except Exception as e:
            return redirect(url_for('quizbank.quizbank_dashboard', open=round_.quiz_id, llm_error=str(e)))

    question = ArchivedQuizQuestion(
        round_id=round_.id,
        position=next_position,
        category=category,
        question_text=question_text,
        is_ai_reconstructed=is_ai_reconstructed,
        reconstructed_confidence=confidence,
        answer=answer,
        points=_to_float(request.form.get('points', '')),
    )
    db.session.add(question)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=round_.quiz_id))


@quizbank_bp.route('/quizbank/questions/<int:question_id>/update', methods=['POST'])
@login_required
def quizbank_update_question(question_id):
    question = db.get_or_404(ArchivedQuizQuestion, question_id)
    question.category = request.form.get('category', '').strip() or None
    question.question_text = request.form.get('question_text', '').strip()
    question.is_ai_reconstructed = False  # any manual save means a human wrote/checked this text
    question.reconstructed_confidence = None
    question.answer = request.form.get('answer', '').strip() or None
    question.points = _to_float(request.form.get('points', ''))
    quiz_id = question.round.quiz_id
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/questions/<int:question_id>/reconstruct_ai', methods=['POST'])
@login_required
def quizbank_reconstruct_question(question_id):
    question = db.get_or_404(ArchivedQuizQuestion, question_id)
    quiz_id = question.round.quiz_id
    try:
        text, answer, category, confidence = reconstruct_question(question.category, question.question_text, question.answer)
        question.question_text = text
        question.answer = answer
        question.category = category
        question.is_ai_reconstructed = True
        question.reconstructed_confidence = confidence
        db.session.commit()
    except Exception as e:
        return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id, llm_error=str(e)))
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/questions/<int:question_id>/delete', methods=['POST'])
@login_required
def quizbank_delete_question(question_id):
    question = db.get_or_404(ArchivedQuizQuestion, question_id)
    quiz_id = question.round.quiz_id
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/rounds/<int:round_id>/songs/add', methods=['POST'])
@login_required
def quizbank_add_song(round_id):
    round_ = db.get_or_404(ArchivedQuizRound, round_id)
    next_position = max([s.position for s in round_.songs], default=0) + 1
    song = ArchivedQuizSong(
        round_id=round_.id,
        position=next_position,
        artist=request.form.get('artist', '').strip() or None,
        title=request.form.get('title', '').strip() or None,
    )
    db.session.add(song)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=round_.quiz_id))


@quizbank_bp.route('/quizbank/songs/<int:song_id>/update', methods=['POST'])
@login_required
def quizbank_update_song(song_id):
    song = db.get_or_404(ArchivedQuizSong, song_id)
    song.artist = request.form.get('artist', '').strip() or None
    song.title = request.form.get('title', '').strip() or None
    quiz_id = song.round.quiz_id
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))


@quizbank_bp.route('/quizbank/songs/<int:song_id>/delete', methods=['POST'])
@login_required
def quizbank_delete_song(song_id):
    song = db.get_or_404(ArchivedQuizSong, song_id)
    quiz_id = song.round.quiz_id
    db.session.delete(song)
    db.session.commit()
    return redirect(url_for('quizbank.quizbank_dashboard', open=quiz_id))
