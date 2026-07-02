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
