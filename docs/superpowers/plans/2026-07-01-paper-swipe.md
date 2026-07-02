# ACL 2026 Paper Swipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A zero-dependency localhost webapp to swipe ACL 2026 papers (like/skip), filter by negative keywords, and export liked papers as an `.ics` calendar.

**Architecture:** `prepare_data.py` converts `paper-info.xlsx` → `papers.json` once (stdlib zip/XML parsing, in-person papers only). `server.py` (stdlib `http.server`) serves static files plus three endpoints: `GET /api/papers`, `GET|POST /api/state` (persisted to `state.json`), `GET /api/export.ics`. The UI is one static page (`static/index.html` + `app.js` + `style.css`) in vanilla JS.

**Tech Stack:** Python 3.12 stdlib only (zipfile, xml.etree, http.server, unittest). Vanilla HTML/CSS/JS. No pip, no npm, no build step.

**Spec:** `docs/superpowers/specs/2026-07-01-paper-swipe-design.md`

## Global Constraints

- Python 3 **stdlib only** — no pip installs; frontend is vanilla JS/CSS — no npm, no frameworks, no build step.
- Tests use `unittest`, run with `python3 -m unittest tests.<module> -v` from the repo root.
- Conference year is **2026**; sheet times are PDT; ICS timezone is `America/Los_Angeles`.
- Keyword matching: case-insensitive, whole-word, **titles only**.
- Generated/user data files (`papers.json`, `state.json`, `*.bak`) are gitignored, never committed.
- The source spreadsheet `paper-info.xlsx` stays untouched at the repo root.

---

### Task 1: Data preparation (`prepare_data.py`)

**Files:**
- Create: `.gitignore`
- Create: `prepare_data.py`
- Create: `tests/__init__.py` (empty)
- Test: `tests/test_prepare_data.py`

**Interfaces:**
- Consumes: `paper-info.xlsx` (sheet1; preamble rows, then a header row whose column A is `Paper number`; columns A=id, B=title, C=abstract, D=authors, E=presentation mode, H=room, I=session, J=session name, K=date like `Sun. July 5`, L=time like `14:00-15:30` or ` 12:45 - 14:15`).
- Produces: `papers.json` — array of `{id, title, abstract, authors, room, session, sessionName, date, time, start, end}` where `start`/`end` are `"2026-07-05T14:00:00"`-style local ISO strings or `null` when the session time is unparseable. Also these importable functions: `read_rows(path) -> iterator of {col_letter: str}`, `parse_session_datetime(date_str, time_str) -> (start, end) | None`, `extract_papers(rows) -> (papers, skipped_count)`.

- [ ] **Step 1: Create `.gitignore`**

```gitignore
.DS_Store
__pycache__/
papers.json
state.json
*.bak
*.tmp
```

- [ ] **Step 2: Write the failing tests**

Create empty `tests/__init__.py`, then `tests/test_prepare_data.py`:

