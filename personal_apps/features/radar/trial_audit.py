# personal_apps/features/radar/trial_audit.py
"""What the trial has to demonstrate, and the arithmetic that decides it.

Pure: no database, no model, no files. It takes labelled rows and two sets
of predictions and returns a verdict, so the rules can be read and tested
without arranging a trial.

Two things here are deliberate and easy to get wrong the other way.

**Bounds, not point estimates.** A trial that cannot demonstrate its bound
with the sample it drew fails. It does not get to pass on a favourable
point estimate with a wide interval around it -- that is how 3-versus-1
wrong deletions out of 200 became an argument for shipping once already.

**Only harm stops the trial.** One criterion decides pass or fail: does it
delete real posts too often. The comparisons against the incumbent are
measured and reported, and they decide nothing here -- because there is no
incumbent to fall back to. The paid judge stopped running on 2026-09-03
when the credits ran out, so the alternative to this judge is no judge at
all, and switching a working one off for losing to a model that cannot run
would leave the board strictly worse. What the incumbent comparison is FOR
is the later decision to expand -- judging every mention instead of the
gated fifth, or letting tone reach the board -- and that decision is not
this one.

**Tone is reported and never gates.** The trial's whole design is that
encoder tone is not written, so tone cannot pass or fail it. The tone
section exists to say whether a LATER, separately reviewed change could be
considered, and meeting it authorises nothing on its own.
"""
import math

# The two-sided 95% normal quantile, written out rather than imported from
# scipy: this number decides whether a trial passes, and it should be
# readable in the diff that changes it.
Z = 1.959963984540054

# The only bar that stops the trial: of what it deleted, how much really was
# junk. Deleting real chatter is the one failure that leaves the board worse
# than no judging at all, which is what makes this the harm test.
REMOVAL_PRECISION_FLOOR = 0.93

# Measured against the incumbent and REPORTED, never gating the trial. They
# are the bar for a later decision to expand, not for whether to keep
# running. Fixed here before any evaluation exists, as everything else is.
REMOVAL_PRECISION_TOLERANCE = 0.03
AGREEMENT_TOLERANCE = 0.02

# Tone qualification only. Never part of the trial's own verdict.
REVERSAL_CEILING = 0.05
TONE_AGREEMENT_TOLERANCE = 0.02
SHADOW_DAYS_REQUIRED = 7

REMOVING_RELEVANCE = 'irrelevant'
REMOVING_ORIGIN = 'broadcast_or_automated'
DIRECTIONAL = ('positive', 'negative')
UNDIRECTED = ('mixed', 'none')


class AuditError(Exception):
    """The audit cannot be evaluated as presented."""


def wilson_interval(successes, total):
    """The Wilson score interval for a proportion, at 95%.

    Wilson rather than the normal approximation because these proportions
    live near 1 with denominators in the hundreds, where the normal
    interval runs past 1 and stops meaning anything.

    A zero denominator raises. It is not a proportion of anything, and
    every gate that could reach one treats it as a failure rather than
    quietly reading it as perfect.
    """
    if total is None or total <= 0:
        raise AuditError('no denominator: there is nothing to be a '
                         'proportion of')
    if successes is None or successes < 0 or successes > total:
        raise AuditError('%r successes out of %r is not possible'
                         % (successes, total))
    proportion = successes / total
    z2 = Z * Z
    denominator = 1 + z2 / total
    centre = (proportion + z2 / (2 * total)) / denominator
    radius = (Z / denominator) * math.sqrt(
        proportion * (1 - proportion) / total + z2 / (4 * total * total))
    return {'point': proportion, 'successes': successes, 'total': total,
            'lower': centre - radius, 'upper': centre + radius}


def removes(verdict):
    """Whether a verdict takes the mention out of the counts.

    Either field alone is enough, which is why removal precision has to be
    measured on the union rather than on relevance by itself.
    """
    return (verdict.get('relevance') == REMOVING_RELEVANCE
            or verdict.get('content_origin') == REMOVING_ORIGIN)


def removal_precision(predictions, reference):
    """Of what this backend chose to remove, how much really was junk.

    The denominator is its OWN predicted removals -- not the reference's,
    and not the sample. A backend that removes nothing has no precision to
    report, and that is a failed criterion rather than a perfect score.
    """
    predicted = [key for key, verdict in predictions.items()
                 if removes(verdict)]
    confirmed = [key for key in predicted if removes(reference[key])]
    return wilson_interval(len(confirmed), len(predicted))


