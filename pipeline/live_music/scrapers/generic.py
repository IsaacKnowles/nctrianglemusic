#!/usr/bin/env python3
"""
Generic event normalizer for plain-HTML venues.

For venues that render events in plain HTML (fetchable via WebFetch), Claude
gathers raw event data from the page and writes a simple "raw" JSON file.
This script normalizes that raw data into the standard live_music_events schema.

USAGE
-----
Step 1 — Gather event data via WebFetch and write to a raw JSON file.
  Each entry in the raw file needs only a handful of fields:

    [
      {
        "slug":      "event-url-slug",          // used as event id
        "title":     "Headliner Name",
        "subtitle":  "with Supporting Act",     // optional, "" if none
        "presenter": "Promoter Presents",       // optional, "" if none
        "date":      "2026-03-18",              // YYYY-MM-DD
        "show_time": "20:00",                   // HH:MM 24-hour
        "end_time":  "22:00",                   // HH:MM 24-hour, optional (default: show_time + 2h)
        "admission": "$10",                     // optional, "" if unknown
        "url":       "https://venue.com/shows/event-slug/"
      },
      ...
    ]

  Save to .tmp/<venue_key>_raw.json

Step 2 — Run this script:
    python3 scraper_generic.py --raw .tmp/<venue_key>_raw.json \\
                               --out .tmp/scraped_<venue_key>.json \\
                               [--days 90]

  Defaults:
    --raw   .tmp/generic_raw.json
    --out   .tmp/scraped_generic.json
    --days  90

OUTPUT
------
Normalized event JSON list ready for:
    python3 live_music_cli.py diff <event_id_tag> .tmp/scraped_<venue_key>.json

NOTES
-----
- "slug" becomes the event "id". Use the URL path segment (e.g. "long-relief").
- "date" must be YYYY-MM-DD. "show_time" / "end_time" must be HH:MM (24-hour).
- If "end_time" is omitted or blank, end defaults to show_time + 2 hours.
- "doors" is always derived as show_time - 1 hour (Slim's and most venues
  don't publish doors time; adjust manually in .tmp/scraped_*.json if known).
- Events outside today … today+days are filtered out automatically.
- Omit Open Jams, private events, and non-music entries before writing raw JSON.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from live_music.artists import detect_live_music, parse_artists

DEFAULT_RAW = ".tmp/generic_raw.json"
DEFAULT_OUT = ".tmp/scraped_generic.json"
DEFAULT_DAYS = 90

FULL_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
    6: "June", 7: "July", 8: "August", 9: "September",
    10: "October", 11: "November", 12: "December",
}


def fmt_time(hour: int, minute: int) -> str:
    h = hour % 12 or 12
    suffix = "AM" if hour < 12 else "PM"
    return f"{h}:{minute:02d}{suffix}"


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_hhmm(s: str) -> tuple[int, int]:
    """Parse 'HH:MM' (24-hour) → (hour, minute)."""
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {s!r}")
    return int(parts[0]), int(parts[1])


def parse_args():
    args = sys.argv[1:]
    raw_file = DEFAULT_RAW
    out_file = DEFAULT_OUT
    days = DEFAULT_DAYS
    i = 0
    while i < len(args):
        if args[i] == "--raw" and i + 1 < len(args):
            raw_file = args[i + 1]; i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            out_file = args[i + 1]; i += 2
        elif args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1]); i += 2
        else:
            i += 1
    return raw_file, out_file, days


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
