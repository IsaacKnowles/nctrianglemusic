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

A management CLI (`pipeline/cli.py`) handles all reads, writes, and maintenance of the three database files (`live_music_events.json`, `artists_db.json`, `venues_db.json`). Never directly edit those files. Writing temporary JSON to `.tmp/` (raw extracts, scraped output, etc.) is fine and expected. If an operation on the databases cannot be performed via the CLI, the skill run has FAILED — notify the user, explain the failure, and stop.

Each event has this normalized schema:
```json
⏺ {
    "id": "slug-from-url",
    "title": "Headliner Name",
    "subtitle": "with Supporting Act",
    "presenter": "Promoter presents",
    "is_live_music": true,
    "artists": [
      { "name": "Headliner Name", "slug": "headliner-slug", "role": "headliner" },
      { "name": "Supporting Act", "slug": "supporting-slug", "role": "support" }
    ],
    "date_str": "Saturday, March 1st, 2026",
    "time": "8:00PM",
    "doors": "7:00PM",
    "admission": "$15 adv / $20 day-of",
    "music_links": { "spotify": "https://...", "youtube": "https://...", "bandcamp": "https://..." },
    "event_url": "https://venue-website.com/shows/event-slug",
    "start_datetime": "2026-03-01T20:00:00",
    "doors_datetime": "2026-03-01T19:00:00",
    "end_datetime": "2026-03-01T22:00:00",
    "content_hash": "md5_of_key_fields"
  }
```
  Notes:
  - subtitle — empty string "" if no support acts
  - presenter — empty string "" if no promoter
  - is_live_music — true for concerts/DJs, false for karaoke, comedy, etc.
  - artists — empty array [] when is_live_music is false; role is "headliner" or "support"
  - music_links — omits keys that are unknown rather than storing empty strings (e.g. only "spotify" and "youtube" if
  Bandcamp is unknown)
  - doors_datetime — can be null if doors time was not scraped
  - date_str — may or may not include ordinal suffix (3rd vs 3) depending on venue/scraper; normalize_for_hash treats
  them as equivalent


---
As you go through steps, if you encounter errors or have to take significant action to improvise, notify the user and stop. This issue needs to be resolved by the user with your assistance. Log smaller or more annoying issues as you'll be providing a report at the end.

## Step 1: Select the stalest venue

Run `status` first to see the full picture — venue rankings, stored event counts, and staleness — then `stale` to confirm the target:

```bash
python3 pipeline/cli.py status
python3 pipeline/cli.py stale
```

`status` shows all venues ranked from most to least stale, with stored event counts. **Read this output before proceeding** — it tells you how many events are already in state for the target venue, which is essential context for interpreting the diff output. `stale` confirms the single venue to process.

> Venues with `last_updated: null` are treated as never updated and always go first.

Log the target venue name, key, `events_url`, and current stored event count.

**Pre-run audit:** Run `audit` before scraping to surface any pre-existing data quality issues:

```bash
python3 pipeline/cli.py audit
```

Log the output. Do not abort if issues are found — they may be from a prior run and provide useful diagnostic context.

---

## Step 2: Scrape the venue's events page

Navigate to the venue's `events_url`. Strongly prefer the venue's website over ticket sellers.

-**Lookahead window:** Only capture events within the next 90 days from today (the default `--days 90` passed to all scrapers)

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

---

### Venue-Specific Extraction

> **Skill accuracy check:** Each venue entry below makes specific claims about how the site works (rendering method, URL structure, extraction approach, etc.). Before proceeding, verify these claims against what you actually observe. If a significant claim no longer holds — the site has been redesigned, a JS framework replaced plain HTML, the URL structure changed, etc. — **stop, notify the user, and work with them to update this skill** before continuing. Do not silently improvise around structural changes; an updated skill is more valuable than a one-off workaround.

#### Kings (`kings-id`)
Server-rendered HTML — use `WebFetch` to read the homepage, write `.tmp/kings_raw.json`, then run the scraper. See [venues/kings.md](venues/kings.md) for the raw format, extraction notes, and scrape/diff commands.

#### Cat's Cradle (`cats-cradle-id`, `cats-cradle-br-id`)
Two rooms tracked separately. See [venues/cats-cradle.md](venues/cats-cradle.md) for JS extraction snippet (with fallback), scrape/diff commands, and pricing notes.