def field_agreement(predictions, reference, field):
    """Exact agreement on one field, over the COMPLETE sampled set.

    The denominator is every row, including ones this backend failed to
    answer: a missing prediction is a disagreement, not an excused absence.
    Shrinking the denominator to what a backend managed to answer is how a
    coverage problem disappears into a quality number.
    """
    agreed = sum(1 for key, truth in reference.items()
                 if predictions.get(key, {}).get(field) == truth.get(field))
    return wilson_interval(agreed, len(reference))


def reversal_rate(predictions, reference):
    """Predicting the opposite polarity of a directional reference row.

    Denominator: reference rows that are positive or negative. `mixed` and
    `none` cannot be reversed, so counting them would dilute the rate that
    matters -- this is the error a reader sees as the wrong colour.
    """
    directional = {key: truth for key, truth in reference.items()
                   if truth.get('attitude') in DIRECTIONAL}
    reversed_count = 0
    for key, truth in directional.items():
        predicted = predictions.get(key, {}).get('attitude')
        if predicted in DIRECTIONAL and predicted != truth['attitude']:
            reversed_count += 1
    return wilson_interval(reversed_count, len(directional))


def mixed_none_confusion(predictions, reference):
    """Reference `mixed` called `none`, or the reverse.

    Its own criterion because the two mean opposite things to a reader:
    `mixed` is a room arguing, `none` is a room saying nothing about the
    company at all, and the board's phrasing leans on the difference.
    """
    slice_ = {key: truth for key, truth in reference.items()
              if truth.get('attitude') in UNDIRECTED}
    confused = 0
    for key, truth in slice_.items():
        predicted = predictions.get(key, {}).get('attitude')
        if predicted in UNDIRECTED and predicted != truth['attitude']:
            confused += 1
    return wilson_interval(confused, len(slice_))


def _criterion(name, passed, detail, gates=True):
    """One measured rule. `gates` says whether it can fail the trial.

    Everything is measured and reported; only the harm test decides.
    """
    return {'criterion': name, 'passed': bool(passed), 'gates': bool(gates),
            **detail}


def is_verdict(value):
    """A dict carrying every field with an allowed value.

    Anything else -- an empty dict, a missing field, a value outside the
    enum -- is not a verdict and is never scored as one. An empty label
    against an empty prediction used to agree on every field, which is
    how invalid rows could count as complete coverage and still pass.
    """
    from .llm_sentiment import _FIELD_ENUMS
    return isinstance(value, dict) and all(
        value.get(field) in allowed for field, allowed in _FIELD_ENUMS.items())


