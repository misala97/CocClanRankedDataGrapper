"""Step 2 / decision 8: a cheap non-Radar request beside two cold boards.

A MODEL, NOT GUNICORN. gunicorn does not run on Windows and there is no WSL
here. Two OS processes (`serve_perf3.py`), one request thread each, serving
the real WSGI app: the model of `--workers 2` with sync workers. PERF2 ran the
same model on the OLD synchronous path and measured a cheap request at 7,602
ms worst with one thread per process (9 ms with two): a board build holds its
worker, and a proxy round-robining `/` onto it waits the whole build. That is
the number the shared path is meant to remove, and it is re-measured here on
the new path, as the ruling asks.

  flag ON   the producer builds; the two web processes only read (a pending
            answer, polls, then the board)
  flag OFF  no producer -- today's deployment; each web process builds its
            own board inside the request

Per episode: two cold selections, one per process, asked at the same moment
(both limit-variants of the standing boards, so each costs what a warm build
costs and neither can be answered by a memo or the store); each client polls
as the real one does until a board is in hand, and meanwhile `/` (the app
overview: one user lookup, one render) is requested round-robin across both
processes every 100 ms -- one sequential hammer, as PERF2's model had. Ten
episodes per flag, after an idle baseline of twelve `/` requests with the
first two discarded, as PERF2 did.

    cd personal_apps
    <python 3.12> scratchpad/perf3/two_workers_perf3.py [--episodes 10] [--out DIR]
"""
import argparse
import json
import threading
import time

import sqlalchemy as sa

import scale_env

app = scale_env.bind()

import perf3_common as common  # noqa: E402

PORTS = (5083, 5084)
CHEAP = '/'
PERF2_OLD_PATH_MODEL = {'one_thread_per_process_worst_ms': 7602,
                        'two_threads_per_process_worst_ms': 9}


def selections(episode, flag):
    limit = str(60 + episode + (0 if flag == 'on' else 20))
    return ({'market': 'us', 'segment': '', 'window': '24', 'limit': limit},
            {'market': 'de', 'segment': '', 'window': '12', 'limit': limit})


def client(port, args, cookie, record):
    began = time.perf_counter()
    took, status, payload = common.board(port, args, cookie, timeout=600)
    record.update(label=common.label(args), port=port,
                  first_ms=round(took * 1000, 1), first_status=status,
                  first_pending=bool(payload and payload.get('pending')))
    polls = 0
    while not common.is_board(payload) and time.perf_counter() - began < 900:
        time.sleep(((payload or {}).get('retry_after_ms') or 1000) / 1000.0)
        took, status, payload = common.board(port, args, cookie, poll=True,
                                             timeout=600)
        polls += 1
    record.update(board_s=round(time.perf_counter() - began, 3), polls=polls,
                  got_board=common.is_board(payload), status=status)