```python
import os
import tempfile
import unittest
import zipfile
from xml.sax.saxutils import escape

from prepare_data import extract_papers, parse_session_datetime, read_rows

HEADER = ['Paper number', 'Title', 'Abstract', 'Authors Names', 'Presentation mode',
          'Presenters Name', 'Registered', 'Room Location', 'Session',
          'Underline Session Name', 'Session Date', 'Session time PDT']


def make_xlsx(path, rows):
    """Build a minimal xlsx with inline-string cells; rows are lists of column A.. values."""
    xml_rows = []
    for r, row in enumerate(rows, start=1):
        cells = ''.join(
            f'<c r="{chr(65 + i)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
            for i, v in enumerate(row))
        xml_rows.append(f'<row r="{r}">{cells}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>' + ''.join(xml_rows) + '</sheetData></worksheet>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/worksheets/sheet1.xml', sheet)


def paper_row(pid='1234-ACL', title='A Paper', mode='In-Person',
              date='Sun. July 5', time='14:00-15:30'):
    return [pid, title, 'An abstract.', 'Ada Lovelace, Alan Turing', mode,
            'Ada Lovelace', 'Yes', 'Harbor A', 'Session 3', 'Poster Session C',
            date, time]


class ParseSessionDatetimeTest(unittest.TestCase):
    def test_plain_range(self):
        self.assertEqual(parse_session_datetime('Sun. July 5', '14:00-15:30'),
                         ('2026-07-05T14:00:00', '2026-07-05T15:30:00'))

    def test_spaced_range(self):
        self.assertEqual(parse_session_datetime('Mon. July 6', ' 12:45 - 14:15'),
                         ('2026-07-06T12:45:00', '2026-07-06T14:15:00'))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_session_datetime('Sun. July 5', 'TBD'))
        self.assertIsNone(parse_session_datetime('', '14:00-15:30'))


class ExtractPapersTest(unittest.TestCase):
    def build(self, rows):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 't.xlsx')
            make_xlsx(path, rows)
            return extract_papers(read_rows(path))

    def test_keeps_in_person_drops_virtual_ignores_preamble(self):
        papers, skipped = self.build([
            ['Some preamble note'],
            HEADER,
            paper_row(pid='1-ACL'),
            paper_row(pid='2-ACL', mode='Virtual'),
        ])
        self.assertEqual([p['id'] for p in papers], ['1-ACL'])
        self.assertEqual(skipped, 0)
        self.assertEqual(papers[0]['start'], '2026-07-05T14:00:00')
        self.assertEqual(papers[0]['end'], '2026-07-05T15:30:00')
        self.assertEqual(papers[0]['title'], 'A Paper')
        self.assertEqual(papers[0]['sessionName'], 'Poster Session C')
        self.assertNotIn('mode', papers[0])

    def test_missing_title_is_skipped_and_counted(self):
        papers, skipped = self.build([HEADER, paper_row(title='')])
        self.assertEqual(papers, [])
        self.assertEqual(skipped, 1)

    def test_bad_time_kept_with_null_start(self):
        papers, _ = self.build([HEADER, paper_row(time='TBD')])
        self.assertEqual(len(papers), 1)
        self.assertIsNone(papers[0]['start'])
        self.assertIsNone(papers[0]['end'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_prepare_data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'prepare_data'`

- [ ] **Step 4: Write `prepare_data.py`**

```python
"""One-time converter: paper-info.xlsx -> papers.json (in-person papers only)."""
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
YEAR = 2026
MONTHS = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], start=1)}
COLUMNS = {'A': 'id', 'B': 'title', 'C': 'abstract', 'D': 'authors', 'E': 'mode',
           'H': 'room', 'I': 'session', 'J': 'sessionName', 'K': 'date', 'L': 'time'}


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def read_rows(path):
    """Yield one {column_letter: cell_text} dict per spreadsheet row of sheet1."""
    z = zipfile.ZipFile(path)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
                  for si in root.findall(NS + 'si')]
    sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    for row in sheet.find(NS + 'sheetData').findall(NS + 'row'):
        vals = {}
        for c in row.findall(NS + 'c'):
            col = re.match(r'[A-Z]+', c.get('r')).group()
            inline = c.find(NS + 'is')
            if inline is not None:
                vals[col] = ''.join(t.text or '' for t in inline.iter(NS + 't'))
                continue
            v = c.find(NS + 'v')
            if v is not None:
                vals[col] = shared[int(v.text)] if c.get('t') == 's' else (v.text or '')
        yield vals


def parse_session_datetime(date_str, time_str):
    """('Sun. July 5', '14:00-15:30') -> ('2026-07-05T14:00:00', '2026-07-05T15:30:00'), or None."""
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2})', clean(date_str))
    if not m or m.group(1).lower() not in MONTHS:
        return None
    month, day = MONTHS[m.group(1).lower()], int(m.group(2))
    t = re.fullmatch(r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})', clean(time_str))
    if not t:
        return None
    h1, m1, h2, m2 = (int(g) for g in t.groups())
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    return (f'{YEAR}-{month:02d}-{day:02d}T{h1:02d}:{m1:02d}:00',
            f'{YEAR}-{month:02d}-{day:02d}T{h2:02d}:{m2:02d}:00')


def extract_papers(rows):
    """Return (papers, skipped_count) from rows after the 'Paper number' header row."""
    papers, skipped = [], 0
    in_data = False
    for vals in rows:
        if not in_data:
            if clean(vals.get('A', '')).lower() == 'paper number':
                in_data = True
            continue
        p = {name: clean(vals.get(col, '')) for col, name in COLUMNS.items()}
        if not p['id'] or not p['title']:
            skipped += 1
            continue
        if p.pop('mode').lower() != 'in-person':
            continue
        span = parse_session_datetime(p['date'], p['time'])
        p['start'], p['end'] = span if span else (None, None)
        papers.append(p)
    return papers, skipped


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'paper-info.xlsx'
    papers, skipped = extract_papers(read_rows(src))
    with open('papers.json', 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)
    no_time = sum(1 for p in papers if not p['start'])
    print(f'Wrote {len(papers)} in-person papers to papers.json '
          f'({skipped} malformed rows skipped, {no_time} with unrecognized session times).')


if __name__ == '__main__':
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_prepare_data -v`
Expected: `OK` (6 tests)

