"""Localhost server for the ACL 2026 paper swipe app. Run: python3 server.py"""
import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
PAPERS_PATH = os.path.join(BASE_DIR, 'papers.json')
STATE_PATH = os.path.join(BASE_DIR, 'state.json')
PORT = 8000

VTIMEZONE_LINES = [
    'BEGIN:VTIMEZONE',
    'TZID:America/Los_Angeles',
    'BEGIN:DAYLIGHT',
    'TZOFFSETFROM:-0800',
    'TZOFFSETTO:-0700',
    'TZNAME:PDT',
    'DTSTART:19700308T020000',
    'RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU',
    'END:DAYLIGHT',
    'BEGIN:STANDARD',
    'TZOFFSETFROM:-0700',
    'TZOFFSETTO:-0800',
    'TZNAME:PST',
    'DTSTART:19701101T020000',
    'RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU',
    'END:STANDARD',
    'END:VTIMEZONE',
]

_SAVE_LOCK = threading.Lock()


def empty_state():
    return {'keywords': [], 'decisions': {}}


def load_state(path):
    """Read state; on a corrupt or malformed file, back it up and start fresh."""
    if not os.path.exists(path):
        return empty_state()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data.get('keywords'), list) or not isinstance(data.get('decisions'), dict):
            raise ValueError('unexpected state shape')
        return {'keywords': data['keywords'], 'decisions': data['decisions']}
    except (ValueError, OSError):
        shutil.copyfile(path, path + '.bak')
        return empty_state()


def save_state(path, state):
    tmp = path + '.tmp'
    with _SAVE_LOCK:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)


def ics_escape(text):
    return (text.replace('\\', '\\\\').replace(';', '\\;')
                .replace(',', '\\,').replace('\n', '\\n'))


def fold(line):
    """Split a content line per RFC 5545 (continuation lines begin with a space)."""
    parts = []
    while len(line.encode('utf-8')) > 74:
        cut = 70
        while len(line[:cut].encode('utf-8')) > 70:
            cut -= 1
        parts.append(line[:cut])
        line = ' ' + line[cut:]
    parts.append(line)
    return parts


def ics_datetime(iso):
    """'2026-07-05T14:00:00' -> '20260705T140000'"""
    return iso.replace('-', '').replace(':', '')


def build_ics(papers, decisions):
    """One VEVENT per session; liked papers listed in the description."""
    sessions = {}
    for p in papers:
        if decisions.get(p['id']) != 'like' or not p['start']:
            continue
        name = p['sessionName'] or p['session'] or 'Unknown session'
        sessions.setdefault((p['start'], p['end'], name), []).append(p)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0',
             'PRODID:-//acl2026-swipe//EN', 'CALSCALE:GREGORIAN']
    lines += VTIMEZONE_LINES
    for (start, end, name), plist in sorted(sessions.items()):
        uid = re.sub(r'[^a-z0-9]+', '-', f'{start}-{name}'.lower()).strip('-')
        desc = '\n'.join(f'- {p["title"]} [{p["room"]}] ({p["id"]})' for p in plist)
        rooms = sorted({p['room'] for p in plist if p['room']})
        count = f'{len(plist)} paper' + ('s' if len(plist) > 1 else '')
        lines += ['BEGIN:VEVENT',
                  f'UID:{uid}@acl2026-swipe',
                  f'DTSTAMP:{stamp}',
                  f'DTSTART;TZID=America/Los_Angeles:{ics_datetime(start)}',
                  f'DTEND;TZID=America/Los_Angeles:{ics_datetime(end)}',
                  f'SUMMARY:{ics_escape(name)} ({count})',
                  f'LOCATION:{ics_escape(", ".join(rooms))}',
                  f'DESCRIPTION:{ics_escape(desc)}',
                  'END:VEVENT']
    lines.append('END:VCALENDAR')
    out = []
    for line in lines:
        out.extend(fold(line))
    return '\r\n'.join(out) + '\r\n'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/papers':
            with open(PAPERS_PATH, encoding='utf-8') as f:
                self.send_json(json.load(f))
        elif self.path == '/api/state':
            self.send_json(load_state(STATE_PATH))
        elif self.path == '/api/export.ics':
            with open(PAPERS_PATH, encoding='utf-8') as f:
                papers = json.load(f)
            body = build_ics(papers, load_state(STATE_PATH)['decisions']).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/calendar; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="acl2026-schedule.ics"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != '/api/state':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or not isinstance(data.get('keywords'), list) \
                    or not isinstance(data.get('decisions'), dict):
                raise ValueError('unexpected state shape')
        except ValueError:
            self.send_json({'error': 'invalid state'}, status=400)
            return
        save_state(STATE_PATH, {'keywords': data['keywords'], 'decisions': data['decisions']})
        self.send_json({'ok': True})

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet while swiping


def main():
    if not os.path.exists(PAPERS_PATH):
        raise SystemExit('papers.json not found — run: python3 prepare_data.py')
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    url = f'http://localhost:{PORT}/'
    print(f'Serving on {url}  (Ctrl-C to stop)')
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
