import calendar
import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy import func

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
    ('heat', 'Hitze'),
]
WEATHER_LABELS = dict(WEATHER_CHOICES)
BIKE_LABELS = dict(BIKE_CHOICES)


def _to_float(value, fallback=0.0):
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return fallback


def _to_int(value, fallback=0):
    try:
        return max(0, int(value))
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
    per_trip = round(total / s.trips, 2) if s.trips else None
    return {
        'id': s.id,
        'shift_date': s.shift_date,
        'shift_start': s.shift_start,
        'shift_end': s.shift_end,
        'hours_worked': s.hours_worked,
        'tips_cash': s.tips_cash or 0,
        'tips_online': s.tips_online or 0,
        'deliveries': s.deliveries or 0,
        'trips': s.trips or 0,
        'bike_size': s.bike_size,
        'bike_label': BIKE_LABELS.get(s.bike_size, '—'),
        'weather': s.weather,
        'weather_label': WEATHER_LABELS.get(s.weather, '—'),
        'notes': s.notes,
        'total': round(total, 2),
        'per_hour': per_hour,
        'per_delivery': per_delivery,
        'per_trip': per_trip,
    }


def _aggregate(rows):
    shift_count = len(rows)
    total_cash = sum(r['tips_cash'] for r in rows)
    total_online = sum(r['tips_online'] for r in rows)
    total_tips = total_cash + total_online
    total_hours = sum(r['hours_worked'] or 0 for r in rows)
    total_deliveries = sum(r['deliveries'] for r in rows)
    total_trips = sum(r['trips'] for r in rows)
    return {
        'shift_count': shift_count,
        'total_cash': round(total_cash, 2),
        'total_online': round(total_online, 2),
        'total_tips': round(total_tips, 2),
        'total_hours': round(total_hours, 2),
        'total_deliveries': total_deliveries,
        'total_trips': total_trips,
        'avg_per_shift': round(total_tips / shift_count, 2) if shift_count else None,
        'avg_per_hour': round(total_tips / total_hours, 2) if total_hours else None,
        'avg_per_delivery': round(total_tips / total_deliveries, 2) if total_deliveries else None,
        'avg_per_trip': round(total_tips / total_trips, 2) if total_trips else None,
    }


WEEKDAY_LABELS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
WEEKDAY_SHORT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
MONTH_LABELS = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

TIME_BUCKET_ORDER = ['morning', 'afternoon', 'evening', 'night']
TIME_BUCKET_LABELS = {
    'morning': 'Vormittag (vor 14 Uhr)',
    'afternoon': 'Nachmittag (14–18 Uhr)',
    'evening': 'Abend (18–22 Uhr)',
    'night': 'Nacht (nach 22 Uhr)',
}


TIME_BUCKET_BOUNDARIES = [(0, 14, 'morning'), (14, 18, 'afternoon'), (18, 22, 'evening'), (22, 24, 'night')]


def _time_bucket_shares(shift_start, hours_worked):
    """Hours-in-bucket for a shift starting at shift_start and lasting hours_worked
    hours, split across every Vormittag/Nachmittag/Abend/Nacht window it actually
    crosses (wraps correctly past midnight). Returns None if start time is unknown."""
    if shift_start is None or not hours_worked:
        return None
    remaining = hours_worked * 60
    cursor = shift_start.hour * 60 + shift_start.minute
    shares = {}
    while remaining > 0:
        cursor_in_day = cursor % 1440
        cursor_hour = cursor_in_day / 60
        for start_h, end_h, key in TIME_BUCKET_BOUNDARIES:
            if start_h <= cursor_hour < end_h:
                minutes_to_boundary = end_h * 60 - cursor_in_day
                chunk = min(remaining, minutes_to_boundary)
                shares[key] = shares.get(key, 0) + chunk / 60
                cursor += chunk
                remaining -= chunk
                break
    return shares