def evaluate_trial_audit(bundle):
    """The verdict, and every number behind it.

    `bundle` carries `reference`, `encoder`, `haiku` -- each {key: verdict}
    -- and, from the real audit, `sample`: the frozen list of sampled keys,
    which is the denominator. Without it the reference's keys are the
    sample, which is what the pure tests use.

    Returns a report. ONE gate decides `passed`: removal precision on the
    encoder's Wilson LOWER bound against the absolute floor (spec 7.1,
    amended 2026-09-06). Relevance and content-origin agreement against
    the incumbent's point estimate are measured and reported and feed
    `expansion_ready`; they cannot stop the trial. Tone is computed and
    reported and takes no part in either.

    Coverage is a validity check over the whole sample: every sampled key
    needs a valid label AND a valid prediction from both backends, and a
    missing or invalid one fails the audit outright -- a denominator is
    never quietly shrunk to what was answered.
    """
    reference = bundle.get('reference') or {}
    encoder = bundle.get('encoder') or {}
    haiku = bundle.get('haiku') or {}
    sample = bundle.get('sample')
    keys = list(sample) if sample is not None else list(reference)
    if not keys:
        raise AuditError('the audit has no reference labels')

    missing = {}
    for key in keys:
        for what, side in (('label', reference), ('encoder', encoder),
                           ('haiku', haiku)):
            if not is_verdict(side.get(key)):
                missing.setdefault(key, []).append(what)
    coverage_ok = not missing
    # Only VALID verdicts on SAMPLED keys are scored. An invalid one has
    # already failed coverage above, and must not also be scored as an
    # agreement; a key outside the sample is not part of this audit.
    wanted = set(keys)
    reference = {key: value for key, value in reference.items()
                 if key in wanted and is_verdict(value)}
    encoder = {key: value for key, value in encoder.items()
               if key in reference and is_verdict(value)}
    haiku = {key: value for key, value in haiku.items()
             if key in reference and is_verdict(value)}
    if not reference:
        raise AuditError('none of the %d sampled rows carries a valid label'
                         % len(keys))

    # A backend that removed NOTHING has no precision to report, and that
    # fails the criterion rather than aborting the audit or reading as a
    # perfect score. The same is true of a sample that gave it nothing to
    # remove: the question went unanswered, and an unanswered question is
    # not a pass.
    try:
        encoder_removal = removal_precision(encoder, reference)
        removal_detail = {'encoder': encoder_removal,
                          'threshold': REMOVAL_PRECISION_FLOOR}
        removal_passed = (coverage_ok
                          and encoder_removal['lower']
                          >= REMOVAL_PRECISION_FLOOR)
        try:
            removal_detail['incumbent'] = removal_precision(haiku, reference)
        except AuditError:
            pass          # reported when available; it decides nothing
    except AuditError as why:
        removal_detail = {'unavailable': str(why)}
        removal_passed = False
    removal_detail['rule'] = (
        'encoder Wilson lower bound >= %.2f. THE trial gate: deleting real '
        'posts is the one failure that leaves the board worse than no '
        'judging at all.' % REMOVAL_PRECISION_FLOOR)

    criteria = [_criterion('removal_precision', removal_passed,
                           removal_detail)]

    # Measured, reported, and gating NOTHING. There is no incumbent to fall
    # back to -- the paid judge stopped on 2026-09-03 when the credits ran
    # out -- so losing to it cannot be a reason to switch this off. What
    # these numbers are for is the separate, later decision to EXPAND:
    # judging every mention instead of the gated fifth, and letting tone
    # reach the board.
    for field in ('relevance', 'content_origin'):
        encoder_field = field_agreement(encoder, reference, field)
        haiku_field = field_agreement(haiku, reference, field)
        threshold = haiku_field['point'] - AGREEMENT_TOLERANCE
        criteria.append(_criterion(
            '%s_agreement' % field,
            coverage_ok and encoder_field['lower'] >= threshold,
            {'encoder': encoder_field, 'incumbent': haiku_field,
             'threshold': threshold,
             'rule': 'encoder Wilson lower bound >= incumbent point - %.2f. '
                     'Reported only; expansion evidence, not a trial gate.'
                     % AGREEMENT_TOLERANCE},
            gates=False))

    gating = [c for c in criteria if c['gates']]
    listed = sorted(missing.items(), key=lambda item: str(item[0]))[:20]
    report = {
        'schema': 'radar-encoder-trial-audit-3',
        'sample_size': len(keys),
        'coverage': {'complete': coverage_ok,
                     'missing': [{'key': key, 'lacks': lacks}
                                 for key, lacks in listed],
                     'missing_count': len(missing)},
        'criteria': criteria,
        'passed': coverage_ok and all(c['passed'] for c in gating),
        'expansion_ready': coverage_ok and all(c['passed'] for c in criteria),
        'tone': _tone_section(bundle, encoder, haiku, reference, coverage_ok),
    }
    if not coverage_ok:
        report['failure'] = (
            '%d of %d sampled rows lack a valid label or a valid prediction '
            'from one or both backends; a denominator is never quietly '
            'shrunk to what was answered' % (len(missing), len(keys)))
    return report


# ---- the supplementary sets: reported apart, never in the gate --------------