- [ ] **Step 6: Run against the real spreadsheet and sanity-check**

Run: `python3 prepare_data.py`
Expected: a line like `Wrote NNNN in-person papers to papers.json (M malformed rows skipped, K with unrecognized session times).` where NNNN is in the low thousands (sheet has ~4,870 data rows; virtual papers are excluded). Spot-check: `python3 -c "import json; ps=json.load(open('papers.json')); print(len(ps)); print(ps[0])"` — the first paper should have a real title, and `start` of the form `2026-07-0XT...`. If NNNN is 0 or K is a large fraction of NNNN, stop and investigate before proceeding.

- [ ] **Step 7: Commit**

```bash
git add .gitignore prepare_data.py tests/__init__.py tests/test_prepare_data.py
git commit -m "feat: convert paper-info.xlsx to papers.json (in-person only)"
```

---

### Task 2: State persistence and ICS generation (`server.py` logic)

**Files:**
- Create: `server.py` (logic functions only; HTTP wiring is Task 3)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: paper dicts as produced by Task 1 (`{id, title, abstract, authors, room, session, sessionName, date, time, start, end}`).
- Produces: `load_state(path) -> {'keywords': list, 'decisions': dict}`, `save_state(path, state)`, `build_ics(papers, decisions) -> str`. Decisions map paper id → `"like" | "skip" | "filtered"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server.py`:

