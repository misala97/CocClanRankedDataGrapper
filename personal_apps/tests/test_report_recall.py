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