def _time_breakdown(rows):
    """Like _group_breakdown, but a shift crossing a time-of-day boundary contributes
    to every bucket it spans, prorated by time-in-bucket (uniform-earning-rate
    assumption) rather than being credited whole to its start bucket. `shift_count`
    per bucket counts shifts that touched that bucket at all, so it can legitimately
    sum to more than the total shift count when shifts cross boundaries."""
    totals = {k: {'tips': 0.0, 'hours': 0.0, 'deliveries': 0.0, 'shift_ids': set()} for k in TIME_BUCKET_ORDER}
    for r in rows:
        shares = _time_bucket_shares(r['shift_start'], r['hours_worked'])
        if not shares:
            continue
        for key, hrs in shares.items():
            frac = hrs / r['hours_worked']
            b = totals[key]
            b['tips'] += r['total'] * frac
            b['hours'] += hrs
            b['deliveries'] += r['deliveries'] * frac
            b['shift_ids'].add(r['id'])
    entries = []
    for key in TIME_BUCKET_ORDER:
        b = totals[key]
        if not b['shift_ids']:
            continue
        entries.append({
            'label': TIME_BUCKET_LABELS[key],
            'shift_count': len(b['shift_ids']),
            'total_hours': round(b['hours'], 2),
            'avg_per_hour': round(b['tips'] / b['hours'], 2) if b['hours'] else None,
            'avg_per_delivery': round(b['tips'] / b['deliveries'], 2) if b['deliveries'] else None,
        })
    return entries


def _group_breakdown(rows, key_func, label_func, order=None):
    groups = {}
    for r in rows:
        k = key_func(r)
        if k is None:
            continue
        groups.setdefault(k, []).append(r)
    entries = []
    for k, group_rows in groups.items():
        agg = _aggregate(group_rows)
        agg['label'] = label_func(k)
        entries.append((k, agg))
    if order is not None:
        order_index = {k: i for i, k in enumerate(order)}
        entries.sort(key=lambda e: order_index.get(e[0], len(order)))
    else:
        entries.sort(key=lambda e: e[1]['avg_per_hour'] if e[1]['avg_per_hour'] is not None else -1, reverse=True)
    return [agg for _, agg in entries]


def _build_month_calendar(year, month, rows, today, week_start):
    rows_by_date = {}
    for r in rows:
        if r['shift_date']:
            rows_by_date.setdefault(r['shift_date'], []).append(r)

    week_end = week_start + dt.timedelta(days=6)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        week_cells = []
        for day in week:
            if day == 0:
                week_cells.append(None)
                continue
            d = dt.date(year, month, day)
            day_rows = rows_by_date.get(d, [])
            cell = {
                'date': d,
                'iso': d.isoformat(),
                'day': day,
                'weekday_label': WEEKDAY_LABELS[d.weekday()],
                'rows': day_rows,
                'is_today': d == today,
                'is_future': d > today,
                'is_current_week': week_start <= d <= week_end,
                'is_month_best': False,
                'is_high_intensity': False,
                'per_hour': None,
                'total': None,
            }
            if day_rows:
                total = sum(r['total'] for r in day_rows)
                hours = sum(r['hours_worked'] or 0 for r in day_rows)
                cell['total'] = round(total, 2)
                cell['per_hour'] = round(total / hours, 2) if hours else None
            week_cells.append(cell)
        weeks.append(week_cells)
    return weeks