```python
import os
import tempfile
import threading
import unittest

from server import build_ics, load_state, save_state

PAPER = {'id': '1-ACL', 'title': 'Cats, Dogs; and LLMs', 'abstract': 'x', 'authors': 'A',
         'room': 'Harbor A', 'session': 'Session 3', 'sessionName': 'Poster Session C',
         'date': 'Sun. July 5', 'time': '14:00-15:30',
         'start': '2026-07-05T14:00:00', 'end': '2026-07-05T15:30:00'}


def paper(**over):
    return {**PAPER, **over}


class BuildIcsTest(unittest.TestCase):
    def test_groups_same_session_into_one_event(self):
        papers = [paper(id='1-ACL'), paper(id='2-ACL', title='Second Paper'),
                  paper(id='3-ACL', sessionName='Oral Session B', time='16:00-17:30',
                        start='2026-07-05T16:00:00', end='2026-07-05T17:30:00')]
        ics = build_ics(papers, {'1-ACL': 'like', '2-ACL': 'like', '3-ACL': 'like'})
        self.assertEqual(ics.count('BEGIN:VEVENT'), 2)
        self.assertIn('DTSTART;TZID=America/Los_Angeles:20260705T140000', ics)
        self.assertIn('DTEND;TZID=America/Los_Angeles:20260705T153000', ics)
        self.assertIn('SUMMARY:Poster Session C (2 papers)', ics)
        self.assertIn('BEGIN:VTIMEZONE', ics)

    def test_skips_unliked_and_untimed_papers(self):
        papers = [paper(id='1-ACL'), paper(id='2-ACL', start=None, end=None)]
        ics = build_ics(papers, {'1-ACL': 'skip', '2-ACL': 'like'})
        self.assertEqual(ics.count('BEGIN:VEVENT'), 0)

    def test_escapes_special_characters(self):
        ics = build_ics([paper()], {'1-ACL': 'like'})
        self.assertIn('Cats\\, Dogs\\; and LLMs', ics)

    def test_folds_lines_to_75_octets(self):
        ics = build_ics([paper(title='T' * 200)], {'1-ACL': 'like'})
        for line in ics.split('\r\n'):
            self.assertLessEqual(len(line.encode('utf-8')), 75)

    def test_folds_multibyte_lines_to_75_octets(self):
        ics = build_ics([paper(title='语言模型' * 50)], {'1-ACL': 'like'})
        for line in ics.split('\r\n'):
            self.assertLessEqual(len(line.encode('utf-8')), 75)


class StateTest(unittest.TestCase):
    def test_missing_file_gives_empty_state(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_state(os.path.join(d, 'state.json')),
                             {'keywords': [], 'decisions': {}})

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'state.json')
            state = {'keywords': ['agent'], 'decisions': {'1-ACL': 'like'}}
            save_state(path, state)
            self.assertEqual(load_state(path), state)

    def test_corrupt_file_is_backed_up_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'state.json')
            with open(path, 'w') as f:
                f.write('{not json')
            self.assertEqual(load_state(path), {'keywords': [], 'decisions': {}})
            self.assertTrue(os.path.exists(path + '.bak'))

    def test_concurrent_saves_never_corrupt_state(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'state.json')
            states = [{'keywords': [], 'decisions': {str(i): 'like'}} for i in range(2)]

            def hammer(state):
                for _ in range(50):
                    save_state(path, state)

            threads = [threading.Thread(target=hammer, args=(s,)) for s in states]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            final = load_state(path)
            self.assertIn(final, states)
            self.assertFalse(os.path.exists(path + '.bak'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_server -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Write `server.py` logic functions**

```python
"""Localhost server for the ACL 2026 paper swipe app. Run: python3 server.py"""
import json
import os
import re
import shutil
import threading
from datetime import datetime, timezone

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_server -v`
Expected: `OK` (9 tests)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add state persistence and per-session ICS generation"
```

---

### Task 3: HTTP wiring (`server.py` routes)

**Files:**
- Modify: `server.py` (append handler + main below the Task 2 functions)

**Interfaces:**
- Consumes: `load_state`, `save_state`, `build_ics`, module constants from Task 2.
- Produces: `GET /` → `static/index.html`; `GET /api/papers` → papers.json content; `GET /api/state` → state JSON; `POST /api/state` (body `{"keywords": [...], "decisions": {...}}`) → `{"ok": true}`; `GET /api/export.ics` → `text/calendar` download named `acl2026-schedule.ics`. Malformed POST bodies → 400.

- [ ] **Step 1: Append the handler and main to `server.py`**

Add to the imports at the top of the file:

```python
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
```

Append at the bottom:

```python
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
```

- [ ] **Step 2: Re-run unit tests (import must still work)**

Run: `python3 -m unittest tests.test_server -v`
Expected: `OK` (7 tests)

- [ ] **Step 3: Smoke-test the endpoints**

`papers.json` must exist from Task 1 Step 6. Run in the background, then curl:

```bash
python3 server.py --no-browser &
sleep 1
curl -s localhost:8000/api/state
# expected: {"keywords": [], "decisions": {}}
curl -s localhost:8000/api/papers | head -c 200
# expected: JSON array starting with [{"id": ...
curl -s -X POST localhost:8000/api/state -H 'Content-Type: application/json' \
  -d '{"keywords":["speech"],"decisions":{"3034-CL":"like"}}'
# expected: {"ok": true}
curl -s localhost:8000/api/export.ics | head -8
# expected: BEGIN:VCALENDAR / VERSION:2.0 / ... / BEGIN:VTIMEZONE
curl -s -X POST localhost:8000/api/state -d 'garbage' -o /dev/null -w '%{http_code}\n'
# expected: 400
kill %1
rm -f state.json   # remove smoke-test state
```

