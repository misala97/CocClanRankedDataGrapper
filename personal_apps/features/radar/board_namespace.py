"""What a cached board belongs to: the identity of the build that made it.

A stored board is addressed by (namespace, key_hash). The key says which
board was asked for; the namespace says which build answered. Everything
that can change a payload without changing the question belongs here -- the
payload's own shape, the code that assembles it, and the configuration that
code reads at startup. Get it wrong in the generous direction and the cache
merely goes cold on deploy; get it wrong in the other direction and a viewer
is served a payload the running code can no longer read.

So the namespace is derived, never typed. A hand-maintained constant is one
forgotten bump away from being wrong, and nothing complains until a shape
changes underneath a live row. And there is no 'unknown' fallback: a build
that cannot say which revision it is refuses to answer rather than sharing
one bucket with every other build that could not say either -- which is the
same collision, wearing a default value as a disguise.

The revision is read from files only: the environment a deploy sets, then a
BUILD_REVISION file a deploy writes, then git's own on-disk layout. Never a
subprocess. This runs per worker under gunicorn, where forking git is both
slow and one PATH away from failing in a way that looks like nothing more
than a cache miss.
"""
import hashlib
import json
import os
import pathlib
import re

# Bumped when the stored payload's shape changes. Rows written under the old
# shape keep their old namespace and are never read again.
PAYLOAD_VERSION = 1

# git writes lowercase hex; a short revision is accepted because a deploy
# that stamps `git rev-parse --short HEAD` into the file is stamping a real
# revision. Anchored, so a line of git porcelain cannot pass as one.
_REVISION = re.compile(r'^[0-9a-f]{7,64}$')

# HEAD -> a symbolic ref -> another one. Real repositories stop after one
# hop; the bound is here so a corrupt pair of refs pointing at each other
# fails as a missing revision instead of hanging a worker.
_MAX_REF_HOPS = 5

_EXHAUSTED = ('RADAR_BUILD_REVISION is not set, no BUILD_REVISION file, '
              'and no git HEAD could be read')

# namespace() is asked on every cached read, and its inputs cannot change
# inside a running process: the revision is the code that is running and the
# configuration is read at startup. So it is resolved once. reset() empties
# this for tests that change an input.
_MEMO = {}


class ConfigError(RuntimeError):
    """The build cannot say what it is.

    Raised rather than defaulted. A cache namespace is an identity, and a
    guessed identity is worse than no cache at all.
    """


def build_revision(*, env=os.environ, root=None):
    """The revision of the running code, from the first source that has one.

    In order: the environment, which a deploy sets explicitly; a
    BUILD_REVISION file, which a build writes when the code ships without
    its .git; and git's own files, which is what a checkout on the VPS or a
    developer's worktree has.

    A source that is present but not a revision is refused rather than
    skipped. Falling through from a mistyped RADAR_BUILD_REVISION would
    answer under a revision nobody chose, and the deploy that set it would
    never learn. Git is the exception: an unreadable HEAD is an absence, not
    a misconfiguration, so it falls through to the error naming all three.
    """
    root = pathlib.Path(root) if root is not None else _repo_root()

    explicit = _configured('RADAR_BUILD_REVISION',
                           env.get('RADAR_BUILD_REVISION'))
    if explicit:
        return explicit

    from_file = _configured('the BUILD_REVISION file',
                            _read(root / 'BUILD_REVISION'))
    if from_file:
        return from_file

    from_git = (_git_revision(root) or '').strip().lower()
    if _REVISION.match(from_git):
        return from_git

    raise ConfigError(_EXHAUSTED)


