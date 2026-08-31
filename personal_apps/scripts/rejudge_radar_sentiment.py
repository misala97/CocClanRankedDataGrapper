# personal_apps/scripts/rejudge_radar_sentiment.py
"""Rejudge retained high-confidence mentions with the current v2 prompt.

The live pass drains the NEWEST unjudged mentions every ten minutes; this
drains HISTORY behind it -- everything whose sentiment_prompt_version is
NULL (never judged, or judged by the retired four-way pass) or differs
from the current binding version. Idempotent and resumable by
construction: a judged mention leaves the selection, a failed batch stays
in it, and re-running after any interruption simply continues.

Never erases a valid older answer except through apply_judgments'
replacement rules; every answer lands in the append-only judgment history
and books spend through the same meter the live pass uses, so the rejudge
cost is visible on the board like any other.

Read-only until --apply. Run from personal_apps/:

    python -m scripts.rejudge_radar_sentiment              # report + cost
    python -m scripts.rejudge_radar_sentiment --apply      # judge one slice
    python -m scripts.rejudge_radar_sentiment --apply --limit 10000
"""
import argparse
import datetime as dt
import sys

sys.path.insert(0, '.')  # noqa: E402

import sqlalchemy as sa  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import llm_sentiment  # noqa: E402
from models import RadarMention, RadarPost, RadarSentimentJudgment  # noqa: E402

# When the judgment history is empty (first run after activation), the
# projection falls back to these measured-order-of-magnitude figures and
# says so in the printout.
FALLBACK_INPUT_PER_MENTION = 2000
FALLBACK_OUTPUT_PER_MENTION = 60


def rejudge_backlog(limit):
    """Oldest-first: the newest mentions are the live pass's job."""
    return (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.confidence == 'high',
                    sa.or_(RadarMention.sentiment_prompt_version.is_(None),
                           RadarMention.sentiment_prompt_version
                           != llm_sentiment.PROMPT_VERSION))
            .order_by(RadarPost.created_utc.asc())
            .limit(limit).all())


def backlog_count():
    return (db.session.query(sa.func.count(RadarMention.id))
            .filter(RadarMention.confidence == 'high',
                    sa.or_(RadarMention.sentiment_prompt_version.is_(None),
                           RadarMention.sentiment_prompt_version
                           != llm_sentiment.PROMPT_VERSION))
            .scalar() or 0)


def measured_tokens_per_mention(days=7):
    """(input, output) per mention off the last week of judgment history.

    Returns None when the history is empty -- the caller falls back to the
    stated constants rather than silently inventing a measurement.
    """
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    row = (db.session.query(
        sa.func.count(RadarSentimentJudgment.id),
        sa.func.sum(RadarSentimentJudgment.input_tokens),
        sa.func.sum(RadarSentimentJudgment.output_tokens))
        .filter(RadarSentimentJudgment.created_utc >= since).one())
    count, input_sum, output_sum = int(row[0] or 0), row[1], row[2]
    if not count:
        return None
    return (float(input_sum or 0) / count, float(output_sum or 0) / count)


def projected_cost_usd(mentions, per_mention):
    """Micro-accurate enough for a go/no-go printout."""
    from features.radar import spend
    input_per, output_per = per_mention
    micros = spend.cost_micros(llm_sentiment.PRIMARY_MODEL,
                               int(mentions * input_per),
                               int(mentions * output_per))
    return (micros or 0) / 1_000_000.0


def run(apply=False, limit=2000):
    with app.app_context():
        total = backlog_count()
        measured = measured_tokens_per_mention()
        if measured is None:
            per_mention = (FALLBACK_INPUT_PER_MENTION,
                           FALLBACK_OUTPUT_PER_MENTION)
            basis = 'assumed %d in / %d out per mention (no history yet)' % \
                per_mention
        else:
            per_mention = measured
            basis = 'measured %.0f in / %.0f out per mention (7d history)' % \
                per_mention
        print('rejudge backlog: %d mentions behind prompt %s'
              % (total, llm_sentiment.PROMPT_VERSION))
        print('projected full-backlog cost: $%.2f (%s)'
              % (projected_cost_usd(total, per_mention), basis))

        if not apply:
            print('dry run -- nothing judged, pass --apply')
            return 0

        judged_total = 0
        while judged_total < limit:
            slice_limit = min(llm_sentiment.PASS_LIMIT, limit - judged_total)
            rows = rejudge_backlog(slice_limit)
            if not rows:
                break
            meter = {'calls': 0, 'input': 0, 'output': 0}

            def count(usage):
                meter['calls'] += 1
                meter['input'] += getattr(usage, 'input_tokens', 0) or 0
                meter['output'] += getattr(usage, 'output_tokens', 0) or 0

            judgments = llm_sentiment.judge(
                llm_sentiment.items_for(rows), on_usage=count)
            from features.radar import spend
            spend.record(llm_sentiment.PRIMARY_MODEL, calls=meter['calls'],
                         input_tokens=meter['input'],
                         output_tokens=meter['output'])
            written = llm_sentiment.apply_judgments(
                rows, judgments, stage='primary',
                model=llm_sentiment.PRIMARY_MODEL)
            changed = llm_sentiment._sync_eligibility(rows, judgments)
            db.session.commit()
            llm_sentiment._rebuild_corrected(changed)
            judged_total += written
            print('  slice: %d judged, %d remaining'
                  % (written, backlog_count()))
            if not written:
                # Every batch in the slice failed; stop rather than spin.
                print('  no batch succeeded -- stopping, rerun to retry')
                break
        print('judged %d mentions this run' % judged_total)
        return judged_total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='judge the backlog (default: report only)')
    parser.add_argument('--limit', type=int, default=2000,
                        help='max mentions this invocation (default 2000)')
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == '__main__':
    main()
