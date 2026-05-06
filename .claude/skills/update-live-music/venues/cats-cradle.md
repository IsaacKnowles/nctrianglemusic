# Cat's Cradle — Scraping Notes

**URL:** https://catscradle.com/events/
**Event ID Tags:** `cats-cradle-id` (Main Stage), `cats-cradle-br-id` (Back Room)

## Site Quirks

Two rooms tracked separately. The events listing page does **not** show ticket prices —
prices are only on individual event pages. The scraper fetches each event's detail page
automatically (0.3s polite delay). Use `--no-fetch` to skip this (faster, empty admission).

**Pricing note (2026-04-25):** Individual event pages use an Etix JS widget. The urllib-based
scraper fetch returns empty admission for most events because prices aren't in the server-rendered
HTML. Only events with static price text (e.g. Carrboro Bluegrass Festival: `$85`) are found.
To get prices you'd need to navigate to each event page via the browser — not practical for
bulk runs. Leave admission blank and note in the run report.

**Site redesign (2026-04-25):** The site now uses "Rockhouse Partners / Etix" theme instead of
The Events Calendar plugin. Use the selectors below. The old `.tribe-*` selectors no longer work.

Time strings are in the format `"Doors: 7 pm : Show: 8 pm"` — extract the show time only
for the `time` field when writing raw JSON; the scraper will compute `doors = show - 1hr`.
Many events have non-standard door/show gaps (e.g. doors 7:30, show 8), but there's no
`doors_time` field in the raw format, so these will be slightly wrong in `doors_datetime`.

## Extraction (Step 1)

Navigate to `https://catscradle.com/events/` and run in the browser console:

```javascript
const events = Array.from(document.querySelectorAll('.rhpSingleEvent')).map(el => {
  const url = el.querySelector('a#eventTitle, .rhp-event-thumb a.url')?.href || '';
  const titleRaw = el.querySelector('.eventTitleDiv h2')?.textContent.trim() || '';
  const subtitleRaw = el.querySelector('.eventSubHeader')?.textContent.trim() || '';
  const dateRaw = el.querySelector('.singleEventDate')?.textContent.trim() || '';
  const timeRaw = el.querySelector('.rhp-event__time-text--list')?.textContent.trim() || '';
  const room = el.querySelector('.venueLink')?.textContent.trim() || '';
  // Combine title + support act; extract show time only
  const title = subtitleRaw ? `${titleRaw} w/ ${subtitleRaw}` : titleRaw;
  const showMatch = timeRaw.match(/show[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm))/i);
  const simpleMatch = timeRaw.match(/(\d{1,2}(?::\d{2})?\s*(?:am|pm))/i);
  const time = showMatch ? showMatch[1].trim() : (simpleMatch ? simpleMatch[1].trim() : '');
  return { title, url, date: dateRaw, time, room };
});
JSON.stringify(events)
```

Save output to `.tmp/cats_cradle_raw.json`.

**Pre-processing before writing raw JSON:**
- Strip tour suffixes: `"Artist – Tour Name w/ Support"` → `"Artist w/ Support"`
- Strip event descriptors: `"An Evening with X"` → `"X"`, `"X: Tour Name"` → `"X"`
- Watch for comma-split collisions: titles like `"A w/ B, C"` will split on `,` before `w/` —
  the comma check runs first if all parts are ≤ 6 words. Verify in scraped output.
- Event names that are not artist names (festivals, benefit shows): set `artists: []` in patch step.
- The word `"club"` in a title suppresses the comma-split (e.g. "Arts Fishing Club" stays intact).

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape cats-cradle
# Skip per-page price fetching (faster):
python3 pipeline/cli.py scrape cats-cradle --no-fetch
```

Outputs two files:
- `.tmp/scraped_cats-cradle.json` (Main Stage)
- `.tmp/scraped_cats-cradle-back-room.json` (Back Room)

## Diff / Set

Run diff + set for **each room separately**:

```bash
python3 pipeline/cli.py diff cats-cradle-id .tmp/scraped_cats-cradle.json \
  --report .tmp/cats-cradle_changes.md

python3 pipeline/cli.py diff cats-cradle-br-id .tmp/scraped_cats-cradle-back-room.json \
  --report .tmp/cats-cradle-back-room_changes.md
```