def supplemental_section(rows, name):
    """The original audit's halves and the locked natural set, recomputed
    under THIS module's definitions (spec 7.3): the same reversal rule, the
    same removal denominator, reported per half and never pooled, with
    every reversal and every disagreement on a truncated post listed for
    a human to look at.

    `rows`: [{key, half, truncated, reference, prediction}]. Pure. Nothing
    here enters the fresh audit's gate totals -- these sets were chosen
    for other reasons and cannot estimate production removal precision.
    """
    valid = [row for row in rows
             if is_verdict(row.get('reference'))
             and is_verdict(row.get('prediction'))]

    def stats(subset):
        reference = {row['key']: row['reference'] for row in subset}
        prediction = {row['key']: row['prediction'] for row in subset}
        out = {'rows': len(subset)}
        measures = [('reversal_rate', lambda: reversal_rate(prediction, reference)),
                    ('removal_precision',
                     lambda: removal_precision(prediction, reference))]
        for field in ('relevance', 'content_origin', 'attitude'):
            measures.append(('%s_agreement' % field,
                             lambda field=field: field_agreement(
                                 prediction, reference, field)))
        for label, measure in measures:
            try:
                out[label] = measure()
            except AuditError as why:
                out[label] = {'unavailable': str(why)}
        return out

    halves = {}
    for half in sorted({row.get('half') or 'all' for row in valid}):
        halves[half] = stats([row for row in valid
                              if (row.get('half') or 'all') == half])
    reversals = []
    truncated = []
    for row in valid:
        truth = row['reference'].get('attitude')
        said = row['prediction'].get('attitude')
        if truth in DIRECTIONAL and said in DIRECTIONAL and truth != said:
            reversals.append({'key': row['key'], 'half': row.get('half'),
                              'truncated': bool(row.get('truncated')),
                              'reference': truth, 'predicted': said})
        if row.get('truncated'):
            for field in ('relevance', 'content_origin', 'attitude',
                          'expected_move', 'confidence'):
                if row['reference'].get(field) != row['prediction'].get(field):
                    truncated.append({'key': row['key'], 'half': row.get('half'),
                                      'field': field,
                                      'reference': row['reference'].get(field),
                                      'predicted': row['prediction'].get(field)})
    section = stats(valid)
    section.update(name=name, invalid_rows=len(rows) - len(valid),
                   halves=halves, reversal_disagreements=reversals,
                   truncated_disagreements=truncated,
                   enters_gate_totals=False)
    return section


def _tone_section(bundle, encoder, haiku, reference, coverage_ok):
    """Reported, never gating. Says whether tone COULD later be considered.

    A missing mixed/none slice fails tone qualification rather than being
    skipped: it is a question this sample cannot answer, and an unanswered
    question is not a pass.
    """
    section = {'gates_the_trial': False, 'qualified': False, 'criteria': []}
    # The shadow period is a fact about the trial's history, not about
    # this sample, so it is reported even when the sample cannot answer
    # the tone questions at all.
    shadow_days = bundle.get('shadow_days')
    shadow = _criterion(
        'shadow_period',
        isinstance(shadow_days, (int, float))
        and shadow_days >= SHADOW_DAYS_REQUIRED,
        {'shadow_days': shadow_days, 'required': SHADOW_DAYS_REQUIRED,
         'rule': 'at least %d days of trial-mode history to compare against '
                 'the tone actually displayed' % SHADOW_DAYS_REQUIRED})
    try:
        encoder_reversal = reversal_rate(encoder, reference)
        haiku_reversal = reversal_rate(haiku, reference)
    except AuditError as why:
        section['unavailable'] = str(why)
        section['criteria'].append(shadow)
        return section

    section['criteria'].append(_criterion(
        'polarity_reversals',
        (encoder_reversal['point'] <= haiku_reversal['point']
         and encoder_reversal['upper'] < REVERSAL_CEILING),
        {'encoder': encoder_reversal, 'incumbent': haiku_reversal,
         'rule': 'encoder point <= incumbent point AND encoder Wilson upper '
                 'bound < %.2f' % REVERSAL_CEILING}))

    encoder_attitude = field_agreement(encoder, reference, 'attitude')
    haiku_attitude = field_agreement(haiku, reference, 'attitude')
    section['criteria'].append(_criterion(
        'attitude_agreement',
        encoder_attitude['lower'] >= haiku_attitude['point']
        - TONE_AGREEMENT_TOLERANCE,
        {'encoder': encoder_attitude, 'incumbent': haiku_attitude,
         'rule': 'encoder Wilson lower bound >= incumbent point - %.2f'
                 % TONE_AGREEMENT_TOLERANCE}))

    try:
        encoder_confusion = mixed_none_confusion(encoder, reference)
        haiku_confusion = mixed_none_confusion(haiku, reference)
        section['criteria'].append(_criterion(
            'mixed_none_confusion',
            encoder_confusion['point'] <= haiku_confusion['point'],
            {'encoder': encoder_confusion, 'incumbent': haiku_confusion,
             'rule': 'encoder point <= incumbent point'}))
    except AuditError as why:
        section['criteria'].append(_criterion(
            'mixed_none_confusion', False,
            {'rule': 'the sample must contain reference mixed/none rows',
             'unavailable': str(why)}))

    section['criteria'].append(shadow)

    section['qualified'] = coverage_ok and all(c['passed']
                                               for c in section['criteria'])
    return section
