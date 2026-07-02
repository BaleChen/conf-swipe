# ACL 2026 Paper Swipe — Design

**Date:** 2026-07-01
**Goal:** A localhost webapp to triage ACL 2026 papers Tinder-style and export the resulting schedule as a calendar file.

## Overview

The user attends ACL 2026 in person and needs to pick papers from ~4,900 candidates in `paper-info.xlsx`. The app filters out papers by negative keywords, presents the rest one at a time as swipeable cards, and exports liked papers as an `.ics` calendar.

## Architecture

Zero-dependency stack, launched with one command:

- `prepare_data.py` — one-time script; parses `paper-info.xlsx` with Python stdlib (zipfile + ElementTree, no openpyxl), keeps only rows with `Presentation mode == In-Person`, writes `papers.json`.
- `server.py` — Python stdlib `http.server`; serves static files, `GET /api/state`, `POST /api/state` (persists to `state.json`), and `GET /api/export.ics`.
- `index.html` — single page, vanilla JS/CSS. No build step, no frameworks.

## Data

`papers.json`: array of `{id (paper number), title, abstract, authors, room, session, sessionName, date, time}`.

`state.json`: `{keywords: [string], decisions: {paperId: "like" | "skip" | "filtered"}}`. Every swipe POSTs the full state; progress survives restarts and browser switches.

## Features

### Negative keywords
- Sidebar panel, always accessible; add/remove keywords at any time.
- Match: case-insensitive, whole-word, **against titles only**.
- Adding a keyword marks all matching *undecided* papers as `filtered` (auto-skipped).
- Removing a keyword returns its `filtered` papers (those not matching any remaining keyword) to the deck.
- Papers already liked/skipped by hand are never touched by keyword changes.

### Swipe deck
- Card shows **title** plus a small chip with session date/time.
- One toggle reveals **details** (abstract + authors together) on the current card.
- Keys: `←` skip · `→` like · `Space` toggle details · `Z` undo last swipe.
- On-screen buttons mirror the keys. Light CSS slide-off animation on swipe.
- Progress counter, e.g. `231 / 3,842` (denominator = papers not keyword-filtered).

### Schedule & export
- Schedule view: liked papers grouped by date → session time → session name, with room and paper number per paper. A paper can be un-liked from here.
- **Download .ics**: one `VEVENT` per session (not per paper); liked papers in that session listed in the event description with rooms/paper numbers. Timezone `America/Los_Angeles` (times in the sheet are PDT).

## Error handling

- Malformed/missing rows in the xlsx (no title or no session time) are skipped by `prepare_data.py` with a count reported.
- Sheet time strings are inconsistent (e.g. `14:00-15:30`, ` 12:45 - 14:15`); parser normalizes whitespace and both `H:MM` forms. Sessions with unparseable times still appear in the schedule view but are flagged and excluded from the `.ics` with a visible warning.
- If `state.json` is missing or corrupt, the server starts with empty state (and backs up the corrupt file rather than overwriting it).

## Testing

Manual verification: run `prepare_data.py` and sanity-check paper counts against the sheet; run the app; swipe with keyboard including undo and mid-session keyword add/remove; download the `.ics` and open it in a calendar app to confirm times, timezone, and grouping.

## Out of scope

Positive-keyword search, virtual papers, multi-user support, authentication, mobile/touch swipe gestures.
