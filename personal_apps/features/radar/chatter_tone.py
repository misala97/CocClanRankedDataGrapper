"""Recent, evidence-backed tone partitions for the detail chatter chart.

The detail chart's totals come from durable source buckets.  Tone evidence is
short-lived event/post/mention data, so this module treats the bucket total as
authoritative and only colours the part that can be reconciled to retained
events.  It deliberately has no write path or historical backfill.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource, RadarMention, RadarMentionEvent, RadarPost

from . import config
from .config import expand_sources_for_history


TONE_CATEGORIES = ('bullish', 'bearish', 'neutral', 'unjudged', 'unavailable')


def classify_recorded_tone(*, attitude, llm_sentiment, lexicon_sentiment):
    """Classify only recorded verdicts; raw wording scores never colour bars."""
    if attitude == 'positive':
        return 'bullish'
    if attitude == 'negative':
        return 'bearish'
    if attitude in {'mixed', 'none'}:
        return 'neutral'
    if llm_sentiment == 'bullish':
        return 'bullish'
    if llm_sentiment == 'bearish':
        return 'bearish'
    if llm_sentiment == 'neutral':
        return 'neutral'
    # 'unclear', a missing verdict, and a lexicon-only score are unresolved.
    return 'unjudged'


def _empty_counts():
    return {key: 0 for key in TONE_CATEGORIES}


def _as_count(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def reconcile_slot(*, total, source_bins):
    """Make one exhaustive partition while preserving the chart total.

    A missing source row is a missing remainder, not permission to shrink the
    denominator.  A malformed or overfull source partition is conservatively
    rendered as unavailable for the whole displayed total.
    """
    if total is None:
        return None
    total = _as_count(total)
    if total is None:
        return None
    result = _empty_counts()
    if total == 0:
        result['status'] = 'complete'
        return result

    observed_total = 0
    for source_bin in source_bins:
        source_total = _as_count(source_bin.get('total'))
        values = {key: _as_count(source_bin.get(key))
                  for key in TONE_CATEGORIES}
        if source_total is None or any(value is None for value in values.values()):
            result['unavailable'] = total
            result['status'] = 'unavailable'
            return result
        categories_total = sum(values[key] for key in TONE_CATEGORIES)
        observed_total += source_total
        if categories_total != source_total:
            result['unavailable'] += source_total
        else:
            for key in TONE_CATEGORIES:
                result[key] += values[key]

    if observed_total > total:
        result = _empty_counts()
        result['unavailable'] = total
    else:
        result['unavailable'] += total - observed_total

    classified = sum(result[key] for key in TONE_CATEGORIES)
    if classified != total:
        result = _empty_counts()
        result['unavailable'] = total
    result['status'] = (
        'complete' if result['unavailable'] == 0 else
        'unavailable' if result['unavailable'] == total else 'partial')
    return result


def _naive_utc(value):
    if value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def _chart_start(chart):
    if isinstance(chart.start, dt.datetime):
        return _naive_utc(chart.start)
    return dt.datetime.combine(chart.start, dt.time.min)


def _slot_index(when, start, step_minutes, slots):
    offset = (_naive_utc(when) - start).total_seconds() / 60
    if offset < 0:
        return None
    index = int(offset // step_minutes)
    return index if index < slots else None


def _iso_z(value):
    return _naive_utc(value).isoformat(timespec='seconds') + 'Z'


def _event_partitions(ticker, sources, lower, upper):
    """Return one scalar aggregate per retained source/bucket."""
    event = RadarMentionEvent
    post = RadarPost
    mention = RadarMention
    eligibility_conflict = sa.or_(
        mention.sentiment_relevance == 'irrelevant',
        mention.sentiment_content_origin == 'broadcast_or_automated',
    )
    event_rows = (db.session.query(
        event.id.label('event_id'),
        event.source.label('source'),
        event.bucket_start.label('bucket_start'),
        sa.func.count(mention.id).label('mention_rows'),
        sa.func.max(mention.sentiment_attitude).label('attitude'),
        sa.func.max(mention.llm_sentiment).label('llm_sentiment'),
        sa.func.max(mention.lexicon_sentiment).label('lexicon_sentiment'),
        sa.func.sum(sa.case((eligibility_conflict, 1), else_=0))
        .label('eligibility_conflicts'),
    ).outerjoin(
        post,
        sa.and_(post.source == event.source,
                post.external_id == event.external_id),
    ).outerjoin(
        mention,
        sa.and_(mention.post_id == post.id, mention.ticker == event.ticker),
    ).filter(
        event.ticker == ticker,
        event.source.in_(list(sources)),
        event.bucket_start >= lower,
        event.bucket_start < upper,
        sa.or_(event.confidence == 'high', event.promoted.is_(True)),
        sa.or_(event.counts_as_human_chatter.is_(None),
               event.counts_as_human_chatter.is_(True)),
    ).group_by(event.id, event.source, event.bucket_start).subquery())

    valid = sa.and_(event_rows.c.mention_rows == 1,
                    event_rows.c.eligibility_conflicts == 0)
    classification = sa.case(
        (sa.and_(valid, event_rows.c.attitude == 'positive'), 'bullish'),
        (sa.and_(valid, event_rows.c.attitude == 'negative'), 'bearish'),
        (sa.and_(valid, event_rows.c.attitude.in_(['mixed', 'none'])), 'neutral'),
        (sa.and_(valid, event_rows.c.llm_sentiment == 'bullish'), 'bullish'),
        (sa.and_(valid, event_rows.c.llm_sentiment == 'bearish'), 'bearish'),
        (sa.and_(valid, event_rows.c.llm_sentiment == 'neutral'), 'neutral'),
        (valid, 'unjudged'),
        else_='unavailable',
    )
    return db.session.query(
        event_rows.c.source,
        event_rows.c.bucket_start,
        sa.func.count(event_rows.c.event_id).label('total'),
        sa.func.sum(event_rows.c.eligibility_conflicts).label('eligibility_conflicts'),
        *[
            sa.func.sum(sa.case((classification == category, 1), else_=0))
            .label(category)
            for category in TONE_CATEGORIES
        ],
    ).group_by(event_rows.c.source, event_rows.c.bucket_start).all()


def chart_tone(ticker, sources, chart, *, now):
    """Return version 1 tone envelope aligned exactly with ``chart.chatter``."""
    now = _naive_utc(now)
    start = _chart_start(chart)
    slots = len(chart.chatter)
    end = start + dt.timedelta(minutes=chart.step_minutes * slots)
    retained_from = max(start, now - dt.timedelta(
        hours=config.MENTION_EVENT_RETENTION_HOURS))
    selected_sources = expand_sources_for_history(sources)

    source_rows = (db.session.query(
        RadarBucketSource.source,
        RadarBucketSource.bucket_start,
        RadarBucketSource.mention_count,
    ).filter(
        RadarBucketSource.ticker == ticker,
        RadarBucketSource.source.in_(list(selected_sources)),
        RadarBucketSource.bucket_start >= retained_from,
        RadarBucketSource.bucket_start < end,
    ).all()) if selected_sources else []

    source_bins_by_slot = defaultdict(list)
    for source, bucket_start, mention_count in source_rows:
        index = _slot_index(bucket_start, start, chart.step_minutes, slots)
        if index is None:
            continue
        total = _as_count(mention_count)
        if total is None:
            source_bins_by_slot[index].append({
                'total': None, '_source': source,
                '_bucket_start': bucket_start,
            })
            continue
        bucket = {
            'total': total, 'bullish': 0, 'bearish': 0, 'neutral': 0,
            'unjudged': 0, 'unavailable': 0,
            '_source': source, '_bucket_start': bucket_start,
        }
        if _naive_utc(bucket_start) < retained_from:
            bucket['unavailable'] = total
        source_bins_by_slot[index].append(bucket)

    event_lower = max(start, retained_from)
    event_upper = min(end, now)
    # The event aggregate is keyed by source and bucket, so update the bins in
    # a second pass with their identities. This keeps source A mismatches from
    # cancelling source B's valid contribution.
    if event_lower < event_upper and selected_sources:
        aggregates = _event_partitions(ticker, selected_sources,
                                        event_lower, event_upper)
        aggregate_map = {(row.source, row.bucket_start): row
                         for row in aggregates}
        for source, bucket_start, mention_count in source_rows:
            index = _slot_index(bucket_start, start, chart.step_minutes, slots)
            if index is None or _naive_utc(bucket_start) < retained_from:
                continue
            source_bin = next((item for item in source_bins_by_slot[index]
                               if item.get('_source') == source and
                               item.get('_bucket_start') == bucket_start), None)
            if source_bin is None:
                continue
            row = aggregate_map.get((source, bucket_start))
            if row is None or row.eligibility_conflicts:
                source_bin.update(total=_as_count(mention_count), bullish=0,
                                  bearish=0, neutral=0, unjudged=0,
                                  unavailable=_as_count(mention_count))
            else:
                source_bin.update(total=_as_count(mention_count), **{
                    key: _as_count(getattr(row, key))
                    for key in TONE_CATEGORIES
                })

    tone_slots = [reconcile_slot(
        total=total,
        source_bins=[{key: value for key, value in item.items()
                      if not key.startswith('_')}
                     for item in source_bins_by_slot[index]],
    ) for index, total in enumerate(chart.chatter)]

    return {
        'version': 1,
        'basis': 'recorded-judgments',
        'calculated_at': _iso_z(now),
        'retained_from': _iso_z(retained_from),
        'slots': tone_slots,
    }
