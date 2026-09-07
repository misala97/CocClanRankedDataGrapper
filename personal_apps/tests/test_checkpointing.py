"""Resuming a training run after the machine dies.

Michi's workstation throws VIDEO_TDR_ERROR (0x116) about every five days,
19 times in 90 days, unrelated to what is running -- it happens while
gaming too. A 50-minute run has a real chance of being hit and a two-hour
base run more so, so a crash must cost one epoch, not the whole run.

The rule that matters: a checkpoint may only resume a run whose SETTINGS
match. Silently continuing under a different recipe would produce numbers
nobody could interpret.
"""
from scratchpad.label_export import checkpointing as cp


def _meta(**over):
    base = {'base': 'microsoft/deberta-v3-small', 'epochs': 6, 'lr': 3e-5,
            'batch_size': 8, 'accumulate': 2, 'max_len': 512, 'seed': 20260905,
            'reversal_penalty': 1.0, 'train_rows': 17090,
            'labels_sha': 'abc123', 'recall_labels_sha': 'def456'}
    base.update(over)
    return base


def test_a_checkpoint_from_the_same_settings_resumes():
    assert cp.is_compatible(_meta(), _meta()) is True


def test_a_different_recipe_never_resumes():
    for field, value in (('lr', 5e-5), ('batch_size', 4), ('max_len', 256),
                         ('seed', 1), ('reversal_penalty', 0.0),
                         ('base', 'microsoft/deberta-v3-base'),
                         ('accumulate', 4)):
        assert cp.is_compatible(_meta(), _meta(**{field: value})) is False, field


def test_different_training_data_never_resumes():
    assert cp.is_compatible(_meta(), _meta(train_rows=17091)) is False
    assert cp.is_compatible(_meta(), _meta(labels_sha='changed')) is False
    assert cp.is_compatible(_meta(), _meta(recall_labels_sha='changed')) is False


def test_asking_for_more_epochs_still_resumes():
    """Only the total changes; the work already done is still valid."""
    assert cp.is_compatible(_meta(epochs=6), _meta(epochs=8)) is True


def test_a_checkpoint_that_already_finished_is_not_resumed():
    assert cp.epochs_left(_meta(epochs=6), done=6) == 0
    assert cp.epochs_left(_meta(epochs=6), done=4) == 2
    assert cp.epochs_left(_meta(epochs=8), done=6) == 2


def test_no_checkpoint_at_all_is_simply_a_fresh_run():
    assert cp.is_compatible(None, _meta()) is False


def test_the_settings_recorded_are_only_the_ones_that_change_the_answer():
    """`--save` or an output path must not invalidate a checkpoint."""
    assert 'save' not in cp.SETTINGS_THAT_MUST_MATCH
    assert 'epochs' not in cp.SETTINGS_THAT_MUST_MATCH
    for field in ('base', 'lr', 'batch_size', 'accumulate', 'max_len', 'seed',
                  'reversal_penalty', 'train_rows', 'labels_sha'):
        assert field in cp.SETTINGS_THAT_MUST_MATCH, field