#### Chapel of Bones (`chapel-of-bones-id`)
TickPick widget rendered in an **iframe** — `javascript_tool` cannot access the DOM. Use `get_page_text` to extract rendered event text, click "Show more" first to load all events. Pre-split ` / ` titles before writing raw JSON. Use `scrape generic`. See [venues/chapel-of-bones.md](venues/chapel-of-bones.md) for format, ID conventions, non-live-music event types, and scrape/diff commands.

#### Neptune's Parlour (`neptunes-id`)
**URL:** `https://www.neptunesraleigh.com/events` — Squarespace, renders in plain HTML. Use `get_page_text` to read the listing. Extract event slugs from the DOM with `javascript_tool` (`a[href*="/events/"]`). Titles use `//` as multi-act separator — pre-split before writing raw JSON. Use `scrape generic`.

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/neptunes_raw.json --out .tmp/scraped_neptunes.json
python3 pipeline/cli.py diff neptunes-id .tmp/scraped_neptunes.json --report .tmp/neptunes_changes.md
```

#### Slim's (`slims-id`)
**URL:** `https://slimsraleigh.com/` — plain HTML; use `scrape generic`. Fetch monthly calendar pages (`/calendar/YYYY-MM/`) for the full lookahead window. Skip "Open Jam" and "Mingle @ Slim's" entries.

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/slims_raw.json --out .tmp/scraped_slims.json
```

#### Stanczyks (`stanczyks-id`)
**URL:** `https://www.stanczyksdurham.com/#/events` — JS-rendered SPA. Use `javascript_tool` to extract event data from the DOM, then write to raw JSON and use `scrape generic`.

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/stanczyks_raw.json --out .tmp/scraped_stanczyks.json
python3 pipeline/cli.py diff stanczyks-id .tmp/scraped_stanczyks.json --report .tmp/stanczyks_changes.md
```

#### Plain-HTML venues (no special handling)
- **Lincoln Theatre** `https://lincolntheatre.com/events/`
- **Local 506** `https://local506.com/events/`
- **Motorco** `https://motorcomusic.com/`
- **The Pinhook** `https://thepinhook.com/events/`
- **The Fruit** `https://www.durhamfruit.com/`
- **Sharp 9 Gallery** `https://www.durhamjazzworkshop.org/`

For plain-HTML venues, Claude reads the page (via `WebFetch` or `get_page_text`), extracts events, and writes a simple raw JSON file. The generic scraper then handles all deterministic normalization: computing datetimes, deriving doors time, running `is_live_music` detection and artist parsing, filtering the lookahead window, and producing the full event schema.

**You write the raw JSON. The scraper computes the rest.**

#### Generic scraper: raw input format

`.tmp/<venue_key>_raw.json` — a JSON array of objects:

```json
{
  "slug":      "event-url-slug",          // URL path segment → event id. Required.
  "title":     "Headliner Name",          // Pre-split by you. Required.
  "subtitle":  "with Supporting Act",     // Pre-split by you. "" if none.
  "presenter": "Promoter Presents",       // "" if none.
  "date":      "2026-04-18",              // YYYY-MM-DD. Required.
  "show_time": "20:00",                   // HH:MM 24-hour. Required.
  "end_time":  "22:00",                   // HH:MM 24-hour. Optional — defaults to show_time + 2h.
  "admission": "$10",                     // "" if unknown.
  "url":       "https://venue.com/events/slug"  // Full event URL. Required.
}
```

**Important:** `title` and `subtitle` must be **pre-split by you** before writing. The scraper passes them through as-is — it does not parse raw title strings. Apply the `//`, `w/`, and `,` splitting rules from the Scraper Fragility Notes above.

**What the scraper computes automatically (not input fields):**
- `doors` / `doors_datetime` — always `show_time − 1 hour`. **This is often wrong** — many venues post doors separately (e.g. `DOORS 7PM // SHOW 7:30PM`). Always capture the explicit doors time when shown and patch `doors` and `doors_datetime` in the scraped output before running `diff`. A future improvement would add an optional `doors_time` raw field to override the default.
- `is_live_music` — keyword-detected from title/subtitle. **Always review and correct before `diff`.**
- `artists` — parsed from title/subtitle. **Always review and fix before `diff`.**
- `date_str`, `start_datetime`, `end_datetime` — computed from `date` + `show_time` + `end_time`.
- Events outside `today … today+days` are filtered out automatically.

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/<venue_key>_raw.json \
                                       --out .tmp/scraped_<venue_key>.json \
                                       [--days 90]
