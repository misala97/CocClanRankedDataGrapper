"""The runnable VC1 preview.

Serves `personal_apps/` as static files AND answers `/radar/api/board`, so the
hub behaves the way it does in production: changing a filter issues a request,
the answer arrives, and the controls echo what was actually asked for. Without
that the preview blanks the moment anyone touches a control, and a preview that
cannot be used is not a preview.

It is NOT the application. There is no database, no login and no watch writes;
it exists to put the built bundle in front of a human with controlled data.

    PYTHONPATH=. py -3.12 scratchpad/vc1_serve.py [port]

Then open   http://127.0.0.1:5071/scratchpad/vc1/real.html#chatter
            http://127.0.0.1:5071/scratchpad/vc1/fixture.html#chatter
"""
import copy
import functools
import http.server
import json
import pathlib
import socketserver
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ROOT / 'scratchpad/vc1'
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5071

# Which payload a request belongs to, taken from the Referer the browser sends
# with the fetch. The island builds its own query string and has no idea this
# server exists, so the page it is running in is the only signal -- and it is
# the right one: real and fictional rows must never meet in one answer.
DATASETS = {}


def load():
    for page in PAGES.glob('*.html'):
        text = page.read_text(encoding='utf-8')
        start = text.index('id="radar-hub-data">') + len('id="radar-hub-data">')
        end = text.index('</script>', start)
        shell = json.loads(text[start:end].replace('<\\/', '</'))
        DATASETS[page.stem] = shell['board']
    print(f'datasets: {", ".join(sorted(DATASETS))}')


class Handler(http.server.SimpleHTTPRequestHandler):
    def dataset(self):
        referer = self.headers.get('Referer') or ''
        stem = pathlib.PurePosixPath(
            urllib.parse.urlparse(referer).path).stem
        return stem or 'fixture'

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == '/radar/api/board':
            return self.board(query)
        if parsed.path.startswith('/radar/api/ticker/'):
            return self.canned(f'ticker-{parsed.path.rsplit("/", 1)[-1]}')
        if parsed.path == '/radar/api/activity':
            return self.canned(f'activity-{query.get("days", ["7"])[0]}')
        if parsed.path == '/radar/api/ops':
            return self.canned('ops')
        if parsed.path == '/radar/api/search':
            return self.send_json({'matches': []})
        return super().do_GET()

    def canned(self, name):
        # A dataset-specific answer wins, so the fictional page can show
        # fictional activity while the real page keeps the real, mostly-empty
        # one. Neither ever borrows the other's numbers.
        for candidate in (f'{self.dataset()}-{name}', name):
            path = PAGES / 'api' / f'{candidate}.json'
            if path.exists():
                return self.send_json(json.loads(path.read_text('utf-8')))
        return self.send_json({'error': 'not in this preview'}, 404)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def board(self, query):
        def one(name, default=None):
            return query.get(name, [default])[0]

        payload = copy.deepcopy(
            DATASETS.get(self.dataset(), DATASETS['fixture']))
        # Echo the selection back, which is what the real API does and what the
        # controls read to show themselves as selected.
        sources = [s for s in (one('sources') or '').split(',') if s]
        if sources:
            payload['sources'] = sources
        if one('window'):
            payload['window_hours'] = int(one('window'))
        if one('min_venues'):
            payload['min_venues'] = int(one('min_venues'))
        if one('market'):
            payload['market'] = one('market')
        segments = [s for s in (one('segments') or '').split(',') if s]
        payload['segments'] = segments
        if one('sort'):
            payload['sort'] = one('sort')
        if one('dir'):
            payload['dir'] = one('dir')
        self.send_json(payload)

    def log_message(self, *args):
        pass


def main():
    load()
    handler = functools.partial(Handler, directory=str(ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', PORT), handler) as srv:
        print(f'preview: http://127.0.0.1:{PORT}/scratchpad/vc1/real.html#chatter')
        print(f'         http://127.0.0.1:{PORT}/scratchpad/vc1/fixture.html#chatter')
        srv.serve_forever()


if __name__ == '__main__':
    main()
