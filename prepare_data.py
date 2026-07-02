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
