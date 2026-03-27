# Monorepo Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combine `live-music-calendar-update` and `triangle-live-music-site` into a single well-organized repo at `/Users/isaacknowles/Code/nctrianglemusic/`.

**Architecture:** Python pipeline in `pipeline/` (core library + per-venue scraper dirs), Cloudflare Worker site in `site/`, single `.claude/` at root. R2 bucket remains the integration point. One CLI entry point: `python3 pipeline/cli.py`. Old repos archived to `/Users/isaacknowles/Code/`.

**Tech Stack:** Python 3, Cloudflare Workers, R2, Wrangler CLI, Claude skills

---

## File Map

**Created:**
- `pipeline/cli.py` — entry point (adds `pipeline/` to sys.path, calls `live_music.cli.main()`)
- `pipeline/live_music/__init__.py` — copied as-is
- `pipeline/live_music/cli.py` — copied + `scrape` command added + docstring updated
- `pipeline/live_music/state.py` — copied as-is (already uses `Path(__file__).parent.parent`)
- `pipeline/live_music/artists.py` — copied as-is
- `pipeline/live_music/utils.py` — copied as-is
- `pipeline/live_music/scrapers/__init__.py` — copied as-is
- `pipeline/live_music/scrapers/generic.py` — copied + `run()` extracted (same pattern as venue scrapers)
- `pipeline/venues/generic/scraper.py` — thin re-export of `live_music.scrapers.generic.run`
- `pipeline/venues/kings/scraper.py` — from `live_music/scrapers/kings.py`, import updated + `run()` extracted
- `pipeline/venues/kings/notes.md` — JS snippet + venue quirks (from SKILL.md)
- `pipeline/venues/cats_cradle/scraper.py` — from `live_music/scrapers/cats_cradle.py`, import updated + `run()` extracted
- `pipeline/venues/cats_cradle/notes.md`
- `pipeline/venues/chapel_of_bones/scraper.py` — from `live_music/scrapers/chapel_of_bones.py`, import updated + `run()` extracted
- `pipeline/venues/chapel_of_bones/notes.md`
- `pipeline/enrich_genres.py` — copied as-is (already uses `Path(__file__).parent`)
- `site/worker.js` — copied as-is
- `site/index.html` — copied as-is
- `site/wrangler.toml` — copied as-is
- `.claude/settings.local.json` — merged from both repos
- `.claude/skills/update-live-music/SKILL.md` — updated paths + notes.md references
- `.claude/skills/update-live-music/reference.md` — updated CLI name
- `CLAUDE.md` — project overview for Claude
- `README.md`
- `.gitignore`

**Not migrated (eliminated):**
- `live_music_cli.py` — replaced by `pipeline/cli.py`
- `scraper_kings.py`, `scraper_cats_cradle.py`, `scraper_chapel_of_bones.py`, `scraper_generic.py` — replaced by `python3 pipeline/cli.py scrape <venue>`
- `live_music/scrapers/kings.py`, `cats_cradle.py`, `chapel_of_bones.py` — moved to `venues/`

---

## Task 1: Initialize repo and scaffold

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: git init**

```bash
cd /Users/isaacknowles/Code/nctrianglemusic
git init
```

Expected: `Initialized empty Git repository in /Users/isaacknowles/Code/nctrianglemusic/.git/`

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p pipeline/live_music/scrapers \
         pipeline/venues/kings \
         pipeline/venues/cats_cradle \
         pipeline/venues/chapel_of_bones \
         pipeline/venues/generic \
         pipeline/.tmp \
         site \
         .claude/skills/update-live-music \
         docs/superpowers/specs \
         docs/superpowers/plans
```

- [ ] **Step 3: Write .gitignore**

Create `/Users/isaacknowles/Code/nctrianglemusic/.gitignore`:

```
# Python
__pycache__/
*.pyc
*.pyo

# Data files (R2 is source of truth)
pipeline/live_music_events.json
pipeline/live_music_events.json.bak
pipeline/artists_db.json
pipeline/venues_db.json

# Scraper scratch space
pipeline/.tmp/

# Credentials
pipeline/.env

# Wrangler cache
.wrangler/

# macOS
.DS_Store

# Claude Code local settings (machine-specific permissions)
.claude/settings.local.json
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: init repo with directory structure and .gitignore"
```

---

## Task 2: Copy core Python library

**Files:**
- Create: `pipeline/live_music/__init__.py`
- Create: `pipeline/live_music/state.py`
- Create: `pipeline/live_music/artists.py`
- Create: `pipeline/live_music/utils.py`
- Create: `pipeline/live_music/scrapers/__init__.py`
- Create: `pipeline/live_music/scrapers/generic.py`

- [ ] **Step 1: Copy files**

```bash
SRC=/Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update
DST=/Users/isaacknowles/Code/nctrianglemusic/pipeline

cp "$SRC/live_music/__init__.py"           "$DST/live_music/__init__.py"
cp "$SRC/live_music/state.py"              "$DST/live_music/state.py"
cp "$SRC/live_music/artists.py"            "$DST/live_music/artists.py"
cp "$SRC/live_music/utils.py"              "$DST/live_music/utils.py"
cp "$SRC/live_music/scrapers/__init__.py"  "$DST/live_music/scrapers/__init__.py"
cp "$SRC/live_music/scrapers/generic.py"   "$DST/live_music/scrapers/generic.py"
```

- [ ] **Step 2: Write pipeline/cli.py entry point**

Create `/Users/isaacknowles/Code/nctrianglemusic/pipeline/cli.py`:

```python
#!/usr/bin/env python3
"""Entry point for the live music pipeline CLI.

Run from the repo root:
    python3 pipeline/cli.py <command> [args...]

All commands are documented in live_music/cli.py. Run with --help to see them.
"""
import sys
from pathlib import Path

# Add pipeline/ to sys.path so live_music package and venue scrapers are importable
sys.path.insert(0, str(Path(__file__).parent))

from live_music.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify imports work**

```bash
cd /Users/isaacknowles/Code/nctrianglemusic
python3 -c "import sys; sys.path.insert(0, 'pipeline'); from live_music import cli; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pipeline/
git commit -m "feat: add core live_music library and pipeline/cli.py entry point"
```

