#!/usr/bin/env python3
"""
Chapel of Bones event scraper / normalizer.

Chapel of Bones uses a TickPick embedded widget for event listings — there are no
individual event pages on the venue's own website. Events must be extracted from the
widget DOM via JavaScript, then normalized into the standard live_music_events schema.

USAGE
-----
Step 1 — Extract raw event data from the browser.
  Navigate to https://chapelofbones.com/events/ and run this JavaScript in the console
  (or via javascript_tool in Claude):

    const items = Array.from(document.querySelectorAll('.eventGridItem_b9cc1'));
    const raw = items.map(item => ({
      title: item.querySelector('.eventTitle_eacac')?.textContent.trim() || '',
      dateLocation: item.querySelector('.eventLocation_0f1cb')?.textContent.trim() || '',
      price: item.querySelector('.eventPriceButton_b33bd')?.textContent.trim() || ''
    }));
    JSON.stringify(raw)

  Save the resulting JSON string to .tmp/chapel_of_bones_raw.json

Step 2 — Run this script:
    python3 scraper_chapel_of_bones.py [--raw .tmp/chapel_of_bones_raw.json] [--out .tmp/scraped_chapel-of-bones.json] [--days 90]

  Defaults:
    --raw   .tmp/chapel_of_bones_raw.json
    --out   .tmp/scraped_chapel-of-bones.json
    --days  90   (lookahead window from today)

OUTPUT
------
Normalized event JSON list ready for:
    python3 live_music_cli.py diff chapel-of-bones-id .tmp/scraped_chapel-of-bones.json
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from live_music.artists import detect_live_music, parse_artists

VENUE_KEY = "chapel-of-bones"
EVENT_ID_TAG = "chapel-of-bones-id"
EVENT_URL = "https://chapelofbones.com/events/"
DEFAULT_RAW = ".tmp/chapel_of_bones_raw.json"
DEFAULT_OUT = ".tmp/scraped_chapel-of-bones.json"
DEFAULT_DAYS = 90

# TickPick adds a flat ~14.3% service fee.  Prices with fractional cents like
# $17.14, $13.71, $11.43, $28.57, $18.29 are fee-inflated; strip the fee back
# to the nearest whole dollar.
TICKPICK_FEE = 1.143


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
MONTH_NAMES = {v: k for k, v in MONTHS.items()}
FULL_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
    6: "June", 7: "July", 8: "August", 9: "September",
    10: "October", 11: "November", 12: "December",
}
DAY_NAMES = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
    "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}


def parse_tickpick_date(date_location: str, year: int = 2026) -> dict:
    """
    Parse TickPick date strings like:
      'Fri Mar 13 @ 7 pm • Chapel of Bones, Raleigh, NC'
      'Sun Apr 5 @ 6:30 pm • Chapel of Bones, Raleigh, NC'
    Returns a dict with date_str, time, doors, start/doors/end_datetime.
    """
    # Strip venue suffix after bullet
    date_part = date_location.split("•")[0].strip()

    m = re.match(r"(\w{3}) (\w{3}) (\d+) @ (\d+):?(\d{2})? (am|pm)", date_part)
    if not m:
        raise ValueError(f"Cannot parse date: {date_part!r}")

    day_abbr, month_abbr, day_str, hour_str, min_str, ampm = m.groups()
    month_num = MONTHS[month_abbr]
    day_num = int(day_str)
    hour = int(hour_str)
    minute = int(min_str) if min_str else 0

    if ampm == "pm" and hour != 12:
        hour24 = hour + 12
    elif ampm == "am" and hour == 12:
        hour24 = 0
    else:
        hour24 = hour

    full_day = DAY_NAMES[day_abbr]
    full_month = FULL_MONTH_NAMES[month_num]
    date_str_fmt = f"{full_day}, {full_month} {day_num}, {year}"

    start_dt = datetime(year, month_num, day_num, hour24, minute)
    doors_dt = start_dt - timedelta(hours=1)
    end_dt = start_dt + timedelta(hours=2)

    def fmt_dt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    def fmt_time(dt: datetime) -> str:
        h = dt.hour % 12 or 12
        suffix = "AM" if dt.hour < 12 else "PM"
        return f"{h}:{dt.minute:02d}{suffix}"

    return {
        "date_str": date_str_fmt,
        "time": fmt_time(start_dt),
        "doors": fmt_time(doors_dt),
        "start_datetime": fmt_dt(start_dt),
        "doors_datetime": fmt_dt(doors_dt),
        "end_datetime": fmt_dt(end_dt),
    }


def normalize_price(price_str: str) -> str:
    """Strip TickPick service fee from prices with non-zero cents."""
    s = price_str.strip()
    if s.lower() in ("free", ""):
        return "Free"
    if s.startswith("$"):
        try:
            val = float(s[1:])
        except ValueError:
            return s
        # If the price has fractional cents (i.e. is fee-inflated), strip fee
        if val != round(val):
            base = round(val / TICKPICK_FEE)
            return f"${base}"
        return f"${int(val)}"
    return s


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text


def make_event_id(raw_title: str, date_location: str) -> str:
    """
    Build a slug ID: <headliner-slug>-<monDD>
    e.g. 'Obscura / Allegaeon / ...' on Mar 22 → 'obscura-mar22'
    """
    # First artist before / , or w/
    first = re.split(r"\s*/\s*|\s*,\s*|\s+w/", raw_title)[0].strip()
    # Trim 'TOUR:' style prefixes
    first = re.sub(r"^[A-Z ]+TOUR:\s*", "", first)
    parts = date_location.split("•")[0].strip().split()
    # parts[1] = month abbr, parts[2] = day
    month_abbr = parts[1].lower()[:3]
    day = parts[2].zfill(2) if len(parts) > 2 else "00"
    slug = slugify(first)
    # Cap slug at 5 words to keep IDs readable but preserve enough specificity
    slug = "-".join(slug.split("-")[:5])
    return f"{slug}-{month_abbr}{day}"


def split_title_subtitle(raw_title: str) -> tuple[str, str, str]:
    """
    Separate headliner from supporting acts.

    Rules (in priority order):
      1. 'TOUR_LABEL: Headliner / Act2 / ...'  → presenter=tour label, title=headliner
      2. 'Act1 / Act2 / Act3'                  → title=Act1, subtitle='with Act2, Act3'
      3. 'Act1, Act2, Act3'  (band list)        → title=Act1, subtitle='with Act2, Act3'
      4. 'Act1 w/ Act2'                         → title=Act1, subtitle='w/ Act2'
      5. otherwise                              → title=raw_title, subtitle=''
    """
    presenter = ""

    # Pattern: ALL-CAPS words ending in colon at start, then slash-separated acts
    tour_match = re.match(r"^([A-Z][A-Z\s$]+(?:TOUR|FEST|PRESENTS)):\s*(.+)$", raw_title)
    if tour_match:
        presenter = tour_match.group(1).strip()
        raw_title = tour_match.group(2).strip()

    if " / " in raw_title:
        parts = [p.strip() for p in raw_title.split(" / ")]
        title = parts[0]
        subtitle = "with " + ", ".join(parts[1:])
        return title, subtitle, presenter

    # Comma-separated band list (not a sentence): detect if all parts look like band names
    if ", " in raw_title:
        parts = [p.strip() for p in raw_title.split(", ")]
        # Treat as a band list only if every part is short (≤5 words) and no long phrases
        if all(len(p.split()) <= 6 for p in parts) and len(parts) >= 2:
            # Skip for obvious non-band-list titles (contain 'the', articles, etc.)
            if not re.search(r'\b(the|learn|edition|market|tribute|competition|club)\b', raw_title, re.I):
                title = parts[0]
                subtitle = "with " + ", ".join(parts[1:])
                return title, subtitle, presenter

    if " w/ " in raw_title:
        idx = raw_title.index(" w/ ")
        title = raw_title[:idx].strip()
        subtitle = "w/ " + raw_title[idx + 4:].strip()
        return title, subtitle, presenter

    return raw_title, "", presenter


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
