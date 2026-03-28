#!/usr/bin/env python3
"""
live_music CLI — Management toolkit for the Live Music calendar state file.

Usage:
  python3 pipeline/cli.py <command> [options]

Commands:
  status                        Show all venues sorted by staleness
  stale                         Show only the single stalest venue
  events [--venue <key>]        List events (optionally filtered to one venue)
  get <event-key>               Look up one event by its full key (e.g. kings-id:holy-fuck)
  set <event-key> <json-file>   Insert or update an event by key (reads JSON from a file)
  delete <event-key>            Remove an event from state
  prune [--days <N>]            Remove events older than N days (default 30)
  audit                         Find data quality issues in the state file
  stats                         Summary statistics across all venues
  search <query>                Search event titles/subtitles for a string
  scrape <venue-key> [--raw <f>] [--out <f>] [--days N] [--no-fetch]
                                Normalize raw scraped JSON for a venue
  upcoming [--days <N>]         List events in the next N days (default 14)
  duplicates                    Find events that look like the same show
  export [--format csv|md]      Export the upcoming schedule as CSV or Markdown
  repair                        Auto-fix common issues (missing end_datetime, etc.)
  add-venue                     Register a new venue in the state file (starts with no events)
  sync-venues                   Regenerate venues_db.json from live_music_events.json (bootstrap/repair)
  upload                        Push live_music_events.json, artists_db.json, and venues_db.json to R2
  migrate-artists               Backfill is_live_music + artists fields on all events (idempotent)
  artists [--venue <key>]       List unique artists from events with enrichment status
  artist <query>                Look up an artist by name/slug and show all their shows
  fix-artist <old-slug> --name "New Name"  Rename an artist in artists_db and all events
  remove-artist <slug>          Remove an artist from artists_db and all events
  audit-artists [--report <f>]  Flag potentially bad artist entries for review

All commands read from and write to the STATE_FILE path below.
"""

import csv
import io
import json
import sys
from datetime import timedelta
from pathlib import Path

from .utils import (
    NOW_UTC, TODAY, DEFAULT_PRUNE_DAYS, DEFAULT_UPCOMING_DAYS,
    parse_dt, parse_event_dt, event_date, normalize_for_hash, content_hash,
    staleness_dt, age_str,
)
from .state import (
    STATE_FILE, ARTISTS_FILE, VENUES_FILE,
    load_state, save_state,
    parse_key, find_venue_by_tag,
    load_artists, save_artists,
    load_venues, save_venues,
)
from .artists import (
    cmd_artist, cmd_artists, cmd_migrate_artists,
    upsert_artists,
)

