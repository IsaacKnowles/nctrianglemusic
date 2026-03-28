---
name: update-live-music
description: >
  Scrapes one Triangle-area live music venue (the stalest one) and saves new
  or changed events to the master state file. Use when updating live music
  events, running the scraper, or processing venue data.
disable-model-invocation: true
argument-hint: "[venue-key]"
---

## Goal

Each run picks **exactly one venue** — whichever has the oldest `last_updated` in the master state file — scrapes its upcoming events, and saves new or changed events to state. Unchanged events are skipped entirely.

Working directory: `/Users/isaacknowles/Code/nctrianglemusic/`

A management CLI (`pipeline/cli.py`) lives alongside the state file and handles all state reads, lookups, writes, and maintenance. Prefer it over manually parsing or editing the JSON wherever possible.

Each event has this normalized schema:
```json
{
  "id": "slug-from-url",
  "title": "...",
  "subtitle": "with ...",
  "presenter": "Promoter presents",
  "date_str": "Saturday, March 1st, 2026",
  "time": "8:00PM",
  "doors": "7:00PM",
  "admission": "$15 adv / $20 day-of",
  "music_links": { "spotify": "...", "youtube": "...", "bandcamp": "..." },
  "event_url": "https://venue-website.com/shows/event-slug",
  "start_datetime": "2026-03-01T20:00:00",
  "doors_datetime": "2026-03-01T19:00:00",
  "end_datetime": "2026-03-01T22:00:00",
  "content_hash": "md5_of_key_fields"
}
```

---

## Step 1: Select the stalest venue

Run the CLI's `stale` command to identify the target venue for this run:

```bash
python3 pipeline/cli.py stale
```

This prints the venue name, its key, and its `events_url`. Log which venue was selected.

> Venues with `last_updated: null` are treated as never updated and always go first. To see the full ranking, use `status` instead.

**Pre-run audit:** Run `audit` before scraping to surface any pre-existing data quality issues:

```bash
python3 pipeline/cli.py audit
```

Log the output. Do not abort if issues are found — they may be from a prior run and provide useful diagnostic context.

---

## Step 2: Scrape the venue's events page

Navigate to the venue's `events_url`. Use `read_page` at depth 2 to explore the page structure; use `ref_id` to drill into containers if output is too large. Strongly prefer the venue's website over ticket sellers.

**Lookahead window:** Only capture events within the next `_meta.lookahead_days` days from today.

**Extract per event:**
- Title (headliner), supporting acts/subtitle, presenter/promoter
- Full date string, show time, doors time
- Admission / ticket price
- The event's URL slug (use as the unique `id`)
- Any music links already on the page (Spotify, Bandcamp, YouTube, SoundCloud, website)

**Admission pricing rules:**
- **Aggressively pursue pricing data.** A blank `admission` field is a last resort, not a default. Work through the full chain before leaving it blank:
  1. Check the listing page for inline price text.
  2. Navigate to each event's detail page — look for price text and also for embedded ticket widgets (iframes, `#ticket-embed`, `od-internal-ticket-embed`, etc.).
  3. On detail pages with a "TICKETS" or "BUY" button/link, **follow that link or inspect the embed** — it often reveals a ticket widget showing tier prices and sold-out status. For OpenDate events, check `https://app.opendate.io/confirms/<event_id>/web_orders/new` directly.
  4. If the detail page links to an external ticket seller (Eventbrite, See Tickets, BoldType, TicketSpice, etc.), navigate there to read tier prices.
  5. Only leave `admission` blank if no price is findable after exhausting these steps.
- **Use only human-readable price text** from the event description or ticket purchase page — the actual words/numbers a user would read. Do **not** trust structured data meta tags (`itemprop="price"`, JSON-LD `price` fields, etc.): these often contain placeholder or minimum values (e.g. `$1`) set by ticketing platforms and are not authoritative.
- Leave `admission` blank (`""`) only if the price is genuinely unavailable after checking the individual event page.
- Do **not** infer free — an event is only free if the page explicitly says "Free" or "$0". A blank admission field means unknown, not free.
- If the listing page doesn't show prices, navigate to each event's detail page (via the Chrome plugin) to retrieve them. Batch this across events — don't skip it.

