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
- Use one browser tab at a time — the app saves the full state after every
  action, so a stale second tab can overwrite a fresh one.

Progress is saved to `state.json` after every action — quit and resume anytime.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```