(`GET /` will 404 until Task 4 creates `static/index.html` — that's fine; don't test it here.)

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: add HTTP routes for papers, state, and ICS export"
```

---

### Task 4: Frontend (`static/index.html`, `static/style.css`, `static/app.js`)

**Files:**
- Create: `static/index.html`
- Create: `static/style.css`
- Create: `static/app.js`

**Interfaces:**
- Consumes: `GET /api/papers`, `GET /api/state`, `POST /api/state`, `GET /api/export.ics` exactly as produced by Task 3.
- Produces: the complete UI. Keys: `←` skip, `→` like, `Space` toggle details (abstract + authors together, one sticky toggle), `Z` undo. Decisions: `like`/`skip` from swiping, `filtered` from keywords. No automated tests — manual checklist in Step 4.

- [ ] **Step 1: Create `static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ACL 2026 Paper Swipe</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>ACL 2026</h1>
  <nav>
    <button id="tab-swipe" class="tab active">Swipe</button>
    <button id="tab-schedule" class="tab">Schedule (<span id="liked-count">0</span>)</button>
  </nav>
  <div id="progress">…</div>
</header>
<div id="layout">
  <aside>
    <h2>Negative keywords</h2>
    <form id="kw-form">
      <input id="kw-input" type="text" placeholder="add keyword, press Enter" autocomplete="off">
    </form>
    <ul id="kw-list"></ul>
    <p class="hint" id="kw-hint"></p>
    <div class="help">
      <p>→ like &nbsp;·&nbsp; ← skip</p>
      <p>space details &nbsp;·&nbsp; Z undo</p>
    </div>
  </aside>
  <main>
    <section id="swipe-view">
      <div id="card-area"></div>
      <div id="controls">
        <button id="btn-skip" title="left arrow">✕ Skip</button>
        <button id="btn-details" title="space">Details</button>
        <button id="btn-like" title="right arrow">♥ Like</button>
      </div>
    </section>
    <section id="schedule-view" hidden>
      <div id="schedule-header">
        <h2>Your schedule</h2>
        <a id="btn-ics" href="/api/export.ics">Download .ics</a>
      </div>
      <div id="schedule"></div>
    </section>
  </main>