**Always use only the venue's own website — never Songkick, Bandsintown, Ticketmaster, etc.**

**If the page appears empty**, try the venue's homepage — some venues list upcoming shows there rather than on the dedicated events URL. Also try `wait` (2s) then re-read, or `get_page_text` as fallback for JS-heavy pages.

Write all scraped events to `.tmp/scraped_<venue_key>.json` for use in the diff step. Create the `.tmp/` folder if it doesn't exist. Delete this file during cleanup (Step 7); keep any `--report` output.

**Venue-specific notes:**
- **Kings**: See `pipeline/venues/kings/notes.md` for JS extraction snippet and quirks.
- **Neptune's Parlour** (`https://www.neptunesraleigh.com/events`): Each show at `/events/{slug}`.
- **Chapel of Bones**: See `pipeline/venues/chapel_of_bones/notes.md` for TickPick widget extraction and quirks.
- **Cat's Cradle**: Two rooms tracked separately. See `pipeline/venues/cats_cradle/notes.md` for JS extraction snippet, room detection, and price-fetching notes.
- **Slim's** (`https://slimsraleigh.com/`): plain HTML; use `pipeline/cli.py scrape generic`. Fetch monthly calendar pages (`/calendar/YYYY-MM/`) for the full lookahead window. Skip Open Jam and Mingle @ Slim's entries.
- **Lincoln Theatre** (`https://lincolntheatre.com/events/`): no special handling.
- **Local 506** (`https://local506.com/events/`): no special handling.
- **Motorco** (`https://motorcomusic.com/`): no special handling.
- **The Pinhook** (`https://thepinhook.com/events/`): no special handling.
- **The Fruit** (`https://www.durhamfruit.com/`): no special handling.
- **Sharp 9 Gallery** (`https://www.durhamjazzworkshop.org/`): no special handling.
- **Stanczyks** (`https://www.stanczyksdurham.com/#/events`): JS-rendered SPA. Use JavaScript DOM extraction to pull event data.

**Plain-HTML venues (WebFetch-accessible):** For venues that render events in standard HTML, use `WebFetch` to collect event data across monthly calendar pages, then write a simple raw JSON file and normalize it with `pipeline/cli.py scrape generic`:

```bash
# Raw input format (.tmp/<venue_key>_raw.json): list of objects with fields:
#   slug, title, subtitle, presenter, date (YYYY-MM-DD), show_time (HH:MM 24h),
#   end_time (HH:MM, optional), admission (optional), url
python3 pipeline/cli.py scrape generic --raw .tmp/<venue_key>_raw.json \
                           --out .tmp/scraped_<venue_key>.json \
                           [--days 90]
```

See `pipeline/venues/<venue>/scraper.py` for full field spec. Omit Open Jams, private events, and non-music entries before writing the raw JSON. The script handles date_str formatting, doors derivation (show − 1h), end_datetime, and lookahead filtering.

If the page is JS-heavy and `read_page` shows no events, try `wait` (2s) then re-read, or `get_page_text` as fallback. As a last resort, use JavaScript (`javascript_tool`) to extract event data directly from the DOM.

---

## Step 3: Classify shows and enrich artists

**3a — Validate `is_live_music` flags**
Review events auto-detected as `false`. Correct misclassifications in the scraped JSON before `diff`.

**3b — Validate `artists` array**
For each `is_live_music: true` event: confirm headliner is clean, supporting acts are split correctly. Fix in scraped JSON before `diff`.

**Artist quality rules:**

`is_live_music: false` when:
- Karaoke, comedy show, film screening, drag performance, dance class, yoga, workshop, market, food/drink tasting
- No named performing musician is featured
- Recurring series with no named performers listed

`is_live_music: true` when:
- Concert featuring named performer(s), including tribute acts, cover bands, and DJs

