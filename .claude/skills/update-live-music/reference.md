# CLI Reference — `pipeline/cli.py`

`pipeline/cli.py` is the entry point for all pipeline operations. Run from the repo root: `python3 pipeline/cli.py <command> [options]`

| Command | What it does |
|---------|-------------|
| `scrape <venue-key> [--raw f] [--out f] [--days N] [--no-fetch]` | Normalize raw scraped JSON for a venue using `pipeline/venues/<venue>/scraper.py` |
| `status` | All venues ranked from most stale to most recent, with event counts |
| `stale` | Just the single stalest venue — what this skill uses at Step 2 |
| `get <tag:id>` | Print a single event as JSON (e.g. `kings-id:holy-fuck`) |
| `set <tag:id> <file.json>` | Insert or overwrite one event from a JSON file; auto-stamps `last_updated` on the venue |
| `diff <tag> <scraped.json> [--report <file>]` | Compare scraped events against stored state; outputs JSON array with `status` (`new`/`changed`/`unchanged`/`possibly_removed`), `field_diffs` per event. Warns if scraped count is less than 50% of stored future events. `--report` writes a Markdown change log. |
| `delete <tag:id>` | Remove an event from state only |
| `prune [--days N]` | Remove events older than N days (default 30) |
| `audit` | Find data quality issues: missing fields, hash mismatches |
| `upcoming [--days N]` | Events in the next N days (default 14), grouped by date |
| `repair` | Auto-fix missing `end_datetime` and recompute stale `content_hash` values |
| `add-venue` | Register a new venue in state + venues_db.json (see `--help` for flags) |
| `sync-venues` | Regenerate `venues_db.json` from current state (bootstrap/repair tool) |
| `upload` | Push `live_music_events.json`, `artists_db.json`, and `venues_db.json` to R2 |
| `migrate-artists` | Backfill `is_live_music` + `artists` fields on all events (idempotent) |
| `artists [--venue <key>]` | List unique artists with enrichment status |
| `artist <query>` | Look up an artist by name/slug and show all their shows |
| `search <query>` | Search event titles/subtitles |
| `export [--format csv\|md]` | Export upcoming schedule as CSV or Markdown |
| `stats` | Summary statistics across all venues |
| `duplicates` | Find events with the same normalized title + date |
