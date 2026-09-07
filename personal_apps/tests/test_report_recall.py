"""The recall report: hit rate per rejection cause, extrapolated to the
week's real volume, and the symbols worth acting on."""
import json

from scripts import report_recall


def _label(mention_id, relevance, stratum):
    return {'mention_id': mention_id, 'relevance': relevance, 'stratum': stratum}


def _cand(mention_id, symbol, cause, evidence='x'):
    return {'mention_id': mention_id, 'ticker': symbol, 'stratum': 'cand:%s' % cause,
            'candidate': {'cause': cause, 'evidence': evidence, 'stored_today': False,
                          'external_id': 't1_%d' % abs(mention_id)}}


def test_the_hit_rate_of_a_cause_scales_to_its_weekly_volume():
    labels = [_label(-1, 'relevant', 'cand:name_only'),
              _label(-2, 'relevant', 'cand:name_only'),
              _label(-3, 'irrelevant', 'cand:name_only'),
              _label(-4, 'uncertain', 'cand:name_only')]
    candidates = [_cand(-1, 'GPRO', 'name_only'), _cand(-2, 'NKE', 'name_only'),
                  _cand(-3, 'BE', 'name_only'), _cand(-4, 'CL', 'name_only')]
    report = report_recall.build(labels, candidates, volumes={'name_only': 8000})
    row = report['by_cause']['name_only']
    assert row['labelled'] == 4 and row['relevant'] == 2
    assert row['hit_rate'] == 0.5
    # Uncertain is neither a hit nor a miss: the band is what it is worth.
    assert row['hit_rate_low'] == 0.5 and row['hit_rate_high'] == 0.75
    assert row['weekly_volume'] == 8000
    assert row['weekly_recovered'] == 4000
    assert row['weekly_recovered_high'] == 6000


def test_a_cause_with_no_labels_is_reported_not_divided_by_zero():
    report = report_recall.build([], [], volumes={'stopword': 6000})
    row = report['by_cause']['stopword']
    assert row['labelled'] == 0 and row['hit_rate'] is None
    assert row['weekly_recovered'] is None


def test_symbols_are_ranked_by_how_much_each_would_recover():
    labels = [_label(-1, 'relevant', 'cand:name_only'),
              _label(-2, 'relevant', 'cand:name_only'),
              _label(-3, 'irrelevant', 'cand:name_only')]
    candidates = [_cand(-1, 'GPRO', 'name_only'), _cand(-2, 'GPRO', 'name_only'),
                  _cand(-3, 'BE', 'name_only')]
    report = report_recall.build(labels, candidates, volumes={'name_only': 100},
                                 symbol_volumes={'name_only': {'GPRO': 60, 'BE': 40}})
    top = report['by_symbol'][0]
    assert top['symbol'] == 'GPRO' and top['cause'] == 'name_only'
    assert top['hit_rate'] == 1.0 and top['weekly_recovered'] == 60
    assert report['by_symbol'][1]['symbol'] == 'BE'
    assert report['by_symbol'][1]['weekly_recovered'] == 0


def test_the_total_counts_only_causes_that_were_labelled():
    labels = [_label(-1, 'relevant', 'cand:name_only')]
    candidates = [_cand(-1, 'GPRO', 'name_only')]
    report = report_recall.build(labels, candidates,
                                 volumes={'name_only': 100, 'stopword': 6000})
    assert report['weekly_recovered_total'] == 100


def test_a_label_whose_candidate_is_unknown_is_refused_loudly():
    labels = [_label(-99, 'relevant', 'cand:name_only')]
    try:
        report_recall.build(labels, [], volumes={'name_only': 10})
    except KeyError as exc:
        assert '-99' in str(exc)
    else:
        raise AssertionError('an unmatched label must not be silently dropped')


def test_the_cause_estimate_weights_each_symbol_by_its_real_volume():
    """The wave caps rows per symbol, so a high-volume symbol is
    deliberately under-sampled; averaging the sample would then report the
    capped mix rather than the week's. GoPro is 90% of this volume and
    always real, BE is 10% and never real."""
    labels = ([_label(-1, 'relevant', 'cand:name_only'),
               _label(-2, 'relevant', 'cand:name_only')]
              + [_label(-3, 'irrelevant', 'cand:name_only'),
                 _label(-4, 'irrelevant', 'cand:name_only')])
    candidates = [_cand(-1, 'GPRO', 'name_only'), _cand(-2, 'GPRO', 'name_only'),
                  _cand(-3, 'BE', 'name_only'), _cand(-4, 'BE', 'name_only')]
    report = report_recall.build(
        labels, candidates, volumes={'name_only': 100},
        symbol_volumes={'name_only': {'GPRO': 90, 'BE': 10}})
    row = report['by_cause']['name_only']
    assert row['hit_rate_sample'] == 0.5          # what the capped wave saw
    assert row['hit_rate'] == 0.9                 # what the week actually is
    assert row['weekly_recovered'] == 90


def test_volume_the_wave_never_sampled_is_carried_at_the_sample_rate():
    labels = [_label(-1, 'relevant', 'cand:name_only'),
              _label(-2, 'irrelevant', 'cand:name_only')]
    candidates = [_cand(-1, 'GPRO', 'name_only'), _cand(-2, 'BE', 'name_only')]
    report = report_recall.build(
        labels, candidates, volumes={'name_only': 100},
        symbol_volumes={'name_only': {'GPRO': 40, 'BE': 40, 'NEVERSEEN': 20}})
    row = report['by_cause']['name_only']
    # 40 at 100% + 40 at 0% + the unsampled 20 at the sample's own 50%.
    assert row['weekly_recovered'] == 50
    assert row['volume_sampled_share'] == 0.8


def test_without_symbol_volumes_the_estimate_is_the_plain_sample_rate():
    labels = [_label(-1, 'relevant', 'cand:name_only'),
              _label(-2, 'irrelevant', 'cand:name_only')]
    candidates = [_cand(-1, 'GPRO', 'name_only'), _cand(-2, 'BE', 'name_only')]
    report = report_recall.build(labels, candidates, volumes={'name_only': 100})
    row = report['by_cause']['name_only']
    assert row['hit_rate'] == 0.5 and row['volume_sampled_share'] is None
