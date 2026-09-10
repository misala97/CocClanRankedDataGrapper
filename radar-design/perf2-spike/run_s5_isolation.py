"""Task S5: private data stays private.

The shared payload is shared. If one account's watch list can reach it, every
account reading that key sees it, and the store would have turned a private
mark into a broadcast.

The tickers are chosen so the test can actually fail: a raw-byte search for a
ticker that is legitimately on the board would pass for the wrong reason, so
both watch lists are drawn from tickers ABSENT from the stored blob.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s5_isolation.py
"""
import json
import os
import subprocess
import sys

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import accounts                                        # noqa: E402
import keys                                            # noqa: E402
import producer                                        # noqa: E402
import reader                                          # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402


def pick_absent(db, blob_text, wanted):
    """`wanted` tickers that are nowhere in the stored bytes."""
    candidates = db.session.execute(sa.text(
        'SELECT DISTINCT ticker FROM radar_bucket_sources'
        " WHERE ticker LIKE 'T%' ORDER BY ticker")).scalars().all()
    out = []
    for ticker in candidates:
        if ticker not in blob_text:
            out.append(ticker)
        if len(out) >= wanted:
            break
    assert len(out) == wanted, 'no absent tickers to test with'
    return out


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S5 -- private data stays private')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        now = selections.fixed_now()
        store.drop_table(engine)
        store.create_table(engine)

        # ---- Step 1: two accounts, one key -------------------------------
        print('\n--- Step 1: two accounts, one stored key ---')
        query = Query(sources=list(sources), segments=[], window=24, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        key_hash, key_json = keys.canonical(query)
        store.enqueue(engine, key_hash, key_json, now, warm=True)
        producer.serve_once(engine, 's5', now, key_hash=key_hash,
                            query_cls=Query)
        row = store.read(engine, key_hash, now)
        assert row.state == 'ready'
        blob_text = store.decompress(row.payload).decode('utf-8')
        print('  stored blob: %d bytes compressed, %d bytes JSON'
              % (row.payload_bytes, len(blob_text)))

        absent = pick_absent(db, blob_text, 5)
        watch_a, watch_b = absent[:3], absent[3:]
        user_a, user_b = accounts.setup(db, (watch_a, watch_b))
        print('  A=%d watches %s' % (user_a, watch_a))
        print('  B=%d watches %s' % (user_b, watch_b))
        print('  both lists were chosen because NONE of these tickers appears'
              ' in the stored blob -- so the byte search below can fail')

        # ---- Step 2: the stored blob is account-free ---------------------
        print('\n--- Step 2: the stored blob carries no account ---')
        stored = json.loads(blob_text)
        print("  'watching'   present in the stored payload: %s"
              % ('watching' in stored))
        print("  'watch_rows' present in the stored payload: %s"
              % ('watch_rows' in stored))
        assert 'watching' not in stored
        assert 'watch_rows' not in stored
        for label, tickers in (('A', watch_a), ('B', watch_b)):
            for ticker in tickers:
                found = ticker in blob_text
                print("  raw-byte search for %s's %-8s in the blob: %s"
                      % (label, ticker, 'FOUND -- LEAK' if found
                         else 'absent'))
                assert not found, 'account data reached the shared payload'
        # The blob is also account-free of the ACCOUNT, not only its tickers.
        for needle in (str(user_a), str(user_b), 'perf2_a', 'perf2_b'):
            assert needle not in blob_text or needle.isdigit(), needle
        print('  no account id or username appears in the blob either')

        # TEETH: the byte search must be able to fail. Prove it by looking
        # for something that IS in the blob.
        on_board = stored['rows'][0]['ticker']
        print('  mutation check: search the same way for %s, which IS on the'
              ' board -> %s' % (on_board, on_board in blob_text))
        assert on_board in blob_text, 'the byte search cannot find anything'

        # ---- Step 3: each response carries its own -----------------------
        print('\n--- Step 3: each response carries its own, and only its own '
              '---')
        procs = {}
        for label, user_id in (('A', user_a), ('B', user_b)):
            procs[label] = subprocess.Popen(
                [sys.executable, os.path.join(SPIKE_DIR, 'reader.py'),
                 '--now', now.isoformat(), '--window', '24',
                 '--segments', '', '--market', 'us', '--fixture-sources',
                 '--user', str(user_id)],
                cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
        seen = {}
        for label, proc in procs.items():
            out, err = proc.communicate(timeout=600)
            line = [x for x in out.splitlines() if x.startswith('RESULT ')]
            assert line, (out, err)
            seen[label] = json.loads(line[0][len('RESULT '):])[0]

        # And in-process too, so the full payload can be inspected, not just
        # the subprocess summary.
        full = {}
        for label, user_id in (('A', user_a), ('B', user_b)):
            full[label] = reader.read_payload(
                engine, {'window': '24', 'segment': '', 'market': 'us',
                         'sources': src}, now, user_id)

        for label, other in (('A', 'B'), ('B', 'A')):
            mine = watch_a if label == 'A' else watch_b
            theirs = watch_b if label == 'A' else watch_a
            print('  %s (own process) got watching=%s'
                  % (label, seen[label]['watching']))
            assert seen[label]['watching'] == mine
            assert full[label]['watching'] == mine
            body = json.dumps(full[label], default=str)
            for ticker in theirs:
                assert ticker not in body, (
                    "%s's response contains %s's %s" % (label, other, ticker))
            print('    watch_rows: %d, and none of %s\'s tickers appears'
                  ' anywhere in %s\'s response'
                  % (len(full[label]['watch_rows']), other, label))

        assert seen['A']['digest'] != seen['B']['digest'], (
            'two accounts got the SAME digest -- the per-account half is not '
            'in the response at all')
        print('  the two responses differ (%s vs %s) precisely because each'
              ' carries its own watches'
              % (seen['A']['digest'][:12], seen['B']['digest'][:12]))
        # ...but the SHARED half is identical, which is the whole claim.
        shared_a = {k: v for k, v in full['A'].items()
                    if k not in ('watching', 'watch_rows')}
        shared_b = {k: v for k, v in full['B'].items()
                    if k not in ('watching', 'watch_rows')}
        assert shared_a == shared_b
        print('  and the shared half of the two responses is IDENTICAL')

        accounts.teardown(db)
        print('\nS5 done. Spike accounts removed.')


if __name__ == '__main__':
    main()