---

## Task 3: Migrate venue scrapers

**Files:**
- Create: `pipeline/venues/kings/scraper.py`
- Create: `pipeline/venues/cats_cradle/scraper.py`
- Create: `pipeline/venues/chapel_of_bones/scraper.py`

Each scraper needs two changes from its source:
1. Change `from ..artists import detect_live_music, parse_artists` → `from live_music.artists import detect_live_music, parse_artists`
2. Extract a `run()` function from `main()` so the CLI can call it directly

- [ ] **Step 1: Create pipeline/venues/kings/scraper.py**

Copy `/Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/live_music/scrapers/kings.py` to `pipeline/venues/kings/scraper.py`, then make these two edits:

**Edit 1** — change the import (line 53):
```python
# OLD:
from ..artists import detect_live_music, parse_artists

# NEW:
from live_music.artists import detect_live_music, parse_artists
```

**Edit 2** — replace the `main()` function (lines 227–334) with a `run()` + `main()` split:

```python
def run(raw_path=DEFAULT_RAW, out_path=DEFAULT_OUT, days=DEFAULT_DAYS):
    """Normalize raw Kings event JSON into the standard schema.

    raw_path: path to .tmp/kings_raw.json (JS-extracted DOM events)
    out_path: path to write normalized output
    days:     lookahead window in days
    """
    raw_path = Path(raw_path)
    if not raw_path.exists():
        print(f"ERROR: Raw input file not found: {raw_path}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    with open(raw_path) as f:
        raw_events = json.load(f)

    if not raw_events:
        print("WARNING: 0 events in raw input — JS selectors may need tuning.", file=sys.stderr)

    today = datetime.today().date()
    cutoff = today + timedelta(days=days)
    year = today.year

    events_out = []
    skipped = 0

    for raw in raw_events:
        raw_title = raw.get("title", "").strip()
        date_raw = raw.get("date", "").strip()
        time_raw = raw.get("time", "").strip()
        price_raw = raw.get("price", "").strip()
        url_raw = raw.get("url", "").strip()

        if not raw_title or not url_raw:
            print(f"  SKIP (missing title or url): {raw}", file=sys.stderr)
            skipped += 1
            continue

        date_dt = parse_date_string(date_raw, year)
        if date_dt is None:
            print(f"  SKIP (cannot parse date {date_raw!r}): {raw_title}", file=sys.stderr)
            skipped += 1
            continue

        if date_dt.date() < today - timedelta(days=30):
            date_dt = date_dt.replace(year=year + 1)

        if date_dt.date() < today or date_dt.date() > cutoff:
            skipped += 1
            continue

        hm = parse_time_string(time_raw) if time_raw else None
        show_hour, show_min = hm if hm else (20, 0)

        start_dt = date_dt.replace(hour=show_hour, minute=show_min)
        doors_dt = start_dt - timedelta(hours=1)
        end_dt = start_dt + timedelta(hours=2)

        day_name = start_dt.strftime("%A")
        month_name = FULL_MONTH_NAMES[start_dt.month]
        date_str = f"{day_name}, {month_name} {start_dt.day}, {start_dt.year}"

        ev_id = make_event_id(raw_title, start_dt)
        title, subtitle, presenter = split_title_subtitle(raw_title)
        event_url = make_url(url_raw)

        slug_match = re.search(r"/shows/([^/?#]+)", event_url)
        if slug_match:
            ev_id = slug_match.group(1)

        event = {
            "id": ev_id,
            "title": title,
            "subtitle": subtitle,
            "presenter": presenter,
            "is_live_music": detect_live_music(title, subtitle, presenter),
            "artists": parse_artists(title, subtitle),
            "date_str": date_str,
            "time": fmt_time(show_hour, show_min),
            "doors": fmt_time(doors_dt.hour, doors_dt.minute),
            "admission": price_raw or "",
            "music_links": {},
            "event_url": event_url,
            "start_datetime": fmt_dt(start_dt),
            "doors_datetime": fmt_dt(doors_dt),
            "end_datetime": fmt_dt(end_dt),
            "content_hash": None,
        }
        events_out.append(event)

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(events_out, f, indent=2, ensure_ascii=False)

    if len(events_out) == 0:
        print("WARNING: 0 events written — JS selectors likely need tuning for current page structure.",
              file=sys.stderr)

    print(f"✅ Kings scraper: {len(events_out)} events written to {out_path}")
    if skipped:
        print(f"   (skipped {skipped} events outside lookahead window or missing/unparseable data)")

    for e in events_out:
        print(f"  {e['id']:45s} | {e['title'][:35]:35s} | {e['date_str'][:20]:20s} | {e['admission']}")


def main():
    raw_file, out_file, lookahead_days = parse_args()
    run(raw_file, out_file, lookahead_days)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create pipeline/venues/chapel_of_bones/scraper.py**

Copy `live_music/scrapers/chapel_of_bones.py` to `pipeline/venues/chapel_of_bones/scraper.py`, then:

**Edit 1** — change the import (line 46):
```python
# OLD:
from ..artists import detect_live_music, parse_artists

