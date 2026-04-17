# Chapel of Bones — Scraping Notes

**URL:** https://chapelofbones.com/events/
**Event ID Tag:** `chapel-of-bones-id`

## Site Quirks

Uses an embedded **TickPick widget** (`TickPickWidgets.createEventsWidget({companyId: 'chapel-of-bones', ...})`) —
there are no individual event pages on the venue's own site. The widget renders into an **iframe**
so `javascript_tool` cannot access its DOM directly (innerHTML returns `[BLOCKED: Cookie/query string data]`).

Instead, use **`get_page_text`** — it extracts the rendered event text from the page. The widget
renders all visible events as plain text. A **"Show more" button** exists; click it before reading to
get all events.

Prices include a TickPick service fee (~14.3%), which produces fractional-cent values like `$22.86`,
`$28.57` etc. Keep these as-is — they're the accurate prices shown to buyers.

## Extraction (Step 1)

Navigate to `https://chapelofbones.com/events/`, click the "Show more" button (loads additional events),
then use `get_page_text` to read the page. Events appear in this format:

```
$22.86ASG / Valletta / Napalm CruiserFri Apr 17 @ 7 pm • Chapel of Bones, Raleigh, NC
$32Uada / Mortiis / Rome / Wraith Knight Fri May 1 @ 7 pm • Chapel of Bones, Raleigh, NC
Free Monthly Pop Shop ARTernative MarketSun May 3 @ 10 am • Chapel of Bones, Raleigh, NC
```

Parse each line manually: price, title (with ` / ` separators for multi-act shows), date+time.
Pre-split titles using ` / ` before writing raw JSON (scraper doesn't split titles).

## ID Convention

IDs use `<slugified-title>-<mon><day>` format with **zero-padded single-digit days**:
- `uada-may01` (not `uada-may1`)
- `conjurer-jun05` (not `conjurer-jun5`)
- Double-digit days are not padded: `apr18`, `may11`

For `(Hed)p.e.`: slug is `hedpe` (strip parens and dots), giving ID `hedpe-may07`.

## Normalization (Step 2)

Write events to `.tmp/chapel_raw.json` in the generic scraper format, then:

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/chapel_raw.json --out .tmp/scraped_chapel.json
python3 pipeline/cli.py diff chapel-of-bones-id .tmp/scraped_chapel.json --report .tmp/chapel_changes.md
```

## Classification Notes

Chapel of Bones runs many non-concert events alongside shows. The global `is_live_music` detector
catches most (karaoke, yoga, market, burlesque, book club, giveaway). Review the detector output
carefully — themed party nights and DJ-only events may slip through and need manual correction.

For events where the title is a recurring series name (e.g. "Wasteland", "Necromancy Goth Night"),
the series name is **not** an artist — use subtitle performers as artists, or `artists: []` if none.
