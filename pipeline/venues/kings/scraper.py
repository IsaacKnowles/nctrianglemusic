#!/usr/bin/env python3
"""
Kings event scraper / normalizer.

Kings (https://www.kingsraleigh.com/) is JS-rendered. The /shows page renders
empty; events are listed on the homepage. Individual show pages are also
JS-rendered and cannot be fetched directly, so we extract all event data from
the homepage DOM in one JS call, then normalize it here.

USAGE
-----
Step 1 — Extract raw event data from the browser.
  Navigate to https://www.kingsraleigh.com/ and run this JavaScript in the
  console (or via javascript_tool in Claude):

    JSON.stringify(Array.from(document.querySelectorAll('[class*="show"], [class*="event"], article'))
      .map(el => ({
        title: el.querySelector('[class*="title"], h2, h3')?.textContent.trim() || '',
        date:  el.querySelector('[class*="date"], time')?.textContent.trim() || '',
        time:  el.querySelector('[class*="time"]')?.textContent.trim() || '',
        price: el.querySelector('[class*="price"], [class*="ticket"]')?.textContent.trim() || '',
        url:   el.querySelector('a[href*="/shows/"]')?.href || ''
      })).filter(e => e.title && e.url))

  NOTE: Selectors are best-effort and may need tuning — verify output before
  saving. The script will warn if 0 events are parsed.

  Save the resulting JSON string to .tmp/kings_raw.json

Step 2 — Run this script:
    python3 scraper_kings.py [--raw .tmp/kings_raw.json] [--out .tmp/scraped_kings.json] [--days 90]

  Defaults:
    --raw   .tmp/kings_raw.json
    --out   .tmp/scraped_kings.json
    --days  90   (lookahead window from today)

OUTPUT
------
Normalized event JSON list ready for:
    python3 live_music_cli.py diff kings-id .tmp/scraped_kings.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from live_music.artists import detect_live_music, parse_artists

VENUE_KEY = "kings"
EVENT_ID_TAG = "kings-id"
VENUE_BASE_URL = "https://www.kingsraleigh.com"
DEFAULT_RAW = ".tmp/kings_raw.json"
DEFAULT_OUT = ".tmp/scraped_kings.json"
DEFAULT_DAYS = 90

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
FULL_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
    6: "June", 7: "July", 8: "August", 9: "September",
    10: "October", 11: "November", 12: "December",
}
DAY_NAMES_ABBR = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text


def make_event_id(title: str, date_obj: datetime) -> str:
    """Build a slug ID: <headliner-slug>-<monDD>"""
    first = re.split(r"\s*/\s*|\s*,\s*|\s+w/", title)[0].strip()
    first = re.sub(r"^[A-Z ]+(?:TOUR|FEST|PRESENTS):\s*", "", first)
    slug = slugify(first)
    slug = "-".join(slug.split("-")[:5])
    month_abbr = date_obj.strftime("%b").lower()
    day = date_obj.strftime("%d")
    return f"{slug}-{month_abbr}{day}"


def parse_date_string(date_str: str, year: int = None) -> datetime | None:
    """
    Parse flexible date strings from Kings DOM. Tries common patterns:
      - 'Friday, March 14'
      - 'Fri Mar 14'
      - 'March 14, 2026'
      - '3/14/2026', '3/14'
    Returns a date-only datetime (midnight) or None if unparseable.
    """
    if year is None:
        year = datetime.today().year
    s = date_str.strip()

    # Try Python strptime patterns
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%A, %B %d, %Y", "%a, %b %d, %Y",
                "%A, %B %d", "%a %b %d", "%B %d", "%b %d",
                "%m/%d/%Y", "%m/%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=year)
            return dt
        except ValueError:
            pass

    # Regex fallback: find month name + day number
    m = re.search(r"(\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                  r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
                  r"nov(?:ember)?|dec(?:ember)?)\b)\s+(\d{1,2})(?:[,\s]+(\d{4}))?",
                  s, re.I)
    if m:
        mon_name, day_str, yr_str = m.groups()
        mon_num = MONTHS.get(mon_name.lower()[:3]) or MONTHS.get(mon_name.lower())
        if mon_num:
            yr = int(yr_str) if yr_str else year
            try:
                return datetime(yr, mon_num, int(day_str))
            except ValueError:
                pass

    return None


def parse_time_string(time_str: str) -> tuple[int, int] | None:
    """Parse '8:00PM', '8 PM', '20:00' → (hour24, minute)."""
    s = time_str.strip()
    m = re.match(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", s, re.I)
    if not m:
        return None
    hour, minute, ampm = m.groups()
    hour = int(hour)
    minute = int(minute) if minute else 0
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    return hour, minute


def fmt_time(hour: int, minute: int) -> str:
    h = hour % 12 or 12
    suffix = "AM" if hour < 12 else "PM"
    return f"{h}:{minute:02d}{suffix}"


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def split_title_subtitle(raw_title: str) -> tuple[str, str, str]:
    presenter = ""
    tour_match = re.match(r"^([A-Z][A-Z\s$]+(?:TOUR|FEST|PRESENTS)):\s*(.+)$", raw_title)
    if tour_match:
        presenter = tour_match.group(1).strip()
        raw_title = tour_match.group(2).strip()

    if " / " in raw_title:
        parts = [p.strip() for p in raw_title.split(" / ")]
        return parts[0], "with " + ", ".join(parts[1:]), presenter

    if ", " in raw_title:
        parts = [p.strip() for p in raw_title.split(", ")]
        if all(len(p.split()) <= 6 for p in parts) and len(parts) >= 2:
            if not re.search(r'\b(the|learn|edition|market|tribute|competition|club)\b', raw_title, re.I):
                return parts[0], "with " + ", ".join(parts[1:]), presenter

    if " w/ " in raw_title:
        idx = raw_title.index(" w/ ")
        return raw_title[:idx].strip(), "w/ " + raw_title[idx + 4:].strip(), presenter

    return raw_title, "", presenter


def make_url(raw_url: str) -> str:
    if raw_url.startswith("http"):
        return raw_url
    if raw_url.startswith("/"):
        return VENUE_BASE_URL + raw_url
    return raw_url


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
