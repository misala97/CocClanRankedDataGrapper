# personal_apps/scratchpad/label_export/checkpointing.py
"""When a half-finished training run may be picked up again.

Michi's workstation throws VIDEO_TDR_ERROR (bugcheck 0x116) roughly every
five days -- 19 times in 90 days, with a clean WHEA log, and while gaming
as much as while training. It is the machine, not the workload. A 50-minute
run has a real chance of being hit; a two-hour base run more so. So the
trainer writes a checkpoint after every epoch and a crash costs one epoch
rather than the whole experiment.

Torch-free on purpose: the DECISION about whether a checkpoint may be
resumed is a rule, and rules belong in the ordinary test suite. The
trainer does the tensor-shaped part.

THE RULE. A checkpoint resumes only a run whose settings produce the same
answer. Resuming across a changed learning rate, batch size, seed, loss or
training set would yield numbers no one could interpret -- worse than
losing the run, because the loss is silent. `epochs` is deliberately NOT
in the list: asking for more epochs does not invalidate the epochs already
done, it just means there is more to do.
"""

# Everything that changes what the finished model would be. `epochs` is
# excluded (see the docstring); so is anything about output paths, saving
# or logging, which change nothing about the answer.
SETTINGS_THAT_MUST_MATCH = (
    'base',                 # the backbone: small vs base is a different model
    'lr',
    'batch_size',
    'accumulate',           # with batch_size, this is the effective batch
    'max_len',
    'seed',
    'reversal_penalty',     # part of the loss
    'train_rows',           # the data changed if this moved
    'labels_sha',
    'recall_labels_sha',
)


def is_compatible(saved, current):
    """Whether `saved` (a checkpoint's manifest, or None) may resume into
    a run configured as `current`."""
    if not saved:
        return False
    return all(saved.get(field) == current.get(field)
               for field in SETTINGS_THAT_MUST_MATCH)


def epochs_left(current, done):
    """How many epochs a resumed run still owes. Never negative: a
    checkpoint from a longer run simply has nothing left to do."""
    return max(0, int(current.get('epochs', 0)) - int(done))