```

---

### Scraper Fragility Notes

Title splitting is handled automatically by per-venue scrapers (Kings, Cat's Cradle). For venues using `scrape generic` (including Chapel of Bones), **you** must pre-split titles before writing the raw JSON. Either way, these patterns apply (in priority order):
1. ` / ` → co-headliners: `"A / B"` → title=`"A"`, subtitle=`"with B"`
2. ` w/ ` → support acts: `"A w/ B, C"` → title=`"A"`, subtitle=`"with B, C"`
3. `, ` → multiple acts (if all parts ≤ 6 words): `"A, B, C"` → title=`"A"`, subtitle=`"with B, C"`

**Known failure modes to watch for:**
- **Non-standard presenters**: `"An evening with X"`, `"Hosted by Y"` prefixes won't be stripped automatically — clean from the raw JSON before scraping.
- **"w/ X, Y" comma mangling**: Fixed in scraper (w/ checked before commas), but verify output for multi-support events.
- **Recurring series names**: `"Rock Roulette"`, `"Songwriter Showcase"` etc. are not artist names — set `artists: []` and verify `is_live_music`.

After running the scraper, **always check the output** for these cases before running `diff`.

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

**3c — New artists**
Verify new artists are in each event's `artists` array with correct names and roles. Do **not** perform manual web searches for Spotify/Bandcamp/YouTube/Instagram — `enrich_genres.py` handles link and genre enrichment automatically via the Spotify API. It runs after all `set` calls in Step 5.

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

**Content hash normalization:** `content_hash` normalizes text before hashing (NFKC, Unicode quote/dash folding, ordinal suffix stripping, casefold, whitespace collapse). This prevents curly-vs-straight quotes, en-dash/em-dash, ordinal suffixes (`17th` vs `17`), and case differences from appearing as spurious changes.

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

After all `set` calls, run repair and prune, then kick off genre enrichment in the background:
```bash
python3 pipeline/cli.py repair
python3 pipeline/cli.py prune --days 30
python3 pipeline/enrich_genres.py &
```

`enrich_genres.py` fetches Spotify genres and Bandcamp tags for any artists lacking enrichment. It can take several minutes for large batches — always run it with `&` so it doesn't block the upload step. It is safe to run after every scrape — it skips artists enriched within the last 30 days. If it exits with "quota exhausted", just re-run it later; the Spotify rate limit resets on a rolling 30-second window and large Retry-After values (~86400s) are a known API quirk meaning "back off now", not a true 24-hour ban.

**Temp file cleanup:** Delete `.tmp/scraped_<venue_key>.json` and `.tmp/events/` after saving. Keep `.tmp/<venue_key>_changes.md` (the diff report) — do not delete it.

---

## Step 6: Upload updated data and report results

After saving state, push the updated JSON to R2 so the live site reflects the new events:

```bash
python3 pipeline/cli.py upload
```

This pushes `live_music_events.json`, `artists_db.json`, and `venues_db.json` to R2.

---

## Step 7: Post-run analysis

After each run, write a brief log covering:

**Summary counts:**
```
Venue processed: [Venue Name]
Lookahead: [N] days (today through [date])
New events added: [N]
Events updated: [N]
Unchanged (skipped): [N]
Possibly removed (not deleted): [N]
State file saved and uploaded.
```

**Issues and friction encountered:** Document anything that required manual intervention or workarounds:
- Did any JS extraction selectors fail or return 0 events? What was the fix?
- Did the scraper mangle any title/subtitle splits? Which events, how were they fixed?
- Were any `is_live_music` flags or artist arrays wrong and corrected?
- Were any prices missing or hard to find?
- Any site structure changes since last scrape?

**Recommendations for next scrape:** Based on the issues above, what should be improved before the next run of this venue?
- Selector updates needed in notes.md?
- Scraper logic that needs fixing?
- Venue-specific edge cases to add to this skill?

This log should be frank and actionable — the goal is to make each subsequent scrape faster and less manual than the one before.

---

## Success criteria

- Exactly one venue processed per run
- All new/changed events within the lookahead window are saved to state
- State file saved with updated `content_hash` and `last_updated`
- Updated data uploaded to R2 (`python3 pipeline/cli.py upload`)
- No duplicates created on re-runs
- Unchanged events trigger zero state writes
- Post-run analysis written

---

For the full CLI command reference, see [reference.md](reference.md).
