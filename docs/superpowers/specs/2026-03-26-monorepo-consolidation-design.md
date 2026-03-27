---
name: Monorepo Consolidation
description: Design for combining live-music-calendar-update and triangle-live-music-site into a single organized repository
type: project
---

# Monorepo Consolidation Design

**Date:** 2026-03-26

## Background

Two repositories have been maintained separately:

- `live-music-calendar-update` — Python data pipeline: scrapes 14 Triangle-area venues, manages three JSON databases (events, artists, venues), enriches artist genres via Spotify/Bandcamp, uploads to Cloudflare R2.
- `triangle-live-music-site` — Cloudflare Worker + single-file frontend: fetches JSON from R2 at request time and injects it into HTML.

Both share the same R2 bucket (`triangle-live-music-data`) as their integration point. The goal is to consolidate into a single, well-organized repository with professional structure, eliminate cruft, and improve coordination between the pipeline and the site.

## Repository Structure

```
nctrianglemusic/                   ← fresh git repo
├── pipeline/                      ← data pipeline (Python)
│   ├── live_music/                ← core library
│   │   ├── __init__.py
│   │   ├── cli.py                 ← all CLI commands + scrape <venue> dispatcher
│   │   ├── state.py               ← load/save for events/artists/venues JSON
│   │   ├── artists.py             ← detection, parsing, upsert
│   │   ├── utils.py               ← dates, hashing, slugify, constants
│   │   └── scrapers/
│   │       └── generic.py         ← shared HTML normalizer for plain-HTML venues
│   ├── venues/                    ← one directory per venue with custom scrapers
│   │   ├── kings/
│   │   │   ├── scraper.py         ← JS extraction + normalization
│   │   │   └── notes.md           ← site quirks, JS snippets, scraping tips
│   │   ├── cats_cradle/
│   │   │   ├── scraper.py
│   │   │   └── notes.md
│   │   ├── chapel_of_bones/
│   │   │   ├── scraper.py
│   │   │   └── notes.md
│   │   └── [future venues get a dir when they need custom code]
│   ├── cli.py                     ← entry point: python3 pipeline/cli.py <cmd>
│   ├── enrich_genres.py           ← standalone Spotify + Bandcamp genre backfill
│   └── .env                       ← gitignored (Spotify client ID + secret)
├── site/                          ← Cloudflare Worker site
│   ├── worker.js                  ← fetches R2, injects data into HTML at request time
│   ├── index.html                 ← complete frontend (CSS + JS inline, no build step)
│   └── wrangler.toml              ← Cloudflare config (R2 binding, custom domain)
├── .claude/                       ← Claude Code config
│   ├── settings.local.json        ← merged permissions from both repos
│   └── skills/
│       └── update-live-music/
│           ├── SKILL.md           ← updated paths; reads venues/<v>/notes.md per venue
│           └── reference.md       ← updated CLI reference
├── docs/
│   └── superpowers/
│       ├── specs/                 ← design specs (this file)
│       └── plans/                 ← implementation plans
├── CLAUDE.md                      ← project overview, key commands, how to add a venue
├── .gitignore
└── README.md
```

## Key Design Decisions

### Per-Venue Directories

Venues with custom scrapers get a directory under `pipeline/venues/`. Each directory contains:

- `scraper.py` — all extraction and normalization logic for that venue
- `notes.md` — venue-specific scraping guidance: site quirks, JS snippet to extract raw data, price parsing edge cases, URL patterns, etc.

Plain-HTML venues (Slim's, Motorco, Pinhook, etc.) do not get a `venues/` directory until they need custom code. They continue to use `live_music/scrapers/generic.py` via the CLI.

This structure scales cleanly: adding a new venue with complex scraping needs means creating one new directory. The skill reads `notes.md` for the target venue rather than having all venue quirks embedded in SKILL.md.

### Eliminated Cruft

The following are removed:

- `scraper_kings.py`, `scraper_cats_cradle.py`, `scraper_chapel_of_bones.py`, `scraper_generic.py` — thin wrapper scripts at the repo root. Replaced by `cli.py scrape <venue>`.
- `live_music_cli.py` — thin wrapper. Replaced by `pipeline/cli.py`.
- `live_music/scrapers/kings.py`, `live_music/scrapers/cats_cradle.py`, `live_music/scrapers/chapel_of_bones.py` — venue-specific code moves to `venues/<venue>/scraper.py`.

### Single CLI Entry Point

All pipeline operations go through `python3 pipeline/cli.py <command>`. New command added:

```
cli.py scrape <venue-key>   ← dispatches to venues/<venue>/scraper.py
```

Full workflow per run:
```
cli.py stale                    → identify stalest venue (e.g. "kings")
cli.py scrape kings             → extract + normalize → .tmp/scraped_kings.json
cli.py diff kings-id .tmp/scraped_kings.json
cli.py set / repair / prune
cli.py upload                   → push all three JSON files to R2
```

### Skills

The `update-live-music` skill moves to `.claude/skills/` at the repo root. SKILL.md is updated to:

- Use correct paths (`pipeline/cli.py` instead of the stale `~/Documents/` path)
- Reference `pipeline/venues/<venue>/notes.md` for venue-specific guidance instead of embedding all notes inline
- Reflect the new `scrape <venue>` command

### Data Files

`live_music_events.json`, `artists_db.json`, and `venues_db.json` sit in `pipeline/` at runtime and are gitignored. R2 is the source of truth. The `.tmp/` scratchpad directory is also gitignored.

### CLAUDE.md

A `CLAUDE.md` at the repo root provides:
- Repository layout overview
- How the pipeline works end-to-end
- Key CLI commands
- R2 bucket name and Cloudflare context
- How to add a new venue (checklist)

## What Does Not Change

- R2 bucket name: `triangle-live-music-data`
- The three JSON database schemas (events, artists, venues)
- The Worker's data injection strategy (parallel R2 fetch → `window.__EVENTS__` + `window.__GENRES__`)
- The one-venue-per-run scraping workflow
- Cloudflare deployment process for the site

## Migration Summary

1. `git init` at `nctrianglemusic/`
2. Copy `pipeline/` files from `live-music-calendar-update/`
3. Copy `site/` files from `triangle-live-music-site/` (already on `main` with genre-display merged)
4. Move venue scrapers from `live_music/scrapers/` to `venues/<venue>/scraper.py`
5. Add `scrape <venue>` command to `live_music/cli.py`; update `pipeline/cli.py` entry point
6. Write `venues/<venue>/notes.md` for each custom venue (extract from SKILL.md)
7. Merge `.claude/settings.local.json` from both repos
8. Update SKILL.md paths and per-venue notes references
9. Write `CLAUDE.md` and `README.md`
10. Write `.gitignore`; commit
11. Move old repos to `/Users/isaacknowles/Code/` as archives