@tips_bp.route('/tips')
@login_required
def tips_dashboard():
    shifts = DeliveryShift.query.order_by(DeliveryShift.shift_date.desc(), DeliveryShift.id.desc()).all()
    rows = [_shift_row(s) for s in shifts]

    today = dt.date.today()
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    try:
        cal_year = int(request.args.get('y', today.year))
        cal_month = int(request.args.get('m', today.month))
        dt.date(cal_year, cal_month, 1)
    except (ValueError, TypeError):
        cal_year, cal_month = today.year, today.month

    calendar_weeks = _build_month_calendar(cal_year, cal_month, rows, today, week_start)
    month_rates = [c['per_hour'] for week in calendar_weeks for c in week if c and c['per_hour'] is not None]
    calendar_max_rate = max(month_rates) if month_rates else 1
    if month_rates:
        for week in calendar_weeks:
            for c in week:
                if c and c['per_hour'] is not None:
                    if c['per_hour'] == calendar_max_rate:
                        c['is_month_best'] = True
                    if c['per_hour'] / calendar_max_rate > 0.55:
                        c['is_high_intensity'] = True

    prev_month, prev_year = (12, cal_year - 1) if cal_month == 1 else (cal_month - 1, cal_year)
    next_month, next_year = (1, cal_year + 1) if cal_month == 12 else (cal_month + 1, cal_year)

    is_current_month = (cal_year == today.year and cal_month == today.month)

    viewed_month_stats = _aggregate([
        r for r in rows if r['shift_date'] and r['shift_date'].year == cal_year and r['shift_date'].month == cal_month
    ])

    default_cell = None
    focus_day = request.args.get('d', type=int)
    if focus_day:
        for week in calendar_weeks:
            for c in week:
                if c and c['day'] == focus_day:
                    default_cell = c

    tabbable_iso = default_cell['iso'] if default_cell else None
    if not tabbable_iso and is_current_month:
        for week in calendar_weeks:
            for c in week:
                if c and c['is_today']:
                    tabbable_iso = c['iso']
    if not tabbable_iso:
        for week in calendar_weeks:
            for c in week:
                if c:
                    tabbable_iso = c['iso']
                    break
            if tabbable_iso:
                break

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
    rows_with_trip_rate = [r for r in rows if r['per_trip'] is not None]
    best_trip_rate = sorted(rows_with_trip_rate, key=lambda r: r['per_trip'], reverse=True)[:5]
    worst_trip_rate = sorted(rows_with_trip_rate, key=lambda r: r['per_trip'])[:5]

    breakdown_weekday = _group_breakdown(
        rows,
        lambda r: r['shift_date'].weekday() if r['shift_date'] else None,
        lambda k: WEEKDAY_LABELS[k],
        order=list(range(7)),
    )
    breakdown_time = _time_breakdown(rows)
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
        best_trip_rate=best_trip_rate,
        worst_trip_rate=worst_trip_rate,
        breakdown_weekday=breakdown_weekday,
        breakdown_time=breakdown_time,
        breakdown_weather=breakdown_weather,
        breakdown_bike=breakdown_bike,
        chart_labels=chart_labels,
        chart_totals=chart_totals,
        chart_rates=chart_rates,
        bike_choices=BIKE_CHOICES,
        weather_choices=WEATHER_CHOICES,
        calendar_weeks=calendar_weeks,
        calendar_year=cal_year,
        calendar_month=cal_month,
        calendar_month_label=MONTH_LABELS[cal_month - 1],
        calendar_max_rate=calendar_max_rate,
        viewed_month_stats=viewed_month_stats,
        weekday_short=WEEKDAY_SHORT,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        is_current_month=is_current_month,
        default_cell=default_cell,
        tabbable_iso=tabbable_iso,
        today=today,
    )