# NEW:
from live_music.artists import detect_live_music, parse_artists
```

**Edit 2** — replace `main()` with `run()` + `main()`:

```python
def run(raw_path=DEFAULT_RAW, out_path=DEFAULT_OUT, days=DEFAULT_DAYS):
    """Normalize raw Chapel of Bones event JSON into the standard schema.

    raw_path: path to .tmp/chapel_of_bones_raw.json (TickPick widget extraction)
    out_path: path to write normalized output
    days:     lookahead window in days
    """
    raw_path = Path(raw_path)
    if not raw_path.exists():
        print(f"ERROR: Raw input file not found: {raw_path}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    with open(raw_path) as f:
        raw_events = json.load(f)

    cutoff = datetime.today().date() + timedelta(days=days)
    today = datetime.today().date()

    events_out = []
    skipped = 0

    for raw in raw_events:
        raw_title = raw.get("title", "").strip()
        date_location = raw.get("dateLocation", "").strip()
        price_raw = raw.get("price", "").strip()

        if not raw_title or not date_location:
            print(f"  SKIP (missing data): {raw}", file=sys.stderr)
            skipped += 1
            continue

        try:
            times = parse_tickpick_date(date_location)
        except ValueError as e:
            print(f"  SKIP (parse error): {e}", file=sys.stderr)
            skipped += 1
            continue

        start_date = datetime.fromisoformat(times["start_datetime"]).date()
        if start_date < today or start_date > cutoff:
            skipped += 1
            continue

        ev_id = make_event_id(raw_title, date_location)
        title, subtitle, presenter = split_title_subtitle(raw_title)
        admission = normalize_price(price_raw)

        event = {
            "id": ev_id,
            "title": title,
            "subtitle": subtitle,
            "presenter": presenter,
            "is_live_music": detect_live_music(title, subtitle, presenter),
            "artists": parse_artists(title, subtitle),
            "date_str": times["date_str"],
            "time": times["time"],
            "doors": times["doors"],
            "admission": admission,
            "music_links": {},
            "event_url": EVENT_URL,
            "start_datetime": times["start_datetime"],
            "doors_datetime": times["doors_datetime"],
            "end_datetime": times["end_datetime"],
            "content_hash": None,
        }
        events_out.append(event)

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(events_out, f, indent=2, ensure_ascii=False)

    print(f"✅ Chapel of Bones scraper: {len(events_out)} events written to {out_path}")
    if skipped:
        print(f"   (skipped {skipped} events outside lookahead window or missing data)")

    for e in events_out:
        print(f"  {e['id']:45s} | {e['title'][:35]:35s} | {e['date_str'][:20]:20s} | {e['admission']}")


def main():
    raw_file, out_file, lookahead_days = parse_args()
    run(raw_file, out_file, lookahead_days)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create pipeline/venues/cats_cradle/scraper.py**

Copy `live_music/scrapers/cats_cradle.py` to `pipeline/venues/cats_cradle/scraper.py`, then:

**Edit 1** — change the import (line 77):
```python
# OLD:
from ..artists import detect_live_music, parse_artists

# NEW:
from live_music.artists import detect_live_music, parse_artists
```

**Edit 2** — replace `main()` with `run()` + `main()`:

```python
def run(raw_path=DEFAULT_RAW, days=DEFAULT_DAYS, fetch=True):
    """Normalize raw Cat's Cradle event JSON into the standard schema.

    Outputs two files (always):
      .tmp/scraped_cats-cradle.json           (Main Stage)
      .tmp/scraped_cats-cradle-back-room.json (Back Room)

    raw_path: path to .tmp/cats_cradle_raw.json
    days:     lookahead window in days
    fetch:    if True, fetches each event page for admission price (slower)
    """
    raw_path = Path(raw_path)
    if not raw_path.exists():
        print(f"ERROR: Raw input file not found: {raw_path}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    with open(raw_path) as f:
        raw_events = json.load(f)

    if not raw_events:
        print("WARNING: 0 events in raw input — JS selectors may need tuning.", file=sys.stderr)

    today = datetime.today().date()
    cutoff = today + timedelta(days=days)
    year = today.year

    main_events: list[dict] = []
    back_events: list[dict] = []
    skipped = 0

    for raw in raw_events:
        raw_title = raw.get("title", "").strip()
        date_raw  = raw.get("date", "").strip()
        time_raw  = raw.get("time", "").strip()
        room_raw  = raw.get("room", "").strip()
        url_raw   = raw.get("url", "").strip()

        if not raw_title or not url_raw:
            print(f"  SKIP (missing title or url): {raw}", file=sys.stderr)
            skipped += 1
            continue

        if url_raw.startswith("/"):
            url_raw = VENUE_BASE_URL + url_raw

        date_dt = parse_date_string(date_raw, year)
        if date_dt is None:
            print(f"  SKIP (cannot parse date {date_raw!r}): {raw_title}", file=sys.stderr)
            skipped += 1
            continue

        if date_dt.date() < today - timedelta(days=30):
            date_dt = date_dt.replace(year=year + 1)

        if date_dt.date() < today or date_dt.date() > cutoff:
            skipped += 1
            continue

        hm = parse_time_string(time_raw) if time_raw else None
        show_hour, show_min = hm if hm else (20, 0)

        start_dt  = date_dt.replace(hour=show_hour, minute=show_min)
        doors_dt  = start_dt - timedelta(hours=1)
        end_dt    = start_dt + timedelta(hours=2)

        day_name   = start_dt.strftime("%A")
        month_name = FULL_MONTH_NAMES[start_dt.month]
        date_str   = f"{day_name}, {month_name} {start_dt.day}, {start_dt.year}"

        slug_m = re.search(r"/event/([^/?#]+)", url_raw)
        ev_id  = slug_m.group(1).rstrip("/") if slug_m else slugify(raw_title)

        title, subtitle, presenter = split_title_subtitle(raw_title)
        room = detect_room(room_raw, raw_title)

        if fetch:
            admission = fetch_admission(url_raw)
            time.sleep(0.3)
        else:
            admission = ""

        event = {
            "id":             ev_id,
            "title":          title,
            "subtitle":       subtitle,
            "presenter":      presenter,
            "is_live_music":  detect_live_music(title, subtitle, presenter),
            "artists":        parse_artists(title, subtitle),
            "room":           room,
            "date_str":       date_str,
            "time":           fmt_time(show_hour, show_min),
            "doors":          fmt_time(doors_dt.hour, doors_dt.minute),
            "admission":      admission,
            "music_links":    {},
            "event_url":      url_raw,
            "start_datetime": fmt_dt(start_dt),
            "doors_datetime": fmt_dt(doors_dt),
            "end_datetime":   fmt_dt(end_dt),
            "content_hash":   None,
        }

        if room == "Back Room":
            back_events.append(event)
        else:
            main_events.append(event)

    os.makedirs(".tmp", exist_ok=True)

    with open(DEFAULT_OUT_MAIN, "w") as f:
        json.dump(main_events, f, indent=2, ensure_ascii=False)

    with open(DEFAULT_OUT_BACK, "w") as f:
        json.dump(back_events, f, indent=2, ensure_ascii=False)

    print(f"Cat's Cradle scraper complete:")
    print(f"   Main Stage:  {len(main_events)} events -> {DEFAULT_OUT_MAIN}")
    print(f"   Back Room:   {len(back_events)} events -> {DEFAULT_OUT_BACK}")
    if skipped:
        print(f"   (skipped {skipped} events outside lookahead window or unparseable)")

    for label, events in [("MAIN", main_events), ("BACK", back_events)]:
        for e in events:
            print(f"  [{label}] {e['id']:45s} | {e['title'][:30]:30s} | {e['date_str'][:20]:20s} | {e['admission'] or '(fetching)':20s}")


def main():
    raw_file, days, do_fetch = parse_args()
    run(raw_file, days, do_fetch)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add run() to generic.py and create venues/generic/**

`pipeline/live_music/scrapers/generic.py` — add a `run()` function and make `main()` call it. Also change the import from `from ..artists import` to `from live_music.artists import`:

**Edit 1** — change the import (line 63):
```python
# OLD:
from ..artists import detect_live_music, parse_artists

# NEW:
from live_music.artists import detect_live_music, parse_artists
```

**Edit 2** — replace `main()` with `run()` + `main()`:

```python
def run(raw_path=DEFAULT_RAW, out_path=DEFAULT_OUT, days=DEFAULT_DAYS):
    """Normalize a raw JSON file for any plain-HTML venue into the standard schema.

    raw_path: path to .tmp/<venue>_raw.json
    out_path: path to write normalized output
    days:     lookahead window in days

    Raw input format: list of objects with fields:
      slug, title, subtitle (opt), presenter (opt), date (YYYY-MM-DD),
      show_time (HH:MM 24h), end_time (HH:MM, opt), admission (opt), url
    """
    raw_path = Path(raw_path)
    if not raw_path.exists():
        print(f"ERROR: Raw input file not found: {raw_path}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    with open(raw_path) as f:
        raw_events = json.load(f)

    today = datetime.today().date()
    cutoff = today + timedelta(days=days)

    events_out = []
    skipped = 0

    for raw in raw_events:
        slug = raw.get("slug", "").strip()
        title = raw.get("title", "").strip()
        subtitle = raw.get("subtitle", "").strip()
        presenter = raw.get("presenter", "").strip()
        date_s = raw.get("date", "").strip()
        show_time_s = raw.get("show_time", "").strip()
        end_time_s = raw.get("end_time", "").strip()
        admission = raw.get("admission", "").strip()
        url = raw.get("url", "").strip()

        if not slug or not title or not date_s or not show_time_s:
            print(f"  SKIP (missing required field): {raw}", file=sys.stderr)
            skipped += 1
            continue

        try:
            date_obj = datetime.strptime(date_s, "%Y-%m-%d").date()
        except ValueError:
            print(f"  SKIP (bad date {date_s!r}): {title}", file=sys.stderr)
            skipped += 1
            continue

        if date_obj < today or date_obj > cutoff:
            skipped += 1
            continue

        try:
            sh, sm = parse_hhmm(show_time_s)
        except ValueError as e:
            print(f"  SKIP (bad show_time): {e}", file=sys.stderr)
            skipped += 1
            continue

        start_dt = datetime(date_obj.year, date_obj.month, date_obj.day, sh, sm)
        doors_dt = start_dt - timedelta(hours=1)

        if end_time_s:
            try:
                eh, em = parse_hhmm(end_time_s)
                end_dt = datetime(date_obj.year, date_obj.month, date_obj.day, eh, em)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
            except ValueError:
                end_dt = start_dt + timedelta(hours=2)
        else:
            end_dt = start_dt + timedelta(hours=2)

        day_name = start_dt.strftime("%A")
        month_name = FULL_MONTH_NAMES[start_dt.month]
        date_str = f"{day_name}, {month_name} {start_dt.day}, {start_dt.year}"

        event = {
            "id": slug,
            "title": title,
            "subtitle": subtitle,
            "presenter": presenter,
            "is_live_music": detect_live_music(title, subtitle, presenter),
            "artists": parse_artists(title, subtitle),
            "date_str": date_str,
            "time": fmt_time(sh, sm),
            "doors": fmt_time(doors_dt.hour, doors_dt.minute),
            "admission": admission,
            "music_links": {},
            "event_url": url,
            "start_datetime": fmt_dt(start_dt),
            "doors_datetime": fmt_dt(doors_dt),
            "end_datetime": fmt_dt(end_dt),
            "content_hash": None,
        }
        events_out.append(event)

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(events_out, f, indent=2, ensure_ascii=False)

    print(f"✅ Generic scraper: {len(events_out)} events written to {out_path}")
    if skipped:
        print(f"   (skipped {skipped} events outside lookahead window or missing data)")

    for e in events_out:
        print(f"  {e['id']:45s} | {e['title'][:35]:35s} | {e['date_str'][:20]:20s} | {e['admission'] or '—'}")


def main():
    raw_file, out_file, lookahead_days = parse_args()
    run(raw_file, out_file, lookahead_days)


if __name__ == "__main__":
    main()
```

Then create `pipeline/venues/generic/scraper.py`:

```bash
mkdir -p /Users/isaacknowles/Code/nctrianglemusic/pipeline/venues/generic
```

```python
"""Generic scraper for plain-HTML venues.

Delegates to live_music/scrapers/generic.py. Used via:
    python3 pipeline/cli.py scrape generic --raw .tmp/<venue>_raw.json --out .tmp/scraped_<venue>.json

See live_music/scrapers/generic.py for the raw input format spec (slug, title, date, show_time, etc.).
"""
from live_music.scrapers.generic import run, main  # noqa: F401
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/venues/
git commit -m "feat: add per-venue scraper dirs (kings, cats_cradle, chapel_of_bones, generic)"
```

---

## Task 4: Add `scrape` command to live_music/cli.py

**Files:**
- Modify: `pipeline/live_music/cli.py`

- [ ] **Step 1: Add cmd_scrape function**

In `pipeline/live_music/cli.py`, add the following function immediately before the `# ── Dispatch ──` section (before the `COMMANDS = {` line):

```python
def cmd_scrape(args):
    """Normalize raw scraped data for a venue using its venues/ scraper.

    Usage: scrape <venue-key> [--raw <file>] [--out <file>] [--days <N>] [--no-fetch]

    The raw JSON file must already exist — place it there using the JS extraction
    step documented in pipeline/venues/<venue>/notes.md.

    For venues with no custom scraper (plain-HTML venues), use:
        scrape generic --raw .tmp/<venue>_raw.json --out .tmp/scraped_<venue>.json

    Outputs:
      kings, chapel-of-bones: writes --out (default: .tmp/scraped_<venue>.json)
      cats-cradle:            always writes two files:
                                .tmp/scraped_cats-cradle.json
                                .tmp/scraped_cats-cradle-back-room.json
    """
    import importlib.util

    if not args:
        print("Usage: scrape <venue-key> [--raw <file>] [--out <file>] [--days <N>] [--no-fetch]")
        sys.exit(1)

    venue_key = args[0]
    rest = args[1:]

    # Parse optional flags
    raw_path = None
    out_path = None
    days = 90
    no_fetch = False
    i = 0
    while i < len(rest):
        if rest[i] == "--raw" and i + 1 < len(rest):
            raw_path = rest[i + 1]; i += 2
        elif rest[i] == "--out" and i + 1 < len(rest):
            out_path = rest[i + 1]; i += 2
        elif rest[i] == "--days" and i + 1 < len(rest):
            days = int(rest[i + 1]); i += 2
        elif rest[i] == "--no-fetch":
            no_fetch = True; i += 1
        else:
            i += 1

    # Resolve the scraper module
    venues_dir = Path(__file__).parent.parent / "venues"
    scraper_path = venues_dir / venue_key / "scraper.py"
    if not scraper_path.exists():
        # Fallback: try with underscores (e.g. "cats_cradle" → cats_cradle dir)
        scraper_path = venues_dir / venue_key.replace("-", "_") / "scraper.py"
    if not scraper_path.exists():
        print(f"ERROR: No scraper found for venue '{venue_key}'", file=sys.stderr)
        print(f"       Expected: {venues_dir / venue_key / 'scraper.py'}", file=sys.stderr)
        print(f"       To add one, create that file with a run() function.", file=sys.stderr)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("venue_scraper", scraper_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Build kwargs — only pass what was explicitly set so run() defaults apply
    kwargs = {"days": days}
    if raw_path is not None:
        kwargs["raw_path"] = raw_path
    if out_path is not None:
        kwargs["out_path"] = out_path
    if no_fetch:
        kwargs["fetch"] = False

    mod.run(**kwargs)
```

- [ ] **Step 2: Add scrape to COMMANDS dict**

In `pipeline/live_music/cli.py`, find the `COMMANDS = {` dict and add one entry:

```python
    "scrape":          cmd_scrape,
```

(Add it alongside the other commands, alphabetically near "status"/"stale".)

- [ ] **Step 3: Update docstring**

At the top of `pipeline/live_music/cli.py`, find the docstring that lists commands. Add this line to the Commands section:

```
  scrape <venue-key> [--raw <f>] [--out <f>] [--days N] [--no-fetch]
                                Normalize raw scraped JSON for a venue
```

And update the first line reference from `live_music_cli.py` to `pipeline/cli.py`:

```python
# OLD:
"""
live_music_cli.py — Management toolkit ...
Usage:
  python3 live_music_cli.py <command> [options]

# NEW:
"""
live_music CLI — Management toolkit ...
Usage:
  python3 pipeline/cli.py <command> [options]
```

- [ ] **Step 4: Smoke test — copy data files and run stale/scrape help**

```bash
cp /Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/live_music_events.json \
   /Users/isaacknowles/Code/nctrianglemusic/pipeline/live_music_events.json
cp /Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/artists_db.json \
   /Users/isaacknowles/Code/nctrianglemusic/pipeline/artists_db.json
cp /Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/venues_db.json \
   /Users/isaacknowles/Code/nctrianglemusic/pipeline/venues_db.json

cd /Users/isaacknowles/Code/nctrianglemusic
python3 pipeline/cli.py stale
```

Expected: prints the stalest venue name, key, and events_url.

```bash
python3 pipeline/cli.py scrape --help 2>&1 || python3 pipeline/cli.py scrape
```

Expected: prints usage line (not a traceback).

- [ ] **Step 5: Commit**

```bash
git add pipeline/live_music/cli.py
git commit -m "feat: add scrape <venue> command dispatching to venues/<v>/scraper.py"
```

---

## Task 5: Copy enrich_genres.py and site files

**Files:**
- Create: `pipeline/enrich_genres.py`
- Create: `site/worker.js`
- Create: `site/index.html`
- Create: `site/wrangler.toml`

- [ ] **Step 1: Copy enrich_genres.py**

```bash
cp /Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/enrich_genres.py \
   /Users/isaacknowles/Code/nctrianglemusic/pipeline/enrich_genres.py
```

No changes needed — it uses `Path(__file__).parent / "artists_db.json"` which resolves correctly to `pipeline/artists_db.json`.

- [ ] **Step 2: Copy site files**

```bash
SRC=/Users/isaacknowles/Code/nctrianglemusic/triangle-live-music-site
DST=/Users/isaacknowles/Code/nctrianglemusic/site

cp "$SRC/worker.js"    "$DST/worker.js"
cp "$SRC/index.html"   "$DST/index.html"
cp "$SRC/wrangler.toml" "$DST/wrangler.toml"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/enrich_genres.py site/
git commit -m "feat: add enrich_genres.py and site (worker, index.html, wrangler.toml)"
```

---

## Task 6: Write venue notes.md files

**Files:**
- Create: `pipeline/venues/kings/notes.md`
- Create: `pipeline/venues/cats_cradle/notes.md`
- Create: `pipeline/venues/chapel_of_bones/notes.md`

These are extracted from the inline notes in SKILL.md and the scraper docstrings.

- [ ] **Step 1: Write pipeline/venues/kings/notes.md**

```markdown
# Kings — Scraping Notes

**URL:** https://www.kingsraleigh.com/
**Events URL:** https://www.kingsraleigh.com/ (homepage — `/shows` renders empty)
**Event ID Tag:** `kings-id`

## Site Quirks

JS-rendered. The `/shows` page is empty — all events are on the **homepage**.
Individual show pages are also JS-rendered; extract all event data from the homepage in one JS call.

## Extraction (Step 1)

Navigate to `https://www.kingsraleigh.com/` and run in the browser console (or via `javascript_tool`):

```javascript
JSON.stringify(Array.from(document.querySelectorAll('[class*="show"], [class*="event"], article'))
  .map(el => ({
    title: el.querySelector('[class*="title"], h2, h3')?.textContent.trim() || '',
    date:  el.querySelector('[class*="date"], time')?.textContent.trim() || '',
    time:  el.querySelector('[class*="time"]')?.textContent.trim() || '',
    price: el.querySelector('[class*="price"], [class*="ticket"]')?.textContent.trim() || '',
    url:   el.querySelector('a[href*="/shows/"]')?.href || ''
  })).filter(e => e.title && e.url))
```

Save output to `.tmp/kings_raw.json`.

> Selectors are best-effort — verify output before saving. Warn if 0 events returned.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape kings
# or with overrides:
python3 pipeline/cli.py scrape kings --raw .tmp/kings_raw.json --out .tmp/scraped_kings.json --days 90
```

## Diff / Set

```bash
python3 pipeline/cli.py diff kings-id .tmp/scraped_kings.json --report .tmp/kings_changes.md
```
```

- [ ] **Step 2: Write pipeline/venues/cats_cradle/notes.md**

```markdown
# Cat's Cradle — Scraping Notes

**URL:** https://catscradle.com/events/
**Event ID Tags:** `cats-cradle-id` (Main Stage), `cats-cradle-br-id` (Back Room)

## Site Quirks

Two rooms tracked separately. The events listing page does **not** show ticket prices —
prices are only on individual event pages. The scraper fetches each event's detail page
automatically (0.3s polite delay). Use `--no-fetch` to skip this (faster, empty admission).

The Events Calendar plugin changes class names periodically. If 0 events are returned,
inspect the DOM and adjust selectors.

## Extraction (Step 1)

Navigate to `https://catscradle.com/events/` and run in the browser console:

```javascript
JSON.stringify(
  Array.from(document.querySelectorAll('.tribe-events-calendar-list__event-article, article.type-tribe_events, .tribe-event'))
    .map(el => ({
      title:    el.querySelector('.tribe-event-url, .tribe-events-calendar-list__event-title a, h2 a, h3 a')?.textContent.trim() || '',
      url:      el.querySelector('.tribe-event-url, .tribe-events-calendar-list__event-title a, h2 a, h3 a')?.href || '',
      date:     el.querySelector('.tribe-event-date-start, time, .tribe-events-start-datetime')?.textContent.trim() || '',
      time:     el.querySelector('.tribe-events-start-time, .tribe-event-time')?.textContent.trim() || '',
      room:     el.querySelector('.tribe-venue-location, .tribe-venue, .tribe-events-calendar-list__event-venue')?.textContent.trim() || '',
    }))
    .filter(e => e.title && e.url)
)
```

**Fallback selector (if 0 events):**
```javascript
JSON.stringify(
  Array.from(document.querySelectorAll('h2 a[href*="/event/"], h3 a[href*="/event/"]'))
    .map(a => ({
      title: a.textContent.trim(),
      url:   a.href,
      date:  a.closest('article, li, div')?.querySelector('time, [class*="date"]')?.textContent.trim() || '',
      time:  a.closest('article, li, div')?.querySelector('[class*="time"]')?.textContent.trim() || '',
      room:  a.closest('article, li, div')?.querySelector('[class*="venue"], [class*="location"]')?.textContent.trim() || '',
    }))
    .filter(e => e.title)
)
```

Save output to `.tmp/cats_cradle_raw.json`.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape cats-cradle
# Skip per-page price fetching (faster):
python3 pipeline/cli.py scrape cats-cradle --no-fetch
```

Outputs two files:
- `.tmp/scraped_cats-cradle.json` (Main Stage)
- `.tmp/scraped_cats-cradle-back-room.json` (Back Room)

## Diff / Set

Run diff + set for **each room separately**:

```bash
python3 pipeline/cli.py diff cats-cradle-id .tmp/scraped_cats-cradle.json \
  --report .tmp/cats-cradle_changes.md

python3 pipeline/cli.py diff cats-cradle-br-id .tmp/scraped_cats-cradle-back-room.json \
  --report .tmp/cats-cradle-back-room_changes.md
```
```

- [ ] **Step 3: Write pipeline/venues/chapel_of_bones/notes.md**

```markdown
# Chapel of Bones — Scraping Notes

**URL:** https://chapelofbones.com/events/
**Event ID Tag:** `chapel-of-bones-id`

## Site Quirks

Uses an embedded **TickPick widget** — there are no individual event pages on the venue's
own site. All event data comes from the widget DOM. Prices include a TickPick service fee
(~14.3%); the scraper strips this automatically from fractional-cent prices.

## Extraction (Step 1)

Navigate to `https://chapelofbones.com/events/` and run in the browser console:

```javascript
const items = Array.from(document.querySelectorAll('.eventGridItem_b9cc1'));
const raw = items.map(item => ({
  title: item.querySelector('.eventTitle_eacac')?.textContent.trim() || '',
  dateLocation: item.querySelector('.eventLocation_0f1cb')?.textContent.trim() || '',
  price: item.querySelector('.eventPriceButton_b33bd')?.textContent.trim() || ''
}));
JSON.stringify(raw)
```

Save output to `.tmp/chapel_of_bones_raw.json`.

> TickPick class names may change. If 0 events, inspect the widget DOM and update selectors.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape chapel-of-bones
# or with overrides:
python3 pipeline/cli.py scrape chapel-of-bones --raw .tmp/chapel_of_bones_raw.json --out .tmp/scraped_chapel-of-bones.json
```

## Diff / Set

```bash
python3 pipeline/cli.py diff chapel-of-bones-id .tmp/scraped_chapel-of-bones.json \
  --report .tmp/chapel-of-bones_changes.md
```
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/venues/
git commit -m "docs: add per-venue notes.md with JS snippets and scraping guidance"
```

---

## Task 7: Migrate .claude/ config

**Files:**
- Create: `.claude/settings.local.json`
- Create: `.claude/skills/update-live-music/SKILL.md`
- Create: `.claude/skills/update-live-music/reference.md`

- [ ] **Step 1: Merge settings.local.json**

Read both existing settings files:
- `/Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/.claude/settings.local.json`
- `/Users/isaacknowles/Code/nctrianglemusic/triangle-live-music-site/.claude/settings.local.json`

Create `.claude/settings.local.json` by taking the pipeline repo's permissions as the base and merging any unique entries from the site repo. The result should be a valid JSON object with the merged `permissions` arrays (deduplicated).

> The exact merged content depends on what's in both files — read them and merge carefully. Do not duplicate entries.

- [ ] **Step 2: Write updated SKILL.md**

Create `.claude/skills/update-live-music/SKILL.md`. Copy the content from the original at `live-music-calendar-update/.claude/skills/update-live-music/SKILL.md` with these changes:

1. **Update working directory** (line 15):
```
# OLD:
Working directory: `/Users/isaacknowles/Documents/live-music-calendar-update/`

# NEW:
Working directory: `/Users/isaacknowles/Code/nctrianglemusic/`
```

2. **Replace all `python3 live_music_cli.py`** with `python3 pipeline/cli.py` throughout the file.

3. **Replace all `python3 scraper_kings.py`** with `python3 pipeline/cli.py scrape kings`.

4. **Replace all `python3 scraper_chapel_of_bones.py`** with `python3 pipeline/cli.py scrape chapel-of-bones`.

5. **Replace all `python3 scraper_cats_cradle.py`** (and the `--no-fetch` variant) with `python3 pipeline/cli.py scrape cats-cradle` (and `python3 pipeline/cli.py scrape cats-cradle --no-fetch`).

6. **Replace `python3 scraper_generic.py --raw ... --out ...`** with `python3 pipeline/cli.py scrape generic --raw ... --out ...`.

7. **Replace venue-specific notes in Step 2** with references to `notes.md`:

For the Kings note, replace:
```
- **Kings** (`https://www.kingsraleigh.com/`): JS-rendered; `/shows` is empty — use the **homepage**. Two-step extraction:
  1. Navigate to `https://www.kingsraleigh.com/` and run the JS snippet from `scraper_kings.py` docstring. Save result to `.tmp/kings_raw.json`.
  2. Run `python3 scraper_kings.py` (outputs `.tmp/scraped_kings.json`). See script docstring for flags and usage.
```
with:
```
- **Kings**: See `pipeline/venues/kings/notes.md` for JS extraction snippet and quirks.
```

For Chapel of Bones, replace the multi-line note with:
```
- **Chapel of Bones**: See `pipeline/venues/chapel_of_bones/notes.md` for TickPick widget extraction and quirks.
```

For Cat's Cradle, replace the multi-line note with:
```
- **Cat's Cradle**: Two rooms tracked separately. See `pipeline/venues/cats_cradle/notes.md` for JS extraction snippet, room detection, and price-fetching notes.
```

- [ ] **Step 3: Write updated reference.md**

Create `.claude/skills/update-live-music/reference.md`. Copy from the original and update the first line:

```markdown
# CLI Reference — `pipeline/cli.py`

`pipeline/cli.py` is the entry point for all pipeline operations. Run from the repo root:
`python3 pipeline/cli.py <command> [options]`
```

Update the table to add the `scrape` command:

```
| `scrape <venue-key> [--raw f] [--out f] [--days N] [--no-fetch]` | Normalize raw scraped JSON for a venue using `pipeline/venues/<venue>/scraper.py` |
```

- [ ] **Step 4: Commit**

```bash
git add .claude/
git commit -m "feat: add .claude/ config with merged permissions and updated skill"
```

---

## Task 8: Write CLAUDE.md and README.md

**Files:**
- Create: `CLAUDE.md`
- Create: `README.md`

- [ ] **Step 1: Write CLAUDE.md**

Create `/Users/isaacknowles/Code/nctrianglemusic/CLAUDE.md`:

```markdown
# nctrianglemusic — Project Guide for Claude

## What This Is

A live music event calendar for the Triangle area (Raleigh, Durham, Chapel Hill, Carrboro).
Tracks upcoming shows at ~14 venues. Data is scraped from venue websites, stored in JSON,
uploaded to Cloudflare R2, and served by a Cloudflare Worker that injects the data into a
single-file HTML frontend.

## Repository Layout

```
nctrianglemusic/
├── pipeline/                  Data pipeline (Python)
│   ├── live_music/            Core library: CLI commands, state I/O, artist parsing
│   ├── venues/                Per-venue scraper directories (one dir per custom venue)
│   │   ├── kings/
│   │   │   ├── scraper.py     Extraction + normalization logic
│   │   │   └── notes.md       JS snippets, site quirks, scraping tips
│   │   ├── cats_cradle/
│   │   └── chapel_of_bones/
│   ├── cli.py                 Entry point: python3 pipeline/cli.py <cmd>
│   └── enrich_genres.py       Spotify + Bandcamp genre backfill (run separately)
├── site/                      Cloudflare Worker site
│   ├── worker.js              Fetches R2 at request time, injects data into HTML
│   ├── index.html             Complete frontend (CSS + JS inline, no build step)
│   └── wrangler.toml          Cloudflare config (R2 binding, custom domain)
├── .claude/                   Claude Code config and skills
└── docs/superpowers/          Design specs and implementation plans
```

## Key Commands

```bash
# Identify the stalest venue (always scrape this one next)
python3 pipeline/cli.py stale

# Full venue status table
python3 pipeline/cli.py status

# Normalize raw JSON for a venue (after JS extraction step)
python3 pipeline/cli.py scrape kings
python3 pipeline/cli.py scrape cats-cradle         # outputs 2 files (main + back room)
python3 pipeline/cli.py scrape chapel-of-bones
python3 pipeline/cli.py scrape generic --raw .tmp/<venue>_raw.json --out .tmp/scraped_<venue>.json

# Diff scraped events against stored state
python3 pipeline/cli.py diff kings-id .tmp/scraped_kings.json --report .tmp/kings_changes.md

# Save new/changed events
python3 pipeline/cli.py set kings-id:<event-id> .tmp/events/<id>.json

# Maintenance
python3 pipeline/cli.py repair
python3 pipeline/cli.py prune --days 30

# Upload all 3 JSON files to R2
python3 pipeline/cli.py upload

# Genre enrichment (run periodically, not per-venue)
python3 pipeline/enrich_genres.py

# Site development
cd site && wrangler dev --remote

# Site deployment (auto via Cloudflare on push to main)
cd site && wrangler deploy
```

## Cloudflare

- **R2 bucket:** `triangle-live-music-data`
- **Worker name:** `triangle-live-music`
- **Production URL:** https://nctrianglemusic.live
- **Files in R2:** `live_music_events.json`, `artists_db.json`, `venues_db.json`

## Data Flow

```
Venue website → JS extraction (browser) → .tmp/<venue>_raw.json
→ python3 pipeline/cli.py scrape <venue> → .tmp/scraped_<venue>.json
→ diff / set → pipeline/live_music_events.json
→ python3 pipeline/cli.py upload → R2
→ site/worker.js fetches R2 at request time → injects into index.html
→ nctrianglemusic.live
```

## Adding a New Venue

1. Add venue to state: `python3 pipeline/cli.py add-venue --key <key> --name <name> --address <address> --url <url> --tag <tag>`
2. If the venue is plain HTML: use `scrape generic` — no new directory needed.
3. If the venue needs custom scraping: create `pipeline/venues/<venue-key>/scraper.py` with a `run(raw_path, out_path, days)` function, and `notes.md` with the JS extraction snippet and any quirks.
4. Update the venue-specific notes in `.claude/skills/update-live-music/SKILL.md`.

## Data Files (gitignored, local only)

- `pipeline/live_music_events.json` — master event state (~600KB)
- `pipeline/artists_db.json` — artist enrichment (~800 artists)
- `pipeline/venues_db.json` — public venue metadata
- `pipeline/.env` — Spotify credentials for enrich_genres.py
- `pipeline/.tmp/` — scraper scratch space (ephemeral)

R2 is the source of truth. These files are working copies only.
```

- [ ] **Step 2: Write README.md**

Create `/Users/isaacknowles/Code/nctrianglemusic/README.md`:

```markdown
# nctrianglemusic

Live music event calendar for the Triangle area (Raleigh, Durham, Chapel Hill, Carrboro).

**Site:** https://nctrianglemusic.live

Tracks upcoming shows at ~14 venues. See `CLAUDE.md` for architecture, commands, and
how to add a new venue.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add CLAUDE.md project guide and README"
```

---

## Task 9: Consolidate docs/

**Files:**
- Copy existing specs and plans from both repos

- [ ] **Step 1: Copy docs from pipeline repo**

```bash
SRC=/Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update/docs/superpowers

# Plans
cp "$SRC/plans/"*.md /Users/isaacknowles/Code/nctrianglemusic/docs/superpowers/plans/ 2>/dev/null || true
```

- [ ] **Step 2: Copy docs from site repo**

```bash
SRC=/Users/isaacknowles/Code/nctrianglemusic/triangle-live-music-site/docs/superpowers

cp "$SRC/specs/"*.md /Users/isaacknowles/Code/nctrianglemusic/docs/superpowers/specs/ 2>/dev/null || true
cp "$SRC/plans/"*.md /Users/isaacknowles/Code/nctrianglemusic/docs/superpowers/plans/ 2>/dev/null || true
```

(The monorepo consolidation spec and plan written during this session are already in `docs/superpowers/`.)

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: consolidate specs and plans from both repos"
```

---

## Task 10: Full smoke test

- [ ] **Step 1: Verify core CLI commands**

Data files should already be in `pipeline/` from Task 4 smoke test. Run:

```bash
cd /Users/isaacknowles/Code/nctrianglemusic
python3 pipeline/cli.py status
```

Expected: table of all 14 venues with last_updated and event counts. No errors.

```bash
python3 pipeline/cli.py stats
```

Expected: summary statistics (total events, future, coverage dates).

```bash
python3 pipeline/cli.py stale
```

Expected: single venue name + key + events_url.

- [ ] **Step 2: Verify scrape command dispatch**

```bash
python3 pipeline/cli.py scrape kings 2>&1 | head -5
```

Expected: `ERROR: Raw input file not found: .tmp/kings_raw.json` — correct, no raw file exists yet. This confirms the dispatch path works.

- [ ] **Step 3: Verify site wrangler config**

```bash
cd /Users/isaacknowles/Code/nctrianglemusic/site
wrangler whoami
```

Expected: shows authenticated Cloudflare account. No errors.

- [ ] **Step 4: Fix any issues found, then commit**

```bash
git add -A
git commit -m "fix: smoke test corrections" # only if changes were needed
```

---

## Task 11: Archive old repos

- [ ] **Step 1: Move old repos out**

```bash
mv /Users/isaacknowles/Code/nctrianglemusic/live-music-calendar-update \
   /Users/isaacknowles/Code/live-music-calendar-update-archived

mv /Users/isaacknowles/Code/nctrianglemusic/triangle-live-music-site \
   /Users/isaacknowles/Code/triangle-live-music-site-archived
```

- [ ] **Step 2: Verify nctrianglemusic/ is clean**

```bash
ls /Users/isaacknowles/Code/nctrianglemusic/
```

Expected: `CLAUDE.md  README.md  .claude/  .git/  .gitignore  docs/  pipeline/  site/`

```bash
python3 pipeline/cli.py status
```

Expected: still works (data files still in `pipeline/`).

- [ ] **Step 3: Final commit**

```bash
cd /Users/isaacknowles/Code/nctrianglemusic
git status  # should be clean
git log --oneline
```

Expected: clean working tree with ~10 commits showing the migration history.
