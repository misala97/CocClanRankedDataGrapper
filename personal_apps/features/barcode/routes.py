"""Barcode scanner: the page, the lookup it calls after every scan, and book covers."""
from flask import Blueprint, abort, current_app, jsonify, render_template, url_for

from auth import admin_required
from . import codes, sources

barcode_bp = Blueprint('barcode', __name__, url_prefix='/barcode')

COVER_MAX_AGE = 7 * 24 * 3600


@barcode_bp.route('/')
@admin_required
def index():
    return render_template('barcode/index.html')


@barcode_bp.route('/api/<raw>')
@admin_required
def api_lookup(raw):
    try:
        code = codes.normalize(raw)
    except codes.InvalidCode:
        return jsonify(error='Ungültiger Code – Länge oder Prüfziffer stimmt nicht.'), 400
    try:
        data = sources.lookup(code)
    except sources.UpstreamError as exc:
        current_app.logger.warning('barcode lookup %s failed: %s', code, exc)
        return jsonify(error='Datenbank gerade nicht erreichbar – bitte nochmal versuchen.',
                       code=code), 502
    if data.get('book'):
        data['book']['image'] = url_for('barcode.cover', isbn=code)
    return jsonify(data)


@barcode_bp.route('/cover/<isbn>')
@admin_required
def cover(isbn):
    """The DNB's cover for a book, from our origin (see sources.fetch_cover)."""
    try:
        code = codes.normalize(isbn)
    except codes.InvalidCode:
        abort(404)
    if codes.classify(code) != 'book':
        abort(404)
    try:
        found = sources.fetch_cover(code)
    except sources.UpstreamError:
        found = None
    if not found:
        abort(404)
    content, media_type = found
    response = current_app.response_class(content, mimetype=media_type)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.cache_control.private = True
    response.cache_control.max_age = COVER_MAX_AGE
    return response