def config_fingerprint():
    """16 hex over the configuration a board would be built under.

    Not memoised: the inputs are read at startup, so this is cheap, and a
    test that changes one has to be able to see its own change.
    """
    payload = json.dumps(_fingerprint_inputs(), sort_keys=True,
                         separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def compute_namespace(version, revision, fingerprint):
    """The namespace three named inputs produce, as a pure function.

    Separate from namespace() so the derivation can be tested without a
    process, and so a caller diagnosing a cold cache can ask what a given
    combination would have produced.
    """
    return hashlib.sha256(
        f'{version}:{revision}:{fingerprint}'.encode('utf-8')).hexdigest()


def namespace():
    """The namespace of this process, resolved once."""
    return _resolved()['namespace']


def describe():
    """The namespace and everything it was derived from.

    For diagnostics: a cache that went cold has one of these four values
    different from the last deploy's, and the answer should say which.
    """
    return dict(_resolved())


def reset():
    """Forget the resolved namespace. For tests that change an input."""
    _MEMO.clear()


def _resolved():
    if not _MEMO:
        revision = build_revision()
        fingerprint = config_fingerprint()
        _MEMO.update({
            'payload_version': PAYLOAD_VERSION,
            'revision': revision,
            'fingerprint': fingerprint,
            'namespace': compute_namespace(PAYLOAD_VERSION, revision,
                                           fingerprint),
        })
    return _MEMO


def _fingerprint_inputs():
    """The configuration a cached board would have been built under.

    Named inputs rather than one opaque hash, so this file says which
    settings a stored board depends on and a diff shows when that list
    changes. `source_config_version` covers what gets ingested and counted;
    the price provider decides which quotes a row shows; the reddit fetcher
    decides where mentions come from; the default segment decides the board
    a bare URL asks for; the sort keys are the payload's own vocabulary.

    Imported at call time. This module is the identity a stored board
    carries, so anything that stores or serves one may import it -- `board`
    included, which would close the circle. It is read once per process, at
    the moment the namespace is first needed.
    """
    from . import board, config

    return {
        'source_config_version': config.source_config_version(),
        'price_provider': list(config.price_provider_config()),
        'reddit_fetcher': config.REDDIT_FETCHER,
        'default_segment': config.DEFAULT_SEGMENT,
        'sort_keys': list(board.SORT_KEYS),
    }


def _repo_root():
    """The checkout root -- the directory holding `.git` and personal_apps.

    This file is <root>/personal_apps/features/radar/board_namespace.py.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def _read(path):
    """A file's text, or None if there is nothing readable there.

    Reading a directory raises too, which is what makes `.git` answerable
    with one call whether it is a file or a directory.
    """
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def _configured(source, raw):
    """A revision somebody configured on purpose, or None if they did not.

    Blank counts as absent -- an environment variable exported empty is how
    a shell says nothing, not how it says garbage. Anything else that is not
    a revision is refused, naming the source, because the fix is at that
    source and nowhere else.
    """
    value = (raw or '').strip().lower()
    if not value:
        return None
    if not _REVISION.match(value):
        raise ConfigError(f'{source} is not a commit revision: {value[:80]!r}')
    return value


def _git_revision(root):
    """HEAD, read the way git lays it out on disk.

    Handles what a real checkout can be: a `.git` directory, or a `.git`
    file naming a worktree's gitdir; a detached HEAD holding the revision
    itself, or a symbolic ref; a branch stored loose, or only in packed-refs
    in the common directory a worktree shares with its main repository.
    """
    git_dir = _git_dir(root)
    if git_dir is None:
        return None
    common = _common_dir(git_dir)

    pointer = (_read(git_dir / 'HEAD') or '').strip()
    for _ in range(_MAX_REF_HOPS):
        if not pointer:
            return None
        if not pointer.startswith('ref:'):
            return pointer
        pointer = _ref(pointer[len('ref:'):].strip(), git_dir, common) or ''
    return None


def _git_dir(root):
    """Where git actually keeps this checkout's HEAD.

    A worktree's `.git` is a file reading `gitdir: <path>`; git writes an
    absolute one, but a relative path is legal and is resolved against the
    checkout it was found in.
    """
    dot_git = root / '.git'
    text = _read(dot_git)
    if text is None:
        return dot_git if dot_git.is_dir() else None

    text = text.strip()
    if not text.startswith('gitdir:'):
        return None
    named = pathlib.Path(text[len('gitdir:'):].strip())
    return named if named.is_absolute() else root / named


def _common_dir(git_dir):
    """The directory a worktree shares with its main repository.

    Branches live there, not in the worktree's own gitdir; `commondir` is
    how the worktree says where. Without one, a gitdir is its own common
    directory.
    """
    text = (_read(git_dir / 'commondir') or '').strip()
    if not text:
        return git_dir
    named = pathlib.Path(text)
    return named if named.is_absolute() else git_dir / named


def _ref(name, git_dir, common):
    """What a ref name points at, loose first and then packed.

    Both directories are tried in both forms. Most refs are common, but a
    worktree keeps a few of its own, and either directory may have packed
    the branch away.
    """
    for base in (git_dir, common):
        loose = (_read(base / name) or '').strip()
        if loose:
            return loose
    for base in (common, git_dir):
        packed = _packed_ref(base, name)
        if packed:
            return packed
    return None


def _packed_ref(base, name):
    """One ref out of packed-refs.

    Lines are `<revision> <ref>`; a leading `#` is the header and a leading
    `^` is the tag a previous line peels to, which is never what HEAD names.
    """
    for line in (_read(base / 'packed-refs') or '').splitlines():
        if not line or line[0] in '#^':
            continue
        revision, _, ref = line.partition(' ')
        if ref.strip() == name:
            return revision.strip()
    return None