Artist name rules:
- If the event title is a recurring series name ("Rivalry Night", "Songwriter Showcase"), the series name is **not** an artist — use subtitle performers instead; if none, leave `artists: []`
- Strip tour/edition suffixes from headliner names: "RATBOYS : Tour Name" → headliner is "RATBOYS"
- Events with `is_live_music: false` must have `artists: []`

**3c — Enrich new artists**
For each artist in the venue's live-music events not yet in `artists_db.json` (or with empty links):
1. **Spotify**: `"{name}" site:open.spotify.com/artist` → URL + genre(s)
2. **Bandcamp**: `"{name} bandcamp"` → URL + genre tags
3. **Instagram**: `"{name} music instagram"` → profile URL if clearly music-related
4. **YouTube**: `"{name} official youtube"` → channel URL
Update `artists_db.json`. Set `last_enriched`. Budget: 4–6 searches/artist. Skip if name too generic or enriched within 30 days. Populate event's `music_links` from headliner's entry.

---

## Step 4: Compute content hashes and detect changes

Use the CLI's `diff` command to compare the scraped events against stored state in one step:

```bash
python3 pipeline/cli.py diff <event_id_tag> .tmp/scraped_<venue_key>.json --report .tmp/<venue_key>_changes.md
```

Example:
```bash
python3 pipeline/cli.py diff kings-id .tmp/scraped_kings.json --report .tmp/kings_changes.md
```

`diff` outputs a JSON array. Each entry has:
- `id` — event slug
- `status` — `"new"`, `"changed"`, or `"unchanged"`
- `field_diffs` — map of `field → [stored_value, new_value]` for changed fields

The `--report` flag writes a human-readable Markdown summary of new and changed events. Keep this file after the run (do not delete it with other temp files).

**Hash comparison is ephemeral:** `diff` always recomputes hashes from stored field values at comparison time. The stored `content_hash` field is never used for comparison — it is only updated when `set` or `repair` is run.

**Content hash normalization:** `content_hash` normalizes text before hashing (NFKC, Unicode quote/dash folding, casefold, whitespace collapse). This prevents curly-vs-straight quotes, en-dash/em-dash, and case differences from appearing as spurious changes.

| `diff` status | Action |
|---------------|--------|
| `"new"` | Save to state |
| `"changed"` | Update in state |
| `"unchanged"` | Skip |
| Not in scraped output | **Possibly removed** — log but do NOT delete |

To look up a single stored event (e.g. to inspect details):
```bash
python3 pipeline/cli.py get <event_id_tag>:<event_id>
# e.g. python3 pipeline/cli.py get kings-id:holy-fuck
```

---

## Step 5: Save updated state file

For each `"new"` or `"changed"` event from the diff output, write its full event JSON to `.tmp/events/<id>.json` and call `set`:

```bash
python3 pipeline/cli.py set <event_id_tag>:<event_id> .tmp/events/<id>.json
```

After all `set` calls, run repair and prune (`last_updated` is automatically stamped on the venue by each `set`, `delete`, and `prune` call):
```bash
python3 pipeline/cli.py repair
python3 pipeline/cli.py prune --days 30
```

**Temp file cleanup:** Delete `.tmp/scraped_<venue_key>.json` and `.tmp/events/` after saving. Keep `.tmp/<venue_key>_changes.md` (the diff report) — do not delete it.

---

## Step 6: Upload updated data and report results

After saving state, push the updated JSON to R2 so the live site reflects the new events:

```bash
python3 pipeline/cli.py upload
```

This pushes `live_music_events.json`, `artists_db.json`, and `venues_db.json` to R2.

Then report:

```
Venue processed: [Venue Name]
Lookahead: [N] days (today through [date])
New events added: [N]
Events updated: [N]
Unchanged (skipped): [N]
Possibly removed (not deleted): [N]
State file saved and uploaded.
```

---

## Success criteria

- Exactly one venue processed per run
- All new/changed events within the lookahead window are saved to state
- State file saved with updated `content_hash` and `last_updated`
- Updated data uploaded to R2 (`python3 pipeline/cli.py upload`)
- No duplicates created on re-runs
- Unchanged events trigger zero state writes

---

For the full CLI command reference, see [reference.md](reference.md).