def _touch_venue(venue: dict):
    """Stamp last_updated on a venue dict to the current UTC time."""
    venue["last_updated"] = NOW_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show all venues sorted from most stale to most recent."""
    data = load_state()
    venues = data["venues"]
    sorted_venues = sorted(venues.items(), key=lambda kv: staleness_dt(kv[1]))

    print(f"\n{'VENUE':<22} {'LAST UPDATED':<32} {'AGE':<12} {'EVENTS':>6}  STATUS")
    print("─" * 85)
    for vk, v in sorted_venues:
        lu = v.get("last_updated")
        lu_dt = staleness_dt(v)
        lu_str = lu if lu else "never"
        age = age_str(lu_dt) if lu else "never"
        nevents = len(v.get("events", []))
        is_stalest = (vk == sorted_venues[0][0])
        flag = " ← NEXT" if is_stalest else ""
        print(f"  {v['name']:<20} {lu_str:<32} {age:<12} {nevents:>6}{flag}")
    print()


def cmd_stale(args):
    """Print just the stalest venue key — useful for scripting."""
    data = load_state()
    venues = data["venues"]
    stalest_key = min(venues.keys(), key=lambda k: staleness_dt(venues[k]))
    v = venues[stalest_key]
    print(f"Stalest venue: {v['name']} (key: {stalest_key})")
    print(f"  last_updated: {v.get('last_updated', 'never')}")
    print(f"  events_url:   {v.get('events_url')}")


def cmd_events(args):
    """List events, optionally filtered to a single venue."""
    venue_filter = None
    i = 0
    while i < len(args):
        if args[i] == "--venue" and i + 1 < len(args):
            venue_filter = args[i + 1]; i += 2
        else:
            i += 1

    data = load_state()
    venues = data["venues"]
    count = 0

    for vk, v in venues.items():
        if venue_filter and vk != venue_filter:
            continue
        events = v.get("events", [])
        if not events:
            continue
        print(f"\n── {v['name']} ({len(events)} events) ──")
        for e in sorted(events, key=lambda x: x.get("start_datetime", "")):
            edt = event_date(e)
            past = " [PAST]" if edt and edt.date() < TODAY else ""
            print(f"  {e.get('start_datetime','?'):>19}  {e.get('id','?'):<35} {e.get('title','')}{past}")
            count += 1

    print(f"\nTotal: {count} event(s)")


def cmd_get(args):
    """Look up a single event by its full key (e.g. kings-id:holy-fuck)."""
    if not args:
        print("Usage: get <event-key>"); sys.exit(1)
    key = args[0]
    tag, event_id = parse_key(key)
    data = load_state()
    vk, v = find_venue_by_tag(data, tag)
    if not v:
        print(f"ERROR: no venue found with event_id_tag '{tag}'"); sys.exit(1)
    for e in v.get("events", []):
        if e.get("id") == event_id:
            print(json.dumps(e, indent=2))
            return
    print(f"ERROR: event '{event_id}' not found in venue '{v['name']}'"); sys.exit(1)


def cmd_set(args):
    """Insert or update an event. Reads the new event JSON from a file or stdin."""
    if len(args) < 2:
        print("Usage: set <event-key> <json-file>  (or use - for stdin)"); sys.exit(1)
    key, json_src = args[0], args[1]
    tag, event_id = parse_key(key)

    if json_src == "-":
        new_event = json.load(sys.stdin)
    else:
        with open(json_src) as f:
            new_event = json.load(f)

    new_event["id"] = event_id
    new_event["content_hash"] = content_hash(new_event)

    data = load_state()
    vk, v = find_venue_by_tag(data, tag)
    if not v:
        print(f"ERROR: no venue found with event_id_tag '{tag}'"); sys.exit(1)

    events = v.get("events", [])
    for i, e in enumerate(events):
        if e.get("id") == event_id:
            events[i] = new_event
            _touch_venue(v)
            print(f"✏️  Updated event '{event_id}' in {v['name']}")
            save_state(data)
            _upsert_event_artists(new_event)
            return
    events.append(new_event)
    _touch_venue(v)
    print(f"➕ Inserted new event '{event_id}' into {v['name']}")
    save_state(data)
    _upsert_event_artists(new_event)


def _upsert_event_artists(event: dict):
    """After saving an event, upsert its artists into artists_db.json."""
    artists = event.get("artists", [])
    if not artists:
        return
    artists_data = load_artists()
    added = upsert_artists(artists_data, artists)
    if added:
        save_artists(artists_data)


def cmd_delete(args):
    """Remove an event from the state file."""
    if not args:
        print("Usage: delete <event-key>"); sys.exit(1)
    key = args[0]
    tag, event_id = parse_key(key)
    data = load_state()
    vk, v = find_venue_by_tag(data, tag)
    if not v:
        print(f"ERROR: no venue found with event_id_tag '{tag}'"); sys.exit(1)
    before = len(v.get("events", []))
    v["events"] = [e for e in v.get("events", []) if e.get("id") != event_id]
    after = len(v["events"])
    if before == after:
        print(f"WARNING: event '{event_id}' not found in {v['name']} — nothing changed")
    else:
        _touch_venue(v)
        print(f"🗑️  Deleted '{event_id}' from {v['name']}")
        save_state(data)


def cmd_prune(args):
    """Remove events older than N days from the state file."""
    days = DEFAULT_PRUNE_DAYS
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1]); i += 2
        else:
            i += 1
    cutoff = TODAY - timedelta(days=days)
    data = load_state()
    total_removed = 0
    for vk, v in data["venues"].items():
        before = v.get("events", [])
        kept, removed = [], []
        for e in before:
            edt = event_date(e)
            if edt and edt.date() < cutoff:
                removed.append(e)
            else:
                kept.append(e)
        if removed:
            print(f"  {v['name']}: removing {len(removed)} event(s) older than {cutoff}")
            for e in removed:
                print(f"    - [{e.get('start_datetime','')}] {e.get('title','')}")
            _touch_venue(v)
        v["events"] = kept
        total_removed += len(removed)
    if total_removed == 0:
        print(f"Nothing to prune (cutoff: {cutoff}, {days} days ago)")
    else:
        print(f"\n🗑️  Total pruned: {total_removed} event(s)")
        save_state(data)


def cmd_audit(args):
    """Find data quality issues across all events."""
    data = load_state()
    issues = []

    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            eid = f"{v['event_id_tag']}:{e.get('id','?')}"
            # Missing required fields
            for field in ["title", "start_datetime", "event_url"]:
                if not e.get(field):
                    issues.append((eid, f"missing '{field}'"))
            # Bad/missing end_datetime
            sd = parse_event_dt(e.get("start_datetime"))
            ed = parse_event_dt(e.get("end_datetime"))
            if sd and ed and ed <= sd:
                issues.append((eid, f"end_datetime ({e.get('end_datetime')}) <= start_datetime ({e.get('start_datetime')})"))
            if not e.get("end_datetime"):
                issues.append((eid, "missing 'end_datetime'"))
            # Hash mismatch
            expected = content_hash(e)
            if e.get("content_hash") and e["content_hash"] != expected:
                issues.append((eid, f"content_hash mismatch (stored: {e['content_hash'][:8]}…, computed: {expected[:8]}…)"))

    if not issues:
        print("✅ No issues found.")
    else:
        print(f"⚠️  {len(issues)} issue(s) found:\n")
        for eid, msg in issues:
            print(f"  [{eid}]  {msg}")


def cmd_stats(args):
    """Show summary statistics across the full state file."""
    data = load_state()
    total_events = 0
    total_future = 0
    total_past = 0
    total_no_music_links = 0
    furthest_date = None

    print(f"\n{'VENUE':<22} {'EVENTS':>6}  {'FUTURE':>6}  {'PAST':>6}  COVERAGE THROUGH")
    print("─" * 65)

    for vk, v in data["venues"].items():
        events = v.get("events", [])
        future_evts = [e for e in events if (event_date(e) and event_date(e).date() >= TODAY)]
        past_evts = [e for e in events if (event_date(e) and event_date(e).date() < TODAY)]
        no_ml = sum(1 for e in events if not e.get("music_links"))
        max_dt = max((event_date(e) for e in future_evts if event_date(e)), default=None)
        total_events += len(events)
        total_future += len(future_evts)
        total_past += len(past_evts)
        total_no_music_links += no_ml
        if max_dt and (furthest_date is None or max_dt > furthest_date):
            furthest_date = max_dt
        coverage = max_dt.strftime("%b %d, %Y") if max_dt else "—"
        print(f"  {v['name']:<20} {len(events):>6}  {len(future_evts):>6}  {len(past_evts):>6}  {coverage}")

    print("─" * 65)
    print(f"  {'TOTAL':<20} {total_events:>6}  {total_future:>6}  {total_past:>6}")
    print(f"\n  Events without music links: {total_no_music_links}")
    print(f"  Furthest future event:      {furthest_date.strftime('%b %d, %Y') if furthest_date else '—'}")
    print()


def cmd_search(args):
    """Search event titles and subtitles for a query string."""
    if not args:
        print("Usage: search <query>"); sys.exit(1)
    query = " ".join(args).lower()
    data = load_state()
    results = []
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            haystack = " ".join([
                e.get("title", ""),
                e.get("subtitle", ""),
                e.get("presenter", ""),
            ]).lower()
            if query in haystack:
                results.append((v["name"], e))
    if not results:
        print(f'No events matching "{query}"')
        return
    print(f'\n{len(results)} result(s) for "{query}":\n')
    for venue_name, e in sorted(results, key=lambda r: r[1].get("start_datetime", "")):
        print(f"  {venue_name:<20}  {e.get('start_datetime','?'):>19}  {e.get('title')}")
        if e.get("subtitle"):
            print(f"            {'':>20}  {'':>19}  {e['subtitle']}")


def cmd_upcoming(args):
    """List events in the next N days."""
    days = DEFAULT_UPCOMING_DAYS
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1]); i += 2
        else:
            i += 1
    cutoff = TODAY + timedelta(days=days)
    data = load_state()
    results = []
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            edt = event_date(e)
            if edt and TODAY <= edt.date() <= cutoff:
                results.append((v["name"], e))
    results.sort(key=lambda r: r[1].get("start_datetime", ""))
    print(f"\nUpcoming events — next {days} days (through {cutoff}):\n")
    if not results:
        print("  (none)")
        return
    prev_date = None
    for venue_name, e in results:
        edt = event_date(e)
        date_str = edt.strftime("%a %b %d") if edt else "?"
        if date_str != prev_date:
            print(f"\n  {date_str}")
            prev_date = date_str
        time_str = e.get("time", "?")
        print(f"    {time_str:<8}  {venue_name:<20}  {e.get('title')}")
        if e.get("subtitle"):
            print(f"             {'':>8}  {'':>20}  {e['subtitle']}")
    print(f"\n  Total: {len(results)} event(s)")


def cmd_duplicates(args):
    """Find events that look like the same show (same normalized title + date)."""
    data = load_state()
    seen = {}  # (normalized_title, date) -> list of (venue, event)
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            norm_title = e.get("title", "").strip().lower()
            edt = event_date(e)
            date_key = edt.date().isoformat() if edt else "?"
            k = (norm_title, date_key)
            seen.setdefault(k, []).append((v["name"], e))
    dupes = {k: vs for k, vs in seen.items() if len(vs) > 1}
    if not dupes:
        print("✅ No duplicate events found.")
        return
    print(f"\n⚠️  {len(dupes)} potential duplicate group(s):\n")
    for (title, date), occurrences in dupes.items():
        print(f"  '{title}'  on {date}:")
        for venue_name, e in occurrences:
            print(f"    {venue_name}: {e.get('id')}")


def cmd_export(args):
    """Export upcoming events as CSV or Markdown."""
    fmt = "md"
    i = 0
    while i < len(args):
        if args[i] == "--format" and i + 1 < len(args):
            fmt = args[i + 1]; i += 2
        else:
            i += 1

    data = load_state()
    results = []
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            edt = event_date(e)
            if edt and edt.date() >= TODAY:
                results.append((v["name"], e, edt))
    results.sort(key=lambda r: r[2])

    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Date", "Day", "Time", "Venue", "Title", "Subtitle", "Admission", "Event URL"])
        for venue_name, e, edt in results:
            writer.writerow([
                edt.strftime("%Y-%m-%d"),
                edt.strftime("%A"),
                e.get("time", ""),
                venue_name,
                e.get("title", ""),
                e.get("subtitle", ""),
                e.get("admission", ""),
                e.get("event_url", ""),
            ])
        print(out.getvalue(), end="")
    else:
        print(f"# Upcoming Live Music — Triangle NC\n")
        print(f"_Generated {TODAY.isoformat()} · {len(results)} events_\n")
        prev_date = None
        for venue_name, e, edt in results:
            date_str = edt.strftime("%A, %B %-d")
            if date_str != prev_date:
                print(f"\n## {date_str}")
                prev_date = date_str
            time_str = e.get("time", "TBD")
            title = e.get("title", "")
            subtitle = e.get("subtitle", "")
            admission = e.get("admission", "")
            url = e.get("event_url", "")
            line = f"- **{venue_name}** · {time_str} · [{title}]({url})"
            if subtitle:
                line += f" _{subtitle}_"
            if admission:
                line += f" · {admission}"
            print(line)


def cmd_repair(args):
    """Auto-fix common data issues: missing end_datetime, hash mismatches, timestamp formats."""
    data = load_state()
    fixes = 0
    for vk, v in data["venues"].items():
        # Normalize last_updated to plain Z-suffix UTC ISO format
        lu = v.get("last_updated")
        if lu:
            lu_dt = parse_dt(lu)
            if lu_dt:
                normalized = lu_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if normalized != lu:
                    v["last_updated"] = normalized
                    print(f"  🔧 Normalized last_updated for {v['name']}: {lu!r} → {normalized!r}")
                    fixes += 1

        for e in v.get("events", []):
            # Fix missing end_datetime (default 2 hours after start)
            if not e.get("end_datetime") and e.get("start_datetime"):
                sd = parse_event_dt(e["start_datetime"])
                if sd:
                    e["end_datetime"] = (sd + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
                    print(f"  🔧 Set end_datetime for {v['name']} / {e.get('id')}")
                    fixes += 1
            # Fix hash mismatches
            expected = content_hash(e)
            if e.get("content_hash") and e["content_hash"] != expected:
                e["content_hash"] = expected
                print(f"  🔧 Recomputed content_hash for {v['name']} / {e.get('id')}")
                fixes += 1
            # Set hash where missing
            if not e.get("content_hash"):
                e["content_hash"] = content_hash(e)
                print(f"  🔧 Added missing content_hash for {v['name']} / {e.get('id')}")
                fixes += 1
    if fixes == 0:
        print("✅ Nothing to repair.")
    else:
        print(f"\n✅ {fixes} fix(es) applied.")
        save_state(data)


def cmd_diff(args):
    """Compare a JSON file of scraped events against the stored state for a venue.

    Usage:
      diff <event_id_tag> <scraped.json> [--report <report.md>]

    <scraped.json> must be an array of event objects, each containing at least:
      id, title, subtitle, date_str, time, admission

    Hashes are computed ephemerally from field values (with normalization) on both
    sides — the stored content_hash field is never used for comparison.

    Output (JSON array) has one entry per scraped event:
      { "id": "...", "status": "new"|"changed"|"unchanged",
        "stored_hash": "...", "new_hash": "...",
        "calendar_event_id": "...",
        "field_diffs": { "field": ["stored_val", "new_val"], ... } }

    --report <file>  Write a human-readable markdown change log to <file>.

    Also prints a summary of events in state but not scraped (possibly removed).
    """
    if len(args) < 2:
        print("Usage: diff <event_id_tag> <scraped.json> [--report <file>]"); sys.exit(1)
    tag, json_src = args[0], args[1]
    report_path = None
    i = 2
    while i < len(args):
        if args[i] == "--report" and i + 1 < len(args):
            report_path = args[i + 1]; i += 2
        else:
            i += 1

    if json_src == "-":
        scraped_events = json.load(sys.stdin)
    else:
        with open(json_src) as f:
            scraped_events = json.load(f)

    # ── Input validation ────────────────────────────────────────────────────
    REQUIRED_SCRAPED_FIELDS = ["id", "title", "date_str", "start_datetime"]
    for idx, e in enumerate(scraped_events):
        for field in REQUIRED_SCRAPED_FIELDS:
            if not e.get(field):
                eid = e.get("id", f"<index {idx}>")
                print(f"WARNING: scraped event '{eid}' missing required field '{field}'", file=sys.stderr)

    data = load_state()
    vk, v = find_venue_by_tag(data, tag)
    if not v:
        print(f"ERROR: no venue found with event_id_tag '{tag}'"); sys.exit(1)

    # ── Scrape-count sanity check ───────────────────────────────────────────
    stored_future_count = sum(
        1 for e in v.get("events", [])
        if (edt := parse_event_dt(e.get("start_datetime", ""))) and edt.date() >= TODAY
    )
    SCRAPE_SANITY_THRESHOLD = 0.5
    if stored_future_count >= 3 and len(scraped_events) < stored_future_count * SCRAPE_SANITY_THRESHOLD:
        print(
            f"WARNING: Scrape sanity check FAILED for '{tag}' — "
            f"scraped {len(scraped_events)} event(s) but {stored_future_count} future event(s) "
            f"are stored in state. Possible scrape failure. Review diff output carefully.",
            file=sys.stderr
        )

    stored = {e["id"]: e for e in v.get("events", [])}
    scraped_by_id = {e["id"]: e for e in scraped_events}
    scraped_ids = set(scraped_by_id.keys())
    results = []
    DIFF_FIELDS = ["title", "subtitle", "date_str", "time", "admission"]

    for e in scraped_events:
        eid = e.get("id", "")
        new_hash = content_hash(e)
        if eid not in stored:
            results.append({
                "id": eid, "status": "new",
                "stored_hash": None, "new_hash": new_hash,
                "calendar_event_id": None,
                "field_diffs": {},
            })
        else:
            # Always recompute from stored field values (ephemeral, normalized)
            stored_hash = content_hash(stored[eid])
            cal_id = stored[eid].get("calendar_event_id")
            field_diffs = {}
            for f in DIFF_FIELDS:
                sv, nv = stored[eid].get(f, ""), e.get(f, "")
                if sv != nv:
                    field_diffs[f] = [sv, nv]
            if stored_hash != new_hash:
                results.append({
                    "id": eid, "status": "changed",
                    "stored_hash": stored_hash, "new_hash": new_hash,
                    "calendar_event_id": cal_id,
                    "field_diffs": field_diffs,
                })
            else:
                results.append({
                    "id": eid, "status": "unchanged",
                    "stored_hash": stored_hash, "new_hash": new_hash,
                    "calendar_event_id": cal_id,
                    "field_diffs": {},
                })

    # ── Events in state but not scraped ────────────────────────────────────
    removed = [eid for eid in stored if eid not in scraped_ids]
    for eid in removed:
        stored_event = stored[eid]
        results.append({
            "id": eid,
            "status": "possibly_removed",
            "stored_hash": content_hash(stored_event),
            "new_hash": None,
            "calendar_event_id": stored_event.get("calendar_event_id"),
            "field_diffs": {},
            "stored_title": stored_event.get("title", ""),
            "stored_start_datetime": stored_event.get("start_datetime", ""),
        })

    print(json.dumps(results, indent=2))
    counts = {"new": 0, "changed": 0, "unchanged": 0, "possibly_removed": 0}
    for r in results:
        counts[r["status"]] += 1
    print(
        f"\n# Summary: {counts['new']} new, {counts['changed']} changed, "
        f"{counts['unchanged']} unchanged, {counts['possibly_removed']} possibly removed",
        file=sys.stderr
    )

    if report_path:
        _write_diff_report(report_path, v["name"], results, removed, scraped_by_id, stored)
        print(f"📄 Report written: {report_path}", file=sys.stderr)


def _write_diff_report(path: str, venue_name: str, results: list, removed: list,
                       scraped_by_id: dict, stored: dict):
    lines = [
        f"# {venue_name} Change Report — {TODAY.isoformat()}",
        f"**Venue:** {venue_name}",
        "",
    ]
    new_items = [r for r in results if r["status"] == "new"]
    changed_items = [r for r in results if r["status"] == "changed"]
    unchanged_count = sum(1 for r in results if r["status"] == "unchanged")

    lines += [f"**Summary:** {len(new_items)} new · {len(changed_items)} changed · "
              f"{unchanged_count} unchanged · {len(removed)} possibly removed", ""]

    if new_items:
        lines += ["## 🆕 New Events", ""]
        for r in new_items:
            e = scraped_by_id[r["id"]]
            lines += [
                f"### {e.get('title', r['id'])}",
                f"- **Date:** {e.get('date_str', '')}",
                f"- **Time:** {e.get('time', '')}  |  **Doors:** {e.get('doors', '')}",
                f"- **Admission:** {e.get('admission', '')}",
                f"- **URL:** {e.get('event_url', '')}",
                "",
            ]

    if changed_items:
        lines += ["## 🔄 Changed Events", ""]
        for r in changed_items:
            e = scraped_by_id[r["id"]]
            lines += [f"### {e.get('title', r['id'])}  _(ID: `{r['id']}`)_"]
            for field, (old_val, new_val) in r.get("field_diffs", {}).items():
                lines.append(f"- **{field}:** `{old_val}` → `{new_val}`")
            lines.append("")

    if removed:
        lines += ["## ⚠️ Possibly Removed (not deleted)", ""]
        for eid in removed:
            se = stored.get(eid, {})
            dt = se.get("start_datetime", "")
            title = se.get("title", eid)
            lines.append(f"- `{eid}` — {title} ({dt[:10] if dt else 'no date'})")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def cmd_add_venue(args):
    """Register a new venue in the state file.

    Usage:
      add-venue --key <key> --name <name> --address <address> --url <events_url> --tag <event_id_tag>

    All five flags are required. The key must be a unique slug used as the
    dictionary key (e.g. 'kings'). The tag must also be unique and is used to
    namespace event IDs (e.g. 'kings-id').

    The new venue starts with last_updated=null so it is immediately treated as
    the stalest venue and scraped on the next run.
    """
    flags = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args):
            flags[args[i][2:]] = args[i + 1]
            i += 2
        else:
            print(f"ERROR: unexpected argument '{args[i]}' — use --flag value pairs")
            sys.exit(1)

    required = {"key", "name", "address", "url", "tag"}
    missing = required - flags.keys()
    if missing:
        print(f"ERROR: missing required flag(s): {', '.join('--' + f for f in sorted(missing))}")
        print()
        print("Usage: add-venue --key <key> --name <name> --address <address> --url <events_url> --tag <event_id_tag>")
        print()
        print("  --key      Unique slug for this venue (e.g. 'kings')")
        print("  --name     Display name            (e.g. 'Kings')")
        print("  --address  Street address          (e.g. '1012 S Blount St, Raleigh, NC 27601')")
        print("  --url      Events page URL         (e.g. 'https://www.kingsraleigh.com/shows')")
        print("  --tag      Event ID tag prefix     (e.g. 'kings-id')")
        sys.exit(1)

    key     = flags["key"].strip()
    name    = flags["name"].strip()
    address = flags["address"].strip()
    url     = flags["url"].strip()
    tag     = flags["tag"].strip()

    if not key.replace("-", "").replace("_", "").isalnum():
        print(f"ERROR: --key '{key}' should contain only letters, digits, hyphens, or underscores")
        sys.exit(1)
    if not tag:
        print("ERROR: --tag cannot be empty")
        sys.exit(1)

    data = load_state()
    venues = data["venues"]

    if key in venues:
        print(f"ERROR: a venue with key '{key}' already exists ('{venues[key]['name']}')")
        sys.exit(1)

    for vk, v in venues.items():
        if v.get("event_id_tag") == tag:
            print(f"ERROR: event_id_tag '{tag}' is already used by venue '{v['name']}' (key: '{vk}')")
            sys.exit(1)

    new_venue = {
        "name":         name,
        "address":      address,
        "events_url":   url,
        "event_id_tag": tag,
        "last_updated": None,
        "events":       [],
    }

    venues[key] = new_venue
    save_state(data)

    # Also upsert into venues_db.json
    venues_db = load_venues()
    venues_db[key] = {
        "name":         name,
        "address":      address,
        "events_url":   url,
        "event_id_tag": tag,
        "last_updated": None,
    }
    save_venues(venues_db)

    print(f"✅ Venue added:")
    print(f"   Key:    {key}")
    print(f"   Name:   {name}")
    print(f"   Tag:    {tag}")
    print(f"   URL:    {url}")
    print(f"   Address:{address}")
    print(f"   Status: never scraped — will be picked up on next run")


def cmd_sync_venues(args):
    """Regenerate venues_db.json from the current live_music_events.json venues dict.

    This is a bootstrap / repair tool. It reads every venue entry from the state
    file and writes its metadata (everything except the events list) to venues_db.json,
    keyed by venue slug. Run once after deploying to generate venues_db.json, or
    whenever venues are added/edited outside of the add-venue command.
    """
    data = load_state()
    venues_db = {}
    for vk, v in data["venues"].items():
        venues_db[vk] = {
            "name":         v["name"],
            "address":      v.get("address", ""),
            "events_url":   v.get("events_url", ""),
            "event_id_tag": v.get("event_id_tag", ""),
            "last_updated": v.get("last_updated"),
        }
    save_venues(venues_db)
    print(f"venues_db.json synced: {len(venues_db)} venue(s)")
    for vk, vd in venues_db.items():
        print(f"   {vk:<30} {vd['name']}")


def cmd_upload(args):
    """Push live_music_events.json, artists_db.json, and venues_db.json to the private R2 bucket."""
    import subprocess
    project_root = Path(__file__).parent.parent

    result = subprocess.run(
        [
            "wrangler", "r2", "object", "put",
            "triangle-live-music-data/live_music_events.json",
            "--file", str(STATE_FILE),
            "--content-type", "application/json",
            "--remote",
        ],
        cwd=project_root,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    # Only upload artists_db.json if it exists
    if ARTISTS_FILE.exists():
        result2 = subprocess.run(
            [
                "wrangler", "r2", "object", "put",
                "triangle-live-music-data/artists_db.json",
                "--file", str(ARTISTS_FILE),
                "--content-type", "application/json",
                "--remote",
            ],
            cwd=project_root,
        )
        if result2.returncode != 0:
            sys.exit(result2.returncode)

    # Only upload venues_db.json if it exists
    if VENUES_FILE.exists():
        result3 = subprocess.run(
            [
                "wrangler", "r2", "object", "put",
                "triangle-live-music-data/venues_db.json",
                "--file", str(VENUES_FILE),
                "--content-type", "application/json",
                "--remote",
            ],
            cwd=project_root,
        )
        sys.exit(result3.returncode)


def cmd_fix_artist(args):
    """Rename an artist: update artists_db.json and all matching events.

    Usage: fix-artist <old-slug> --name "Correct Name"
    """
    if not args:
        print("Usage: fix-artist <old-slug> --name \"Correct Name\""); sys.exit(1)
    old_slug = args[0]
    new_name = None
    i = 1
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            new_name = args[i + 1]; i += 2
        else:
            i += 1
    if not new_name:
        print("ERROR: --name is required"); sys.exit(1)

    from .utils import slugify
    new_slug = slugify(new_name)

    artists_data = load_artists()
    if old_slug not in artists_data:
        print(f"ERROR: artist '{old_slug}' not found in artists_db.json"); sys.exit(1)

    # Update artists_db: add new entry, remove old
    old_entry = artists_data[old_slug].copy()
    old_entry["name"] = new_name
    artists_data[new_slug] = old_entry
    if new_slug != old_slug:
        del artists_data[old_slug]

    # Update events
    data = load_state()
    events_updated = 0
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            changed = False
            for artist in e.get("artists", []):
                if artist.get("slug") == old_slug:
                    artist["slug"] = new_slug
                    artist["name"] = new_name
                    changed = True
            if changed:
                e["content_hash"] = content_hash(e)
                events_updated += 1

    save_artists(artists_data)
    save_state(data)
    if new_slug != old_slug:
        print(f"✅ Renamed '{old_slug}' → '{new_slug}' (name: \"{new_name}\") across {events_updated} event(s)")
    else:
        print(f"✅ Updated name for '{old_slug}' to \"{new_name}\" across {events_updated} event(s)")


def cmd_remove_artist(args):
    """Remove an artist from artists_db.json and from all event artists arrays.

    Usage: remove-artist <slug>
    """
    if not args:
        print("Usage: remove-artist <slug>"); sys.exit(1)
    slug = args[0]

    artists_data = load_artists()
    if slug not in artists_data:
        print(f"WARNING: artist '{slug}' not found in artists_db.json — will still scan events")
    else:
        del artists_data[slug]

    data = load_state()
    events_updated = 0
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            before = len(e.get("artists", []))
            e["artists"] = [a for a in e.get("artists", []) if a.get("slug") != slug]
            if len(e.get("artists", [])) != before:
                e["content_hash"] = content_hash(e)
                events_updated += 1

    save_artists(artists_data)
    save_state(data)
    print(f"✅ Removed artist '{slug}' from db and {events_updated} event(s)")


def cmd_audit_artists(args):
    """Flag potentially problematic artist entries for review.

    Usage: audit-artists [--report <file>]

    Flags each artist slug against known bad patterns, then lists unflagged
    entries in a Clean section for spot-checking.
    """
    report_path = None
    i = 0
    while i < len(args):
        if args[i] == "--report" and i + 1 < len(args):
            report_path = args[i + 1]; i += 2
        else:
            i += 1

    artists_data = load_artists()
    data = load_state()

    # Build slug → list of events
    slug_events: dict[str, list] = {}
    for vk, v in data["venues"].items():
        for e in v.get("events", []):
            for artist in e.get("artists", []):
                slug = artist.get("slug", "")
                if slug:
                    slug_events.setdefault(slug, []).append({
                        "title": e.get("title", ""),
                        "subtitle": e.get("subtitle", ""),
                        "venue": v["name"],
                        "date": (e.get("start_datetime", "") or "")[:10],
                        "event_url": e.get("event_url", ""),
                    })

    # Pattern rules: (flag_name, test_fn)
    FLAG_RULES = [
        ("tour_suffix",   lambda s: any(t in s for t in ["tour", "anniversary-tour", "edition-tour"])),
        ("rescheduled",   lambda s: "rescheduled" in s),
        ("evening_with",  lambda s: s.startswith("an-evening-with")),
        ("album_release", lambda s: "album-release" in s or "ep-release" in s),
        ("party_rave",    lambda s: any(t in s for t in ["party", "rave", "dance-night"])),
        ("event_series",  lambda s: any(t in s for t in ["showcase", "festival", "lineup", "mass", "workshop"])),
        ("tribute_desc",  lambda s: "tribute-to" in s or "a-tribute" in s),
        ("long_slug",     lambda s: len(s.split("-")) > 7),
    ]

    flagged: list[tuple[str, list[str], dict]] = []  # (slug, flags, db_entry)
    clean: list[str] = []

    all_slugs = sorted(set(list(artists_data.keys()) + list(slug_events.keys())))
    for slug in all_slugs:
        flags = [name for name, test in FLAG_RULES if test(slug)]
        entry = artists_data.get(slug, {})
        if flags:
            flagged.append((slug, flags, entry))
        else:
            clean.append(slug)

    # ── Print to stdout ─────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  ARTIST AUDIT — {len(flagged)} flagged, {len(clean)} clean")
    print(f"{'─'*70}\n")

    for slug, flags, entry in flagged:
        name = entry.get("name", slug)
        print(f"  [{', '.join(flags)}]  {name}  (slug: {slug})")
        for ev in slug_events.get(slug, []):
            print(f"    ↳ {ev['title']} | {ev['subtitle']} | {ev['venue']} | {ev['date']} | {ev['event_url']}")
        print()

    print(f"\n{'─'*70}")
    print(f"  CLEAN entries ({len(clean)}) — spot-check sample recommended")
    print(f"{'─'*70}\n")
    for slug in clean:
        entry = artists_data.get(slug, {})
        name = entry.get("name", slug)
        print(f"  {name}  (slug: {slug})")

    # ── Write report file ───────────────────────────────────────────────────
    if report_path:
        lines = [
            f"# Artist Audit Report",
            f"",
            f"**Flagged:** {len(flagged)}  |  **Clean:** {len(clean)}",
            f"",
            f"## Flagged Entries",
            f"",
        ]
        for slug, flags, entry in flagged:
            name = entry.get("name", slug)
            lines += [
                f"### `{slug}`",
                f"**Name:** {name}  |  **Flags:** {', '.join(flags)}",
                f"",
            ]
            evs = slug_events.get(slug, [])
            if evs:
                lines.append("**Events:**")
                for ev in evs:
                    lines.append(
                        f"- {ev['title']} | {ev['subtitle']} | {ev['venue']} | {ev['date']} | {ev['event_url']}"
                    )
            else:
                lines.append("_(no events reference this artist)_")
            lines.append("")

        lines += [
            f"## Clean Entries ({len(clean)})",
            f"",
        ]
        for slug in clean:
            entry = artists_data.get(slug, {})
            name = entry.get("name", slug)
            evs = slug_events.get(slug, [])
            lines.append(f"- **{name}** (`{slug}`)")
            for ev in evs:
                lines.append(
                    f"  - {ev['title']} | {ev['subtitle']} | {ev['venue']} | {ev['date']} | {ev['event_url']}"
                )

        with open(report_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n📄 Report written: {report_path}", file=sys.stderr)


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
        # Fallback: try with underscores (e.g. "cats-cradle" -> "cats_cradle")
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


# ── Dispatch ───────────────────────────────────────────────────────────────────

COMMANDS = {
    "status":          cmd_status,
    "stale":           cmd_stale,
    "events":          cmd_events,
    "get":             cmd_get,
    "set":             cmd_set,
    "delete":          cmd_delete,
    "prune":           cmd_prune,
    "audit":           cmd_audit,
    "stats":           cmd_stats,
    "search":          cmd_search,
    "scrape":          cmd_scrape,
    "upcoming":        cmd_upcoming,
    "duplicates":      cmd_duplicates,
    "export":          cmd_export,
    "repair":          cmd_repair,
    "add-venue":       cmd_add_venue,
    "sync-venues":     cmd_sync_venues,
    "diff":            cmd_diff,
    "upload":          cmd_upload,
    "migrate-artists": cmd_migrate_artists,
    "artists":         cmd_artists,
    "artist":          cmd_artist,
    "fix-artist":      cmd_fix_artist,
    "remove-artist":   cmd_remove_artist,
    "audit-artists":   cmd_audit_artists,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd not in COMMANDS:
        print(f"ERROR: unknown command '{cmd}'. Run with --help to see available commands.", file=sys.stderr)
        sys.exit(1)
    COMMANDS[cmd](rest)


if __name__ == "__main__":
    main()
