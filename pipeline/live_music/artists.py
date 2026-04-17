"""
live_music/artists.py — Artist detection, parsing, and enrichment logic.
"""

import re
import sys

from .state import load_state, save_state, load_artists, save_artists
from .utils import slugify

# ── Detection ──────────────────────────────────────────────────────────────────

NON_MUSIC_KEYWORDS = [
    "karaoke", "trivia", "comedy", "open mic", "open jam", "drag", "burlesque",
    "film", "screening", "class", "lesson", "workshop", "market", "private",
    "yoga", "dance party", "bingo", "shrimp boil", "whiskey tasting", "improv theater",
    "book club", "giveaway",
]


def detect_live_music(title: str, subtitle: str = "", presenter: str = "") -> bool:
    """Return False if the event is clearly not a live music show; True otherwise.
    Conservative — over-includes rather than misses genuine shows."""
    text = title.lower()
    return not any(kw in text for kw in NON_MUSIC_KEYWORDS)


# ── Parsing ────────────────────────────────────────────────────────────────────

def parse_artists(title: str, subtitle: str) -> list[dict]:
    """Extract a structured artist list from event title and subtitle.

    Returns a list of dicts with keys: name, slug, role ("headliner" or "support").
    """
    # Strip tour-label prefix from title (e.g. "FOO TOUR: Band" → "Band")
    title = re.sub(r"^[A-Z][A-Z\s$]+(?:TOUR|FEST|PRESENTS):\s*", "", title).strip()
    # Strip bracket prefix (e.g. "[Late]", "[Early]")
    title = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
    # Strip trailing tour/edition suffix appended after the artist name, e.g.:
    #   "RATBOYS : When the Sun Explodes Tour 2026" -> "RATBOYS"
    #   "The Black Angels: Passover 2026 Tour"      -> "The Black Angels"
    title = re.sub(r'\s*[–:]\s*.+\b(tour|edition|anniversary)\b.*$', '', title, flags=re.I).strip()
    # Strip "– An Evening With" suffix
    title = re.sub(r'\s*[–:]\s*an evening with\s*$', '', title, flags=re.I).strip()

    artists = []

    if title:
        artists.append({"name": title, "slug": slugify(title), "role": "headliner"})

    sub = subtitle.strip()
    if sub:
        # Strip "with " / "w/ " prefix
        sub = re.sub(r"^(?:with\s+|w/\s*)", "", sub, flags=re.I).strip()
        if sub:
            # Split on " / ", ", ", " & "
            parts = re.split(r"\s*/\s*|,\s*|\s+&\s+", sub)
            for part in parts:
                part = part.strip()
                if part:
                    artists.append({"name": part, "slug": slugify(part), "role": "support"})

    return artists


# ── Upsert helper ──────────────────────────────────────────────────────────────

def upsert_artists(artists_data: dict, artists: list[dict]) -> int:
    """Add new artists to artists_data (stub entry). Returns count of newly added."""
    added = 0
    for artist in artists:
        slug = artist.get("slug", "")
        if slug and slug not in artists_data:
            artists_data[slug] = {
                "name": artist["name"],
                "genre": [],
                "links": {
                    "spotify": "",
                    "bandcamp": "",
                    "instagram": "",
                    "youtube": "",
                    "website": "",
                },
                "last_enriched": None,
            }
            added += 1
    return added


# ── CLI commands ───────────────────────────────────────────────────────────────

def cmd_migrate_artists(args):
    """Backfill is_live_music and artists fields on all existing events (idempotent).

    Skips events where the field already exists — preserves manual corrections.
    """
    data = load_state()
    artists_data = load_artists()
    events_updated = 0
    artists_added = 0

    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            changed = False

            if "is_live_music" not in e:
                e["is_live_music"] = detect_live_music(
                    e.get("title", ""), e.get("subtitle", ""), e.get("presenter", "")
                )
                changed = True

            if "artists" not in e:
                e["artists"] = parse_artists(e.get("title", ""), e.get("subtitle", ""))
                changed = True

            if changed:
                events_updated += 1

            # Always upsert artists from this event (even if fields already existed)
            artists_added += upsert_artists(artists_data, e.get("artists", []))

    save_state(data)
    save_artists(artists_data)
    print(f"✅ migrate-artists: {events_updated} event(s) updated, {artists_added} new artist(s) added to db")


