"""Barcode scanner: the page, and the lookup it calls after every scan."""
from flask import Blueprint, current_app, jsonify, render_template

from auth import admin_required
from . import codes, sources

barcode_bp = Blueprint('barcode', __name__, url_prefix='/barcode')


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
        return jsonify(sources.lookup(code))
    except sources.UpstreamError as exc:
        current_app.logger.warning('barcode lookup %s failed: %s', code, exc)
        return jsonify(error='Datenbank gerade nicht erreichbar – bitte nochmal versuchen.',
                       code=code), 502
