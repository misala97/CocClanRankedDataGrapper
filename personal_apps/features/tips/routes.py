import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for

from extensions import db
from models import DeliveryShift
from auth import login_required

tips_bp = Blueprint('tips', __name__)

BIKE_CHOICES = [
    ('small', 'Klein'),
    ('big', 'Groß'),
]

WEATHER_CHOICES = [
    ('clear', 'Klar'),
    ('rain', 'Regen'),
    ('heavy_rain', 'Starkregen'),
    ('snow', 'Schnee'),
    ('thunderstorm', 'Gewitter'),
    ('hail', 'Hagel'),
]
WEATHER_LABELS = dict(WEATHER_CHOICES)
BIKE_LABELS = dict(BIKE_CHOICES)


def _to_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _to_time(value):
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, '%H:%M').time()
    except ValueError:
        return None


def _shift_row(s):
    total = (s.tips_cash or 0) + (s.tips_online or 0)
    per_hour = round(total / s.hours_worked, 2) if s.hours_worked else None
    per_delivery = round(total / s.deliveries, 2) if s.deliveries else None
    return {
        'id': s.id,
        'shift_date': s.shift_date,
        'shift_start': s.shift_start,
        'shift_end': s.shift_end,
        'hours_worked': s.hours_worked,
        'tips_cash': s.tips_cash or 0,
        'tips_online': s.tips_online or 0,
        'deliveries': s.deliveries or 0,
        'bike_size': s.bike_size,
        'bike_label': BIKE_LABELS.get(s.bike_size, '—'),
        'weather': s.weather,
        'weather_label': WEATHER_LABELS.get(s.weather, '—'),
        'notes': s.notes,
        'total': round(total, 2),
        'per_hour': per_hour,
        'per_delivery': per_delivery,
    }


def _aggregate(rows):
    shift_count = len(rows)
    total_cash = sum(r['tips_cash'] for r in rows)
    total_online = sum(r['tips_online'] for r in rows)
    total_tips = total_cash + total_online
    total_hours = sum(r['hours_worked'] or 0 for r in rows)
    total_deliveries = sum(r['deliveries'] for r in rows)
    return {
        'shift_count': shift_count,
        'total_cash': round(total_cash, 2),
        'total_online': round(total_online, 2),
        'total_tips': round(total_tips, 2),
        'total_hours': round(total_hours, 2),
        'total_deliveries': total_deliveries,
        'avg_per_shift': round(total_tips / shift_count, 2) if shift_count else None,
        'avg_per_hour': round(total_tips / total_hours, 2) if total_hours else None,
        'avg_per_delivery': round(total_tips / total_deliveries, 2) if total_deliveries else None,
    }


WEEKDAY_LABELS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

TIME_BUCKET_ORDER = ['morning', 'afternoon', 'evening', 'night']
TIME_BUCKET_LABELS = {
    'morning': 'Vormittag (vor 14 Uhr)',
    'afternoon': 'Nachmittag (14–18 Uhr)',
    'evening': 'Abend (18–22 Uhr)',
    'night': 'Nacht (nach 22 Uhr)',
}


def _time_bucket(t):
    if t is None:
        return None
    h = t.hour
    if h < 14:
        return 'morning'
    if h < 18:
        return 'afternoon'
    if h < 22:
        return 'evening'
    return 'night'


def _group_breakdown(rows, key_func, label_func):
    groups = {}
    for r in rows:
        k = key_func(r)
        if k is None:
            continue
        groups.setdefault(k, []).append(r)
    result = []
    for k, group_rows in groups.items():
        agg = _aggregate(group_rows)
        agg['label'] = label_func(k)
        result.append(agg)
    result.sort(key=lambda a: a['avg_per_hour'] if a['avg_per_hour'] is not None else -1, reverse=True)
    return result