def run_flag(flag, args, out, engine, ns, cookie):
    print(f"\n--- flag {flag.upper()}: "
          + ('the producer builds, the web processes read ---' if flag == 'on'
             else 'no producer, each web process builds its own board ---'))
    children = []
    producer = None
    record = {'flag': flag, 'episodes': []}
    try:
        if flag == 'on':
            producer = common.start_producer(out, name='producer-2w')
            children.append(producer)
            if producer.namespace != ns:
                raise SystemExit('producer namespace differs')
            common.wait_ready_idle(engine, ns, timeout=900)
        webs = [common.start_web(out, port, name=f'web{port}-{flag}',
                                 flag=flag) for port in PORTS]
        children += webs
        for web in webs:
            if web.namespace != ns:
                raise SystemExit('web namespace differs')
        idle = [common.http_get(PORTS[0], CHEAP, cookie=cookie)
                for _ in range(12)][2:]
        record['idle_ms'] = [round(t * 1000, 2) for t, _, _ in idle]
        record['idle_statuses'] = sorted({s for _, s, _ in idle})
        locks = common.lock_status(engine)
        for episode in range(args.episodes):
            pair = selections(episode, flag)
            if flag == 'on':
                for selection in pair:
                    common.delete_key(engine, ns, common.key_of(selection)[0])
            boards = [{}, {}]
            cheap = []
            stop = threading.Event()

            def hammer():
                i = 0
                while not stop.is_set():
                    port = PORTS[i % 2]
                    i += 1
                    took, status, _ = common.http_get(port, CHEAP,
                                                      cookie=cookie,
                                                      timeout=600)
                    cheap.append({'ms': round(took * 1000, 2),
                                  'status': status, 'port': port})
                    time.sleep(0.1)

            threads = [threading.Thread(target=client, args=(
                PORTS[i], pair[i], cookie, boards[i])) for i in (0, 1)]
            pounding = threading.Thread(target=hammer)
            began = time.perf_counter()
            for thread in threads:
                thread.start()
            pounding.start()
            peak = {web.name: 0.0 for web in webs}
            while any(thread.is_alive() for thread in threads):
                for web in webs:
                    peak[web.name] = max(peak[web.name],
                                         common.working_set(web.pid)['ws_mb'])
                time.sleep(0.3)
            for thread in threads:
                thread.join()
            stop.set()
            pounding.join()
            record['episodes'].append({
                'boards': boards, 'cheap': cheap, 'peak_ws_mb': peak,
                'span_s': round(time.perf_counter() - began, 2)})
            worst = max(c['ms'] for c in cheap)
            print(f'  episode {episode + 1}: boards '
                  + '; '.join(f"{b['label']} first {b['first_ms']:.0f} ms"
                              f"{' (pending)' if b['first_pending'] else ''},"
                              f" in hand {b['board_s']:.2f} s" for b in boards)
                  + f'   /: {len(cheap)} requests, worst {worst:.0f} ms',
                  flush=True)
            time.sleep(2)
        record['locks'] = common.lock_delta(locks, common.lock_status(engine))
        record['stats'] = [json.loads(common.http_get(p, '/perf3/stats')[2])
                           for p in PORTS]
    finally:
        if producer is not None:
            try:
                common.wait_ready_idle(engine, ns, timeout=600)
            except TimeoutError:
                print('  (producer not idle at the end)')
        common.stop_all(children)
    cheap = [c['ms'] / 1000 for e in record['episodes'] for c in e['cheap']]
    statuses = sorted({c['status'] for e in record['episodes']
                       for c in e['cheap']})
    boards_s = [b['board_s'] for e in record['episodes'] for b in e['boards']]
    record['cheap_ms'] = common.triple(cheap)
    record['cheap_statuses'] = statuses
    record['boards_s'] = common.triple(boards_s, scale=1.0)
    print(f"  '/' idle                 {common.fmt([v / 1000 for v in record['idle_ms']])}")
    print(f"  '/' during two boards    {common.fmt(cheap)}   statuses {statuses}")
    print('  board in hand            ' + common.fmt(boards_s, scale=1.0,
                                                    unit='s', digits=2))
    if flag == 'on':
        print(f"  row-lock waits across the episodes: {record['locks']['waits']}"
              f" ({record['locks']['time_ms']} ms)")
    return record


def main():
    parser = argparse.ArgumentParser()
    # Ten: with the flag off every `/` waits out a build, so an episode yields
    # only about two cheap samples, and ten episodes make that about twenty.
    parser.add_argument('--episodes', type=int, default=10)
    parser.add_argument('--out')
    parser.add_argument('--flags', default='on,off')
    args = parser.parse_args()

    import env_check
    env_check.preflight('two_workers_perf3 (Step 2) -- a MODEL, not gunicorn')
    out = common.out_dir(args.out)
    engine = scale_env.engine()
    ns = scale_env.namespace()
    with engine.connect() as c:
        user_id = c.execute(sa.text(
            'SELECT id FROM app_user WHERE username NOT LIKE :p'
            ' ORDER BY id LIMIT 1'), {'p': common.USER_PREFIX + '%'}).scalar()
    cookie = common.mint_cookie(app, user_id)
    print(f'THIS IS A MODEL OF gunicorn, NOT gunicorn: two OS processes x one'
          f' request thread, Windows, no WSL. Cookie: the fixture account'
          f' (id {user_id}), no watches.')
    record = {'model': 'two OS processes x 1 request thread (NOT gunicorn)',
              'perf2_old_path_model': PERF2_OLD_PATH_MODEL}
    for flag in args.flags.split(','):
        record[flag] = run_flag(flag, args, out, engine, ns, cookie)
    rows, others = common.delete_on_demand(engine, ns)
    print(f'\ncleanup: {rows} on-demand board(s) removed')
    if 'on' in record and 'off' in record:
        on, off = record['on']['cheap_ms'], record['off']['cheap_ms']
        print('\nTHE NUMBER (MODEL, two processes x one thread): a cheap'
              f' non-Radar request during two cold board requests --'
              f' median {on[0]} ms / worst {on[2]} ms with the flag ON,'
              f' median {off[0]} ms / worst {off[2]} ms with it OFF.'
              f" PERF2's old-path MODEL: {PERF2_OLD_PATH_MODEL['one_thread_per_process_worst_ms']:,}"
              ' ms worst.')
    common.save(out, 'two_workers.json', record)


if __name__ == '__main__':
    main()
