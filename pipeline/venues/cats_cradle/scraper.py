#!/usr/bin/env python3
"""
Cat's Cradle event scraper / normalizer.

Cat's Cradle (https://catscradle.com/events/) has two rooms: Main Stage and
Back Room. The events listing page shows all events but does NOT include ticket
prices — those only appear on individual event detail pages. This scraper
fetches each event's detail page to extract the admission price.

NOTE: As of 2026-04-25, the site uses the Rockhouse Partners / Etix theme.
The old .tribe-* selectors no longer work. Use the snippet below.

USAGE
-----
Step 1 — Extract raw event cards from the browser.
  Navigate to https://catscradle.com/events/ and run this JavaScript in the
  console (or via javascript_tool in Claude):

    const events = Array.from(document.querySelectorAll('.rhpSingleEvent')).map(el => {
      const url = el.querySelector('a#eventTitle, .rhp-event-thumb a.url')?.href || '';
      const titleRaw = el.querySelector('.eventTitleDiv h2')?.textContent.trim() || '';
      const subtitleRaw = el.querySelector('.eventSubHeader')?.textContent.trim() || '';
      const dateRaw = el.querySelector('.singleEventDate')?.textContent.trim() || '';
      const timeRaw = el.querySelector('.rhp-event__time-text--list')?.textContent.trim() || '';
      const room = el.querySelector('.venueLink')?.textContent.trim() || '';
      const title = subtitleRaw ? `${titleRaw} w/ ${subtitleRaw}` : titleRaw;
      const showMatch = timeRaw.match(/show[:\\s]+(\\d{1,2}(?::\\d{2})?\\s*(?:am|pm))/i);
      const simpleMatch = timeRaw.match(/(\\d{1,2}(?::\\d{2})?\\s*(?:am|pm))/i);
      const time = showMatch ? showMatch[1].trim() : (simpleMatch ? simpleMatch[1].trim() : '');
      return { title, url, date: dateRaw, time, room };
    });
    JSON.stringify(events)

  Save the resulting JSON string to .tmp/cats_cradle_raw.json

  Optional: add a "doors_time" field (e.g. "7:30 pm") to any event object to
  override the default doors = show - 1hr calculation.

Step 2 — Run the scraper:
    python3 pipeline/cli.py scrape cats-cradle [--no-fetch] [--days 90]

  Flags:
    --days  90       Lookahead window from today (default)
    --no-fetch       Skip individual page fetches (faster, but admission = "")

  Outputs two files:
    .tmp/scraped_cats-cradle.json            (Main Stage events)
    .tmp/scraped_cats-cradle-back-room.json  (Back Room events)

OUTPUT
------
Each output file is a normalized event JSON list ready for:
    python3 pipeline/cli.py diff cats-cradle-id .tmp/scraped_cats-cradle.json
    python3 pipeline/cli.py diff cats-cradle-br-id .tmp/scraped_cats-cradle-back-room.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

from live_music.artists import detect_live_music, parse_artists

VENUE_KEY_MAIN = "cats-cradle"
VENUE_KEY_BACK = "cats-cradle-back-room"
EVENT_ID_TAG_MAIN = "cats-cradle-id"
EVENT_ID_TAG_BACK = "cats-cradle-br-id"
VENUE_BASE_URL = "https://catscradle.com"
DEFAULT_RAW = ".tmp/cats_cradle_raw.json"
DEFAULT_OUT_MAIN = ".tmp/scraped_cats-cradle.json"
DEFAULT_OUT_BACK = ".tmp/scraped_cats-cradle-back-room.json"
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
ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)\b", re.I)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text


def strip_ordinals(s: str) -> str:
    """'March 14th' → 'March 14'"""
    return ORDINAL_RE.sub(r"\1", s)


def parse_date_string(date_str: str, year: int = None) -> datetime | None:
    if year is None:
        year = datetime.today().year
    s = strip_ordinals(date_str.strip())

    for fmt in (
        "%B %d, %Y", "%b %d, %Y",
        "%A, %B %d, %Y", "%a, %b %d, %Y",
        "%A, %B %d", "%a %b %d",
        "%B %d", "%b %d",
        "%m/%d/%Y", "%m/%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=year)
            return dt
        except ValueError:
            pass

    m = re.search(
        r"(\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\b)\s+(\d{1,2})(?:[,\s]+(\d{4}))?",
        s, re.I,
    )
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
    s = time_str.strip()
    m = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)", s, re.I)
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

    if " w/ " in raw_title:
        idx = raw_title.index(" w/ ")
        return raw_title[:idx].strip(), "w/ " + raw_title[idx + 4:].strip(), presenter

    if ", " in raw_title:
        parts = [p.strip() for p in raw_title.split(", ")]
        if all(len(p.split()) <= 6 for p in parts) and len(parts) >= 2:
            if not re.search(r'\b(the|learn|edition|market|tribute|competition|club)\b', raw_title, re.I):
                return parts[0], "with " + ", ".join(parts[1:]), presenter

    return raw_title, "", presenter


def detect_room(raw_room: str, raw_title: str) -> str:
    """Return 'Back Room' or 'Main Stage' based on available text."""
    combined = (raw_room + " " + raw_title).lower()
    if "back room" in combined or "backroom" in combined:
        return "Back Room"
    return "Main Stage"


# ---------------------------------------------------------------------------
# Individual event page fetching
# ---------------------------------------------------------------------------

def fetch_admission(event_url: str) -> str:
    """
    Fetch an individual Cat's Cradle event page and extract the admission price.
    Returns empty string if price cannot be determined (caller should NOT default to "Free").

    Looks for patterns like:
      - "$15 Advance / $18 Day of Show"
      - "General Admission: $20"
      - "Free" / "FREE" near a ticket/admission context
      - Structured meta price tags
    """
    try:
        req = urllib.request.Request(
            event_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; live-music-scraper/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as e:
        print(f"  WARNING: could not fetch {event_url}: {e}", file=sys.stderr)
        return ""

    # Look for price in admission/ticket context — scan ~500 chars around keywords
    # NOTE: intentionally skip itemprop="price" meta tags — ticketing platforms often
    # set these to placeholder/minimum values (e.g. $1) that don't reflect real prices.
    price_pattern = re.compile(
        r'\$\s*\d+(?:\.\d{2})?(?:\s*(?:adv(?:ance)?|day[\s-]of|door|ga|general))?'
        r'(?:\s*/\s*\$\s*\d+(?:\.\d{2})?(?:\s*(?:adv(?:ance)?|day[\s-]of|door))?)?',
        re.I,
    )
    for keyword in ("ticket", "admission", "advance", "door"):
        idx = html.lower().find(keyword)
        while idx != -1:
            window = html[max(0, idx - 100):idx + 400]
            m = price_pattern.search(window)
            if m:
                raw = m.group(0).strip().rstrip(".")
                return _clean_price(raw)
            idx = html.lower().find(keyword, idx + 1)
            if idx > html.lower().find(keyword) + 2000:
                break

    # "Free" in ticket/admission context
    for keyword in ("ticket", "admission"):
        idx = html.lower().find(keyword)
        if idx != -1:
            window = html[max(0, idx - 50):idx + 300]
            if re.search(r'\bfree\b', window, re.I):
                return "Free"

    return ""


def _clean_price(raw: str) -> str:
    """Normalize a scraped price string."""
    raw = raw.strip().rstrip(".")
    # Collapse whitespace around slashes
    raw = re.sub(r"\s*/\s*", " / ", raw)
    # Capitalize Advance / Day of
    raw = re.sub(r"\badv(?:ance)?\b", "Advance", raw, flags=re.I)
    raw = re.sub(r"\bday[\s-]of\b", "Day of Show", raw, flags=re.I)
    return raw


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    args = sys.argv[1:]
    raw_file = DEFAULT_RAW
    days = DEFAULT_DAYS
    fetch = True
    i = 0
    while i < len(args):
        if args[i] == "--raw" and i + 1 < len(args):
            raw_file = args[i + 1]; i += 2
        elif args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1]); i += 2
        elif args[i] == "--no-fetch":
            fetch = False; i += 1
        else:
            i += 1
    return raw_file, days, fetch


def run(raw_path=DEFAULT_RAW, days=DEFAULT_DAYS, fetch=True,
        out_main=DEFAULT_OUT_MAIN, out_back=DEFAULT_OUT_BACK):
    """Normalize raw Cat's Cradle event JSON into the standard schema.

    Outputs two files (always):
      out_main  (default: .tmp/scraped_cats-cradle.json)           Main Stage
      out_back  (default: .tmp/scraped_cats-cradle-back-room.json) Back Room

    raw_path:  path to .tmp/cats_cradle_raw.json
    days:      lookahead window in days
    fetch:     if True, fetches each event page for admission price (slower)
    out_main:  output path for Main Stage events
    out_back:  output path for Back Room events
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
        end_dt    = start_dt + timedelta(hours=2)

        raw_doors = raw.get("doors_time", "").strip()
        if raw_doors:
            parsed_doors = parse_time_string(raw_doors)
            if parsed_doors:
                dh, dm = parsed_doors
                doors_dt = start_dt.replace(hour=dh, minute=dm)
            else:
                doors_dt = start_dt - timedelta(hours=1)
        else:
            doors_dt = start_dt - timedelta(hours=1)

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

    with open(out_main, "w") as f:
        json.dump(main_events, f, indent=2, ensure_ascii=False)

    with open(out_back, "w") as f:
        json.dump(back_events, f, indent=2, ensure_ascii=False)

    print(f"Cat's Cradle scraper complete:")
    print(f"   Main Stage:  {len(main_events)} events -> {out_main}")
    print(f"   Back Room:   {len(back_events)} events -> {out_back}")
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