def cmd_artists(args):
    """List all unique artists from events, with enrichment status.

    Usage: artists [--venue <key>]
    """
    venue_filter = None
    i = 0
    while i < len(args):
        if args[i] == "--venue" and i + 1 < len(args):
            venue_filter = args[i + 1]; i += 2
        else:
            i += 1

    data = load_state()
    artists_data = load_artists()

    # Collect unique artists by slug
    seen: dict[str, dict] = {}
    for vk, v in data["venues"].items():
        if venue_filter and vk != venue_filter:
            continue
        for e in v.get("events", []):
            for artist in e.get("artists", []):
                slug = artist.get("slug", "")
                if slug and slug not in seen:
                    seen[slug] = artist

    if not seen:
        print("No artists found. Run: python3 live_music_cli.py migrate-artists")
        return

    print(f"\n{'ARTIST':<30} {'SLUG':<30} {'ENRICHED':<12} GENRE")
    print("─" * 90)
    for slug in sorted(seen.keys()):
        artist = seen[slug]
        db_entry = artists_data.get(slug, {})
        enriched = db_entry.get("last_enriched") or ""
        enriched_str = enriched[:10] if enriched else "—"
        genres = db_entry.get("genre", [])
        genre_str = ", ".join(genres) if genres else "(not yet enriched)"
        print(f"  {artist['name']:<28} {slug:<30} {enriched_str:<12} {genre_str}")

    print(f"\n  Total: {len(seen)} unique artist(s)")


def cmd_artist(args):
    """Look up an artist by name or slug and show all their shows.

    Usage: artist <query>

    Partial matching — 'oort' matches 'oort-patrol'. Case-insensitive.
    Shows upcoming events first, then past, across all venues.
    """
    if not args:
        print("Usage: artist <query>"); return

    query = " ".join(args).lower().strip()
    query_slug = slugify(query)

    data = load_state()
    artists_data = load_artists()

    # Build: slug -> list of (venue_name, event)
    slug_shows: dict[str, list] = {}
    slug_artist: dict[str, dict] = {}
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            for artist in e.get("artists", []):
                slug = artist.get("slug", "")
                if not slug:
                    continue
                slug_shows.setdefault(slug, []).append((v["name"], e, artist["role"]))
                slug_artist.setdefault(slug, artist)

    # Find matching slugs (partial match on slug or name)
    matches = [
        slug for slug in slug_shows
        if query_slug in slug or query in slug_artist[slug]["name"].lower()
    ]

    if not matches:
        print(f'No artists matching "{query}"')
        return

    from .utils import parse_event_dt, TODAY

    for slug in sorted(matches):
        artist = slug_artist[slug]
        db = artists_data.get(slug, {})
        genres = db.get("genre", [])
        links = db.get("links", {})

        print(f"\n{artist['name']}  (slug: {slug})")
        if genres:
            print(f"  Genre: {', '.join(genres)}")
        link_parts = [f"{k}: {v}" for k, v in links.items() if v]
        if link_parts:
            print(f"  Links: {' · '.join(link_parts)}")

        shows = slug_shows[slug]
        # Sort: upcoming first (by date asc), then past (by date desc)
        def sort_key(item):
            edt = parse_event_dt(item[1].get("start_datetime", ""))
            return (edt.date() if edt else TODAY, item[0])

        from datetime import datetime as _dt
        def edt_date(e):
            dt = parse_event_dt(e.get("start_datetime", ""))
            return dt.date() if dt else None

        def edt_or_min(e):
            return parse_event_dt(e.get("start_datetime", "")) or _dt.min

        upcoming = [(vn, e, role) for vn, e, role in shows
                    if (edt_date(e) or TODAY) >= TODAY]
        past     = [(vn, e, role) for vn, e, role in shows
                    if (edt_date(e) or TODAY) < TODAY]

        upcoming.sort(key=lambda x: edt_or_min(x[1]))
        past.sort(key=lambda x: edt_or_min(x[1]), reverse=True)

        if upcoming:
            print(f"  UPCOMING ({len(upcoming)}):")
            for vn, e, role in upcoming:
                synced = "✓" if e.get("calendar_event_id") else "✗"
                edt = parse_event_dt(e.get("start_datetime", ""))
                date_s = edt.strftime("%a %b %-d, %Y") if edt else "?"
                print(f"    [{synced}] {date_s:<20}  {e.get('time','?'):<8}  {vn:<22}  {e.get('title','')}  [{role}]")
        if past:
            print(f"  PAST ({len(past)}):")
            for vn, e, role in past:
                edt = parse_event_dt(e.get("start_datetime", ""))
                date_s = edt.strftime("%a %b %-d, %Y") if edt else "?"
                print(f"         {date_s:<20}  {e.get('time','?'):<8}  {vn:<22}  {e.get('title','')}  [{role}]")

    if len(matches) > 1:
        print(f"\n({len(matches)} artists matched)")
