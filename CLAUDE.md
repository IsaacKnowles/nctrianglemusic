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