</div>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `static/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f6f6f4; color: #1a1a1a; }
header { display: flex; align-items: center; gap: 24px; padding: 12px 20px;
         background: #fff; border-bottom: 1px solid #e2e2de; }
header h1 { font-size: 18px; margin: 0; }
#progress { margin-left: auto; font-variant-numeric: tabular-nums; color: #666; }
.tab { background: none; border: none; padding: 8px 12px; font-size: 14px;
       cursor: pointer; border-radius: 6px; color: #555; }
.tab.active { background: #ececea; color: #000; font-weight: 600; }
#layout { display: flex; min-height: calc(100vh - 57px); }
aside { width: 250px; flex-shrink: 0; padding: 20px; border-right: 1px solid #e2e2de; }
aside h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em;
           color: #888; margin: 0 0 10px; }
#kw-input { width: 100%; padding: 8px 10px; border: 1px solid #d5d5d0;
            border-radius: 6px; font-size: 14px; }
#kw-list { list-style: none; padding: 0; margin: 12px 0; }
#kw-list li { display: flex; justify-content: space-between; align-items: center;
              padding: 4px 0; font-size: 14px; }
#kw-list button, .session li button { background: none; border: none; color: #b55;
                                      cursor: pointer; font-size: 13px; padding: 0 4px; }
.hint { font-size: 12px; color: #888; min-height: 1em; }
.help { margin-top: 24px; font-size: 12px; color: #aaa; }
.help p { margin: 4px 0; }
main { flex: 1; padding: 32px; display: flex; justify-content: center; }
#swipe-view { width: 100%; max-width: 660px; display: flex;
              flex-direction: column; align-items: center; }
#card-area { width: 100%; min-height: 320px; display: flex;
             align-items: flex-start; justify-content: center; }
.card { width: 100%; background: #fff; border: 1px solid #e2e2de; border-radius: 14px;
        padding: 28px; box-shadow: 0 2px 10px rgba(0,0,0,.05);
        transition: transform .18s ease, opacity .18s ease; }
.card h2 { font-size: 22px; line-height: 1.35; margin: 12px 0 0; }
.chip { font-size: 12.5px; color: #777; }
.details { margin-top: 16px; border-top: 1px solid #eee; padding-top: 14px;
           font-size: 14.5px; line-height: 1.55; color: #333; }
.authors { color: #777; font-size: 13px; margin: 0 0 10px; }
.card.out-left { transform: translateX(-130%) rotate(-5deg); opacity: 0; }
.card.out-right { transform: translateX(130%) rotate(5deg); opacity: 0; }
.card.done { text-align: center; }
#controls { display: flex; gap: 14px; margin-top: 22px; }
#controls button { padding: 10px 22px; font-size: 15px; border: 1px solid #d5d5d0;
                   background: #fff; border-radius: 999px; cursor: pointer; }
#controls button:hover { background: #f0f0ee; }
#schedule-view { width: 100%; max-width: 760px; }
#schedule-header { display: flex; align-items: center; justify-content: space-between; }
#schedule-header h2 { font-size: 20px; }
#btn-ics { background: #1a7f37; color: #fff; padding: 9px 16px; border-radius: 8px;
           text-decoration: none; font-size: 14px; }
.session { background: #fff; border: 1px solid #e2e2de; border-radius: 10px;
           padding: 14px 18px; margin: 14px 0; }
.session h3 { margin: 0 0 8px; font-size: 15px; }
.session ul { list-style: none; margin: 0; padding: 0; }
.session li { display: flex; gap: 8px; padding: 5px 0; font-size: 14px;
              align-items: baseline; }
.warn { color: #b06000; font-size: 13px; }
```

- [ ] **Step 3: Create `static/app.js`**

```javascript
'use strict';

let papers = [];
let keywords = [];
let decisions = {};
let queue = [];
let undoStack = [];
let showDetails = false;
let view = 'swipe';
let animating = false;

const $ = id => document.getElementById(id);

async function init() {
  const [pRes, sRes] = await Promise.all([fetch('/api/papers'), fetch('/api/state')]);
  papers = await pRes.json();
  const state = await sRes.json();
  keywords = state.keywords;
  decisions = state.decisions;
  rebuildQueue();
  renderKeywords();
  renderCard();
  renderProgress();
}

function saveState() {
  fetch('/api/state', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, decisions}),
  });
}

function rebuildQueue() {
  queue = papers.filter(p => !(p.id in decisions));
}

function keywordRegex(kw) {
  const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^A-Za-z0-9])${esc}([^A-Za-z0-9]|$)`, 'i');
}

function matchesAny(title, kws) {
  return kws.some(kw => keywordRegex(kw).test(title));
}

function addKeyword(raw) {
  const kw = raw.trim().toLowerCase();
  if (!kw || keywords.includes(kw)) return;
  keywords.push(kw);
  let n = 0;
  for (const p of papers) {
    if (!(p.id in decisions) && keywordRegex(kw).test(p.title)) {
      decisions[p.id] = 'filtered';
      n++;
    }
  }
  $('kw-hint').textContent = `“${kw}” filtered out ${n} papers`;
  afterMutation();
}

function removeKeyword(kw) {
  keywords = keywords.filter(k => k !== kw);
  let n = 0;
  for (const p of papers) {
    if (decisions[p.id] === 'filtered' && !matchesAny(p.title, keywords)) {
      delete decisions[p.id];
      n++;
    }
  }
  $('kw-hint').textContent = `removed “${kw}”, ${n} papers back in the deck`;
  afterMutation();
}

function afterMutation() {
  rebuildQueue();
  saveState();
  renderKeywords();
  renderCard();
  renderProgress();
  if (view === 'schedule') renderSchedule();
}

