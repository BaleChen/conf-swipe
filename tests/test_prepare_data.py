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
