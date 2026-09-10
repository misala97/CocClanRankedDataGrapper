"""Radar board producer daemon.

Mirrors run_radar_ingest.py: a long-running process holding a Flask app
context, deployed as its own systemd unit and restarted by the VPS deploy
script. It is the only process that builds a board; every web worker reads
what it published.

One producer, not one per worker. Two would not be wrong -- the lease token
and the namespace control row make a second one safe -- but they would be
wasteful, because the eight standing boards are the same eight boards for
both of them. What the design actually needs from being single is nothing;
what it gets from being supervised is that somebody notices when it stops.

The namespace is resolved before anything else and the failure is fatal. A
build that cannot say which revision it is has no business writing rows that
another build might read: the whole point of the namespace is that a payload
carries the identity of the code that produced it, and a guessed identity is
worse than no cache at all.

`--readiness` is the prewarm gate. A deploy turns the shared read path on only
once this exits 0, because the alternative is every viewer on the site meeting
`pending` at the same moment.
"""
import argparse
import json
import logging
import signal
import sys
import threading

from app import app
from extensions import db
from features.radar import board_namespace, board_producer

logger = logging.getLogger('radar.board')

# The producer's own clock, not a copy of it. Two definitions of "now" in a
# process whose stored `as_of` is the whole point of the cache is one more than
# it can have: `--readiness` compares a stamp this file reads against one the
# loop wrote, and the day one of them grew a timezone the other would still
# look right.
_utcnow = board_producer.utcnow


def _stop_on_signals(stop):
    """SIGTERM and SIGINT set the event; the build in flight still finishes.

    Both, and not only SIGTERM: systemd sends SIGTERM and a developer sends
    SIGINT, and a producer that dropped its lease on one but not the other
    would leave a key locked for the length of a lease after every Ctrl-C.

    SIGTERM exists on Windows but cannot be delivered from outside the
    process, so registering it there is harmless rather than useful -- the
    handler is registered unconditionally because the code that runs the
    daemon is the same code either way.
    """
    def handler(number, frame):
        logger.info('board producer asked to stop signal=%s', number)
        stop.set()

    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Radar shared board producer')
    parser.add_argument('--once', action='store_true',
                        help='run a single tick and exit')
    parser.add_argument('--readiness', action='store_true',
                        help='print warm-cache readiness as JSON; '
                             'exit 0 when every standing board is fresh')
    parser.add_argument('--poll-interval', type=float,
                        default=board_producer.DEFAULT_POLL_INTERVAL,
                        help='seconds an idle loop waits before asking again')
    parser.add_argument('--owner', default=board_producer.default_owner(),
                        help='the lease owner this producer claims under')
    # Direct callers keep the no-argument contract; the entry point below
    # supplies the real CLI arguments.
    args = parser.parse_args([] if argv is None else argv)
    logging.basicConfig(level=logging.INFO)

    # Uncaught on purpose. A ConfigError here means the build cannot say which
    # revision it is, and the loudest possible answer to that is the right
    # one: the namespace is an identity, and there is no default identity.
    described = board_namespace.describe()

    with app.app_context():
        engine = db.engine
        if args.readiness:
            state = board_producer.readiness(engine, described['namespace'],
                                             _utcnow())
            print(json.dumps(state, sort_keys=True))
            return 0 if state['ready'] else 1

        logger.info(
            'radar board producer namespace=%s payload_version=%s '
            'revision=%s fingerprint=%s owner=%s',
            described['namespace'], described['payload_version'],
            described['revision'], described['fingerprint'], args.owner)

        loop = board_producer.Loop(engine, ns=described['namespace'],
                                   owner=args.owner,
                                   revision=described['revision'],
                                   now_fn=_utcnow,
                                   poll_interval=args.poll_interval)
        if args.once:
            loop.tick()
            return 0

        stop = threading.Event()
        _stop_on_signals(stop)
        loop.run(stop)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