function decide(action) {  // 'like' | 'skip'
  const p = queue[0];
  if (!p || animating) return;
  animating = true;
  decisions[p.id] = action;
  undoStack.push(p.id);
  const card = document.getElementById('card');
  if (card) card.classList.add(action === 'like' ? 'out-right' : 'out-left');
  setTimeout(() => {
    animating = false;
    queue.shift();
    saveState();
    renderCard();
    renderProgress();
  }, 180);
}

function undo() {
  const id = undoStack.pop();
  if (!id) return;
  delete decisions[id];
  afterMutation();
}

function toggleDetails() {
  showDetails = !showDetails;
  renderCard();
}

function renderCard() {
  const area = $('card-area');
  const p = queue[0];
  if (!p) {
    const liked = papers.filter(x => decisions[x.id] === 'like').length;
    area.innerHTML = `<div class="card done"><h2>All done 🎉</h2>
      <p>You liked ${liked} papers. Check the Schedule tab.</p></div>`;
    return;
  }
  const card = document.createElement('div');
  card.className = 'card';
  card.id = 'card';
  const chip = document.createElement('div');
  chip.className = 'chip';
  chip.textContent = `${p.date} · ${p.time}` + (p.sessionName ? ` · ${p.sessionName}` : '');
  const title = document.createElement('h2');
  title.textContent = p.title;
  card.append(chip, title);
  if (showDetails) {
    const det = document.createElement('div');
    det.className = 'details';
    const auth = document.createElement('p');
    auth.className = 'authors';
    auth.textContent = p.authors;
    const abs = document.createElement('p');
    abs.textContent = p.abstract;
    det.append(auth, abs);
    card.append(det);
  }
  area.replaceChildren(card);
}

function renderProgress() {
  let done = 0, total = 0, liked = 0;
  for (const p of papers) {
    const d = decisions[p.id];
    if (d === 'like') liked++;
    if (d === 'filtered') continue;
    total++;
    if (d === 'like' || d === 'skip') done++;
  }
  $('progress').textContent = `${done.toLocaleString()} / ${total.toLocaleString()}`;
  $('liked-count').textContent = liked;
}

function renderKeywords() {
  const ul = $('kw-list');
  ul.replaceChildren();
  for (const kw of keywords) {
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = kw;
    const btn = document.createElement('button');
    btn.textContent = '✕';
    btn.title = 'remove keyword';
    btn.onclick = () => removeKeyword(kw);
    li.append(span, btn);
    ul.append(li);
  }
}

function renderSchedule() {
  const container = $('schedule');
  const liked = papers.filter(p => decisions[p.id] === 'like');
  container.replaceChildren();
  if (!liked.length) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'No liked papers yet — go swipe!';
    container.append(p);
    return;
  }
  const groups = new Map();
  for (const p of liked) {
    const name = p.sessionName || p.session || 'Unknown session';
    const key = `${p.start || '9999'}|${p.time}|${name}`;
    if (!groups.has(key)) groups.set(key, {p0: p, name, papers: []});
    groups.get(key).papers.push(p);
  }
  const sorted = [...groups.values()].sort((a, b) =>
    `${a.p0.start || '9999'}|${a.p0.time}`.localeCompare(`${b.p0.start || '9999'}|${b.p0.time}`));
  for (const g of sorted) {
    const sec = document.createElement('section');
    sec.className = 'session';
    const h = document.createElement('h3');
    h.textContent = `${g.p0.date} · ${g.p0.time} — ${g.name}`;
    sec.append(h);
    if (!g.p0.start) {
      const warn = document.createElement('p');
      warn.className = 'warn';
      warn.textContent = '⚠ Unrecognized session time — not included in the .ics export';
      sec.append(warn);
    }
    const ul = document.createElement('ul');
    for (const p of g.papers) {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = '✕';
      btn.title = 'remove from schedule';
      btn.onclick = () => {
        decisions[p.id] = 'skip';
        undoStack.push(p.id);
        saveState();
        renderSchedule();
        renderProgress();
      };
      const span = document.createElement('span');
      span.textContent = `${p.title} — ${p.room} (${p.id})`;
      li.append(btn, span);
      ul.append(li);
    }
    sec.append(ul);
    container.append(sec);
  }
}

