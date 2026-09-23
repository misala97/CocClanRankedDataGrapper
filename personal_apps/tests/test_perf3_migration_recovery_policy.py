"""Fail-closed decisions used by the executable MariaDB rehearsal."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


PATH = (Path(__file__).resolve().parents[1] / 'scratchpad/perf3/'
        'rehearse_board_results_mariadb.py')
SPEC = importlib.util.spec_from_file_location('perf3_recovery', PATH)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)

EXPECTED = {
    'radar_board_namespaces': {'columns': ('ns-columns',),
                               'indexes': (('PRIMARY', 0),)},
    'radar_board_results': {'columns': ('result-columns',),
                            'indexes': (('PRIMARY', 0), ('queue', 1),
                                        ('warm', 1), ('demand', 1))},
}


def test_only_exact_empty_prior_revision_states_are_recoverable():
    assert recovery.recovery_plan(
        recovery.PREVIOUS, set(), {}, {}, EXPECTED) == 'upgrade'
    assert recovery.recovery_plan(
        recovery.PREVIOUS, {'radar_board_namespaces'},
        {'radar_board_namespaces': 0},
        {'radar_board_namespaces': EXPECTED['radar_board_namespaces']},
        EXPECTED) == 'rebuild'
    partial = deepcopy(EXPECTED)
    partial['radar_board_results']['indexes'] = (
        ('PRIMARY', 0), ('queue', 1), ('warm', 1))
    assert recovery.recovery_plan(
        recovery.PREVIOUS, recovery.NEW_TABLES,
        {name: 0 for name in recovery.NEW_TABLES}, partial,
        EXPECTED) == 'rebuild'
    assert recovery.recovery_plan(
        recovery.PREVIOUS, recovery.NEW_TABLES,
        {name: 0 for name in recovery.NEW_TABLES}, EXPECTED,
        EXPECTED) == 'stamp'


@pytest.mark.parametrize('stamp,rows,signatures', [
    ('wrongstamp', {name: 0 for name in recovery.NEW_TABLES}, EXPECTED),
    (recovery.PREVIOUS,
     {'radar_board_namespaces': 1, 'radar_board_results': 0}, EXPECTED),
    (recovery.PREVIOUS, {name: 0 for name in recovery.NEW_TABLES},
     {**EXPECTED,
      'radar_board_results': {'columns': ('unexpected',),
                              'indexes': (('PRIMARY', 0),)}}),
])
def test_wrong_stamp_data_or_shape_is_a_hard_refusal(stamp, rows, signatures):
    before = deepcopy((rows, signatures))
    with pytest.raises(recovery.RecoveryRefused):
        recovery.recovery_plan(stamp, recovery.NEW_TABLES, rows, signatures,
                               EXPECTED)
    assert (rows, signatures) == before
