"""The namespace a cached board belongs to, derived from the running build.

The key says which board was asked for; the namespace says which build
answered. A stale namespace serves a payload the current code can no longer
read, so it is computed from the payload version, the code revision and the
configuration read at startup -- never typed by hand, and never a shared
'unknown' that every build unable to identify itself would fall into
together.

The revision tests walk the three sources in order, and the git one is
deliberately awkward: this task was written in a git WORKTREE, where `.git`
is a file pointing at a gitdir under the main repository and the branch it
names lives in the common directory's packed-refs. Reading `<root>/.git/HEAD`
resolves nothing there, which is why that case has its own test.

No database: every input here is a file or a module constant.
"""
import pytest

from features.radar import board_namespace


@pytest.fixture(autouse=True)
def fresh_namespace_memo():
    """namespace() is memoised per process. A test that changes an input has
    to be able to see its own change, and must not leave its answer behind
    for the next test to read."""
    board_namespace.reset()
    yield
    board_namespace.reset()


def test_revision_prefers_the_explicit_environment(tmp_path):
    assert board_namespace.build_revision(
        env={'RADAR_BUILD_REVISION': 'a' * 40}, root=tmp_path) == 'a' * 40


def test_revision_reads_the_build_file_next(tmp_path):
    (tmp_path / 'BUILD_REVISION').write_text('b' * 40 + '\n')
    assert board_namespace.build_revision(env={}, root=tmp_path) == 'b' * 40


def test_revision_reads_git_head_last(tmp_path):
    git = tmp_path / '.git'; git.mkdir()
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'refs' / 'heads' / 'main').write_text('c' * 40 + '\n')
    assert board_namespace.build_revision(env={}, root=tmp_path) == 'c' * 40


def test_a_worktree_gitfile_is_followed(tmp_path):
    """The checkout this task was written in: `.git` is a file naming a
    gitdir under the main repository, HEAD lives in that gitdir, and the
    branch it names is only in the common directory's packed-refs."""
    git_dir = tmp_path / 'main' / '.git' / 'worktrees' / 'wt'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/feature\n')
    (git_dir / 'commondir').write_text('../..\n')
    (tmp_path / 'main' / '.git' / 'packed-refs').write_text(
        '# pack-refs with: peeled fully-peeled sorted \n'
        + 'd' * 40 + ' refs/heads/feature\n')
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    (checkout / '.git').write_text('gitdir: %s\n' % git_dir)

    assert board_namespace.build_revision(env={}, root=checkout) == 'd' * 40


def test_a_relative_gitfile_path_resolves_from_the_worktree_root(tmp_path):
    """git writes an absolute gitdir on this machine, but a relative one is
    legal too, and it is resolved against the worktree root the `.git` file
    lives in -- not the process cwd, and not the main repository."""
    git_dir = tmp_path / 'main' / '.git' / 'worktrees' / 'wt'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('f' * 40 + '\n')
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    (checkout / '.git').write_text('gitdir: ../main/.git/worktrees/wt\n')

    assert board_namespace.build_revision(env={}, root=checkout) == 'f' * 40


def test_head_and_ref_files_with_crlf_line_endings_resolve(tmp_path):
    """A Windows git client can write CRLF; the trailing \\r must not end up
    glued onto the ref name or the revision."""
    git = tmp_path / '.git'; git.mkdir()
    (git / 'HEAD').write_bytes(b'ref: refs/heads/main\r\n')
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'refs' / 'heads' / 'main').write_bytes(b'a' * 40 + b'\r\n')

    assert board_namespace.build_revision(env={}, root=tmp_path) == 'a' * 40


def test_a_detached_head_is_the_revision(tmp_path):
    """A deploy that checks out a tag has no branch to follow."""
    git = tmp_path / '.git'; git.mkdir()
    (git / 'HEAD').write_text('e' * 40 + '\n')
    assert board_namespace.build_revision(env={}, root=tmp_path) == 'e' * 40


def test_no_revision_is_a_configuration_error(tmp_path):
    with pytest.raises(board_namespace.ConfigError):
        board_namespace.build_revision(env={}, root=tmp_path)


def test_a_malformed_revision_is_refused(tmp_path):
    with pytest.raises(board_namespace.ConfigError):
        board_namespace.build_revision(env={'RADAR_BUILD_REVISION': 'not hex'}, root=tmp_path)


def test_a_malformed_build_file_is_refused_rather_than_skipped(tmp_path):
    """A deploy that wrote junk into the file has misconfigured the build.
    Falling through to git would answer under a revision nobody asked for."""
    (tmp_path / 'BUILD_REVISION').write_text('HEAD -> main\n')
    git = tmp_path / '.git'; git.mkdir()
    (git / 'HEAD').write_text('c' * 40 + '\n')
    with pytest.raises(board_namespace.ConfigError):
        board_namespace.build_revision(env={}, root=tmp_path)


def test_the_namespace_moves_with_each_input(monkeypatch):
    base = board_namespace.compute_namespace(1, 'a' * 40, 'f' * 16)
    assert board_namespace.compute_namespace(2, 'a' * 40, 'f' * 16) != base
    assert board_namespace.compute_namespace(1, 'b' * 40, 'f' * 16) != base
    assert board_namespace.compute_namespace(1, 'a' * 40, '0' * 16) != base


def test_the_fingerprint_covers_source_and_price_configuration(monkeypatch):
    before = board_namespace.config_fingerprint()
    monkeypatch.setattr(board_namespace, '_fingerprint_inputs',
                        lambda: {'source_config_version': 'changed'})
    assert board_namespace.config_fingerprint() != before


def test_the_fingerprint_reads_the_live_configuration():
    """Named inputs, not a hash of a hash: if one of these stops being read,
    a configuration change stops moving the namespace and nothing says so."""
    inputs = board_namespace._fingerprint_inputs()
    assert set(inputs) == {'source_config_version', 'price_provider',
                           'reddit_fetcher', 'default_segment', 'sort_keys'}
    assert len(board_namespace.config_fingerprint()) == 16


def test_the_process_namespace_is_memoised_and_resolves_here():
    """This worktree is a git checkout, so the git fallback resolves."""
    a = board_namespace.namespace(); b = board_namespace.namespace()
    assert a == b and len(a) == 64


def test_the_memo_holds_until_it_is_reset(monkeypatch):
    """What makes namespace() free to call on every request -- and what
    reset() exists to undo."""
    first = board_namespace.namespace()
    monkeypatch.setattr(board_namespace, '_fingerprint_inputs',
                        lambda: {'source_config_version': 'changed'})
    assert board_namespace.namespace() == first

    board_namespace.reset()
    assert board_namespace.namespace() != first


def test_describe_says_what_the_namespace_was_derived_from():
    described = board_namespace.describe()
    assert described['payload_version'] == board_namespace.PAYLOAD_VERSION
    assert described['namespace'] == board_namespace.namespace()
    assert described['namespace'] == board_namespace.compute_namespace(
        described['payload_version'], described['revision'],
        described['fingerprint'])