@tips_bp.route('/tips/add', methods=['POST'])
@login_required
def tips_add():
    date_str = request.form.get('shift_date', '').strip()
    try:
        shift_date = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Ungültiges Datum — Schicht wurde nicht gespeichert.', 'error')
        return redirect(url_for('tips.tips_dashboard'))

    shift = DeliveryShift(
        shift_date=shift_date,
        shift_start=_to_time(request.form.get('shift_start', '')),
        shift_end=_to_time(request.form.get('shift_end', '')),
        hours_worked=_to_float(request.form.get('hours_worked', '')),
        tips_cash=_to_float(request.form.get('tips_cash', '')),
        tips_online=_to_float(request.form.get('tips_online', '')),
        deliveries=_to_int(request.form.get('deliveries', '')),
        trips=_to_int(request.form.get('trips', '')),
        bike_size=request.form.get('bike_size') if request.form.get('bike_size') in dict(BIKE_CHOICES) else None,
        weather=request.form.get('weather') if request.form.get('weather') in dict(WEATHER_CHOICES) else None,
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(shift)
    db.session.commit()

    max_rate = db.session.query(
        func.max(
            (func.coalesce(DeliveryShift.tips_cash, 0) + func.coalesce(DeliveryShift.tips_online, 0))
            / DeliveryShift.hours_worked
        )
    ).filter(DeliveryShift.hours_worked > 0).scalar()
    new_rate = ((shift.tips_cash or 0) + (shift.tips_online or 0)) / shift.hours_worked if shift.hours_worked else None
    is_new_best = new_rate is not None and max_rate is not None and new_rate >= max_rate

    if is_new_best:
        flash('Neue Bestleistung — %.2f €/h!' % new_rate, 'best')
    else:
        flash('Schicht gespeichert.', 'success')
    return redirect(url_for('tips.tips_dashboard', y=shift_date.year, m=shift_date.month, d=shift_date.day))


@tips_bp.route('/tips/<int:shift_id>/update', methods=['POST'])
@login_required
def tips_update(shift_id):
    shift = db.get_or_404(DeliveryShift, shift_id)

    date_str = request.form.get('shift_date', '').strip()
    try:
        shift.shift_date = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Ungültiges Datum — restliche Änderungen wurden trotzdem gespeichert.', 'error')

    shift.shift_start = _to_time(request.form.get('shift_start', ''))
    shift.shift_end = _to_time(request.form.get('shift_end', ''))
    shift.hours_worked = _to_float(request.form.get('hours_worked', ''), shift.hours_worked)
    shift.tips_cash = _to_float(request.form.get('tips_cash', ''), shift.tips_cash)
    shift.tips_online = _to_float(request.form.get('tips_online', ''), shift.tips_online)
    shift.deliveries = _to_int(request.form.get('deliveries', ''), shift.deliveries)
    shift.trips = _to_int(request.form.get('trips', ''), shift.trips)
    bike = request.form.get('bike_size')
    shift.bike_size = bike if bike in dict(BIKE_CHOICES) else None
    weather = request.form.get('weather')
    shift.weather = weather if weather in dict(WEATHER_CHOICES) else None
    shift.notes = request.form.get('notes', '').strip() or None

    db.session.commit()
    flash('Schicht aktualisiert.', 'success')
    return redirect(url_for('tips.tips_dashboard', y=shift.shift_date.year, m=shift.shift_date.month, d=shift.shift_date.day))


@tips_bp.route('/tips/<int:shift_id>/delete', methods=['POST'])
@login_required
def tips_delete(shift_id):
    shift = db.get_or_404(DeliveryShift, shift_id)
    year, month, day = shift.shift_date.year, shift.shift_date.month, shift.shift_date.day
    session['last_deleted'] = {
        'shift_date': shift.shift_date.isoformat(),
        'shift_start': shift.shift_start.isoformat() if shift.shift_start else None,
        'shift_end': shift.shift_end.isoformat() if shift.shift_end else None,
        'hours_worked': shift.hours_worked,
        'tips_cash': shift.tips_cash,
        'tips_online': shift.tips_online,
        'deliveries': shift.deliveries,
        'trips': shift.trips,
        'bike_size': shift.bike_size,
        'weather': shift.weather,
        'notes': shift.notes,
    }
    db.session.delete(shift)
    db.session.commit()
    undo_url = url_for('tips.tips_undo_delete')
    flash(
        'Schicht gelöscht. '
        f'<form method="post" action="{undo_url}" class="flash-undo-form">'
        '<button type="submit" class="flash-undo-btn">Rückgängig</button>'
        '</form>',
        'success',
    )
    return redirect(url_for('tips.tips_dashboard', y=year, m=month, d=day))


@tips_bp.route('/tips/undo-delete', methods=['POST'])
@login_required
def tips_undo_delete():
    data = session.pop('last_deleted', None)
    if not data:
        flash('Nichts zum Wiederherstellen.', 'error')
        return redirect(url_for('tips.tips_dashboard'))

    shift = DeliveryShift(
        shift_date=dt.date.fromisoformat(data['shift_date']),
        shift_start=dt.time.fromisoformat(data['shift_start']) if data['shift_start'] else None,
        shift_end=dt.time.fromisoformat(data['shift_end']) if data['shift_end'] else None,
        hours_worked=data['hours_worked'],
        tips_cash=data['tips_cash'],
        tips_online=data['tips_online'],
        deliveries=data['deliveries'],
        trips=data['trips'],
        bike_size=data['bike_size'],
        weather=data['weather'],
        notes=data['notes'],
    )
    db.session.add(shift)
    db.session.commit()
    flash('Schicht wiederhergestellt.', 'success')
    return redirect(url_for(
        'tips.tips_dashboard', y=shift.shift_date.year, m=shift.shift_date.month, d=shift.shift_date.day,
    ))