@tips_bp.route('/tips')
@login_required
def tips_dashboard():
    shifts = DeliveryShift.query.order_by(DeliveryShift.shift_date.desc(), DeliveryShift.id.desc()).all()
    rows = [_shift_row(s) for s in shifts]

    today = dt.date.today()
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    periods = {
        'week': _aggregate([r for r in rows if r['shift_date'] and r['shift_date'] >= week_start]),
        'month': _aggregate([r for r in rows if r['shift_date'] and r['shift_date'] >= month_start]),
        'year': _aggregate([r for r in rows if r['shift_date'] and r['shift_date'] >= year_start]),
        'all': _aggregate(rows),
    }

    rows_with_rate = [r for r in rows if r['per_hour'] is not None]
    best_rate = sorted(rows_with_rate, key=lambda r: r['per_hour'], reverse=True)[:5]
    worst_rate = sorted(rows_with_rate, key=lambda r: r['per_hour'])[:5]
    rows_with_delivery_rate = [r for r in rows if r['per_delivery'] is not None]
    best_delivery_rate = sorted(rows_with_delivery_rate, key=lambda r: r['per_delivery'], reverse=True)[:5]
    worst_delivery_rate = sorted(rows_with_delivery_rate, key=lambda r: r['per_delivery'])[:5]

    breakdown_weekday = _group_breakdown(
        rows,
        lambda r: r['shift_date'].weekday() if r['shift_date'] else None,
        lambda k: WEEKDAY_LABELS[k],
    )
    breakdown_time = _group_breakdown(
        rows,
        lambda r: _time_bucket(r['shift_start']),
        lambda k: TIME_BUCKET_LABELS[k],
    )
    breakdown_weather = _group_breakdown(
        rows,
        lambda r: r['weather'],
        lambda k: WEATHER_LABELS.get(k, k),
    )
    breakdown_bike = _group_breakdown(
        rows,
        lambda r: r['bike_size'],
        lambda k: BIKE_LABELS.get(k, k),
    )

    chart_rows = sorted([r for r in rows if r['shift_date']], key=lambda r: r['shift_date'])
    chart_labels = [r['shift_date'].strftime('%d.%m.%Y') for r in chart_rows]
    chart_totals = [r['total'] for r in chart_rows]
    chart_rates = [r['per_hour'] if r['per_hour'] is not None else 0 for r in chart_rows]

    return render_template(
        'tips/tips.html',
        rows=rows,
        periods=periods,
        best_rate=best_rate,
        worst_rate=worst_rate,
        best_delivery_rate=best_delivery_rate,
        worst_delivery_rate=worst_delivery_rate,
        breakdown_weekday=breakdown_weekday,
        breakdown_time=breakdown_time,
        breakdown_weather=breakdown_weather,
        breakdown_bike=breakdown_bike,
        chart_labels=chart_labels,
        chart_totals=chart_totals,
        chart_rates=chart_rates,
        bike_choices=BIKE_CHOICES,
        weather_choices=WEATHER_CHOICES,
    )


@tips_bp.route('/tips/add', methods=['POST'])
@login_required
def tips_add():
    date_str = request.form.get('shift_date', '').strip()
    try:
        shift_date = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return redirect(url_for('tips.tips_dashboard'))

    shift = DeliveryShift(
        shift_date=shift_date,
        shift_start=_to_time(request.form.get('shift_start', '')),
        shift_end=_to_time(request.form.get('shift_end', '')),
        hours_worked=_to_float(request.form.get('hours_worked', '')),
        tips_cash=_to_float(request.form.get('tips_cash', '')),
        tips_online=_to_float(request.form.get('tips_online', '')),
        deliveries=_to_int(request.form.get('deliveries', '')),
        bike_size=request.form.get('bike_size') if request.form.get('bike_size') in dict(BIKE_CHOICES) else None,
        weather=request.form.get('weather') if request.form.get('weather') in dict(WEATHER_CHOICES) else None,
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(shift)
    db.session.commit()
    return redirect(url_for('tips.tips_dashboard'))


@tips_bp.route('/tips/<int:shift_id>/update', methods=['POST'])
@login_required
def tips_update(shift_id):
    shift = db.get_or_404(DeliveryShift, shift_id)

    date_str = request.form.get('shift_date', '').strip()
    try:
        shift.shift_date = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        pass

    shift.shift_start = _to_time(request.form.get('shift_start', ''))
    shift.shift_end = _to_time(request.form.get('shift_end', ''))
    shift.hours_worked = _to_float(request.form.get('hours_worked', ''), shift.hours_worked)
    shift.tips_cash = _to_float(request.form.get('tips_cash', ''), shift.tips_cash)
    shift.tips_online = _to_float(request.form.get('tips_online', ''), shift.tips_online)
    shift.deliveries = _to_int(request.form.get('deliveries', ''), shift.deliveries)
    bike = request.form.get('bike_size')
    shift.bike_size = bike if bike in dict(BIKE_CHOICES) else None
    weather = request.form.get('weather')
    shift.weather = weather if weather in dict(WEATHER_CHOICES) else None
    shift.notes = request.form.get('notes', '').strip() or None

    db.session.commit()
    return redirect(url_for('tips.tips_dashboard'))


@tips_bp.route('/tips/<int:shift_id>/delete', methods=['POST'])
@login_required
def tips_delete(shift_id):
    shift = db.get_or_404(DeliveryShift, shift_id)
    db.session.delete(shift)
    db.session.commit()
    return redirect(url_for('tips.tips_dashboard'))
