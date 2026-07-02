"""Localhost server for the ACL 2026 paper swipe app. Run: python3 server.py"""
import json
import os
import re
import shutil
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
        parts.append(line[:70])
        line = ' ' + line[70:]
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