function showView(v) {
  view = v;
  $('swipe-view').hidden = v !== 'swipe';
  $('schedule-view').hidden = v !== 'schedule';
  $('tab-swipe').classList.toggle('active', v === 'swipe');
  $('tab-schedule').classList.toggle('active', v === 'schedule');
  if (v === 'schedule') renderSchedule();
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'z' || e.key === 'Z') { undo(); return; }
  if (view !== 'swipe') return;
  if (e.key === 'ArrowRight') decide('like');
  else if (e.key === 'ArrowLeft') decide('skip');
  else if (e.key === ' ') { e.preventDefault(); toggleDetails(); }
});

$('kw-form').addEventListener('submit', e => {
  e.preventDefault();
  addKeyword($('kw-input').value);
  $('kw-input').value = '';
});
$('btn-like').onclick = () => decide('like');
$('btn-skip').onclick = () => decide('skip');
$('btn-details').onclick = toggleDetails;
$('tab-swipe').onclick = () => showView('swipe');
$('tab-schedule').onclick = () => showView('schedule');

init();
```

- [ ] **Step 4: Manual verification checklist**

Start `python3 server.py` and open `http://localhost:8000/`. Verify each:

1. A card shows a real paper title with a date/time/session chip; progress shows `0 / N`.
2. `→` likes (card slides right), `←` skips (slides left); progress counter increments; rapid keypresses don't skip papers.
3. `Space` shows abstract + authors on the card; `Space` again hides; the toggle stays on across cards.
4. `Z` brings the last swiped paper back and decrements progress.
5. Add keyword `speech` → hint reports how many papers were filtered; progress denominator drops by the same amount; the current card is replaced if its title matched.
6. Remove the keyword → hint reports papers returned; denominator recovers.
7. Typing `z` inside the keyword input does NOT trigger undo.
8. Schedule tab: liked papers grouped under `date · time — session` headings with room + id; ✕ removes a paper; badge count matches.
9. Download .ics saves `acl2026-schedule.ics`; open it (e.g. `open acl2026-schedule.ics` into Calendar.app) — events at the right PDT times, one event per session, papers in the description.
10. Restart the server, reload the page — keywords and progress are intact (state.json).

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/style.css static/app.js
git commit -m "feat: add swipe UI with keywords, schedule view, and ICS download"
```

---

### Task 5: README and end-to-end check

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: user-facing run instructions.

- [ ] **Step 1: Create `README.md`**

```markdown
# ACL 2026 Paper Swipe

Tinder-style triage for ACL 2026 papers: swipe through titles, filter with
negative keywords, and export the sessions you care about as a calendar file.

## Run

```bash
python3 prepare_data.py   # once: paper-info.xlsx -> papers.json (in-person papers)
python3 server.py         # serves http://localhost:8000 and opens your browser
```

No dependencies beyond Python 3 stdlib.

## Use

- **→** like · **←** skip · **Space** show/hide abstract & authors · **Z** undo
- Add negative keywords in the sidebar (case-insensitive, whole-word, matched
  against titles). Matching unseen papers are auto-skipped; deleting a keyword
  brings them back.
- The **Schedule** tab groups liked papers by session; **Download .ics** exports
  one calendar event per session (times in America/Los_Angeles).

Progress is saved to `state.json` after every action — quit and resume anytime.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```
```

- [ ] **Step 2: Full test suite**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: `OK` (15 tests)

- [ ] **Step 3: End-to-end sanity pass**

Repeat the quick loop: `rm -f state.json`, start `python3 server.py --no-browser`, curl `/api/state`, like one paper via POST, download `/api/export.ics`, confirm it contains one `VEVENT` with `TZID=America/Los_Angeles`. Then `kill %1 && rm -f state.json` so the user starts clean.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with run and usage instructions"
```
