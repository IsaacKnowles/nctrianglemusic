# Motorco Music Hall (`motorco-id`)

**URL:** `https://motorcomusic.com/`
**Ticketing:** Tickera (self-hosted) — prices available on each event's detail page via WebFetch.

The homepage is **JavaScript-rendered** — `WebFetch` returns CSS/structure only, no event data. Use `javascript_tool` via Chrome instead. Individual event pages (`/event/<slug>/`) are server-rendered and work fine with `WebFetch` for pricing.

## Extraction (Step 1)

Navigate to `https://motorcomusic.com/` in Chrome and run in the console:

```javascript
const MONTHS = {Jan:1,Feb:2,Mar:3,Apr:4,May:5,Jun:6,Jul:7,Aug:8,Sep:9,Oct:10,Nov:11,Dec:12};
function parseDate(ds) {
  const m = ds.match(/(\w+) (\d+), (\d{4})/);
  if (!m) return null;
  const mon = MONTHS[m[1].substring(0,3)];
  return `${m[3]}-${String(mon).padStart(2,'0')}-${String(m[2]).padStart(2,'0')}`;
}
function parseTime(ts) {
  const m = ts.match(/(\d+):(\d{2})\s*(am|pm)/i);
  if (!m) return '20:00';
  let h = parseInt(m[1]), mn = m[2], ap = m[3].toLowerCase();
  if (ap === 'pm' && h !== 12) h += 12;
  if (ap === 'am' && h === 12) h = 0;
  return `${String(h).padStart(2,'0')}:${mn}`;
}

const sections = Array.from(document.querySelectorAll('section')).filter(s => s.querySelector('a[href*="/event/"]'));
const events = sections.map(s => {
  // Title is in the second <a> — first link is the image (empty text)
  const titleLink = Array.from(s.querySelectorAll('a[href*="/event/"]'))
    .find(a => a.textContent.trim() && !a.textContent.trim().includes('TICKETS'));
  const url = titleLink?.href || '';
  const slug = url.replace(/\/$/, '').split('/').pop();
  const titleRaw = titleLink?.textContent.trim() || '';
  const allText = s.textContent.replace(/\s+/g, ' ').trim();
  const dateTimeMatch = allText.match(/(\w{3} \w+ \d+, \d{4})\s+(\d{1,2}:\d{2} [ap]m)/i);
  const dateStr = dateTimeMatch?.[1] || '';
  const timeStr = dateTimeMatch?.[2] || '';
  const afterDateTime = allText.replace(/^\w{3} \w+ \d+, \d{4}\s+\d{1,2}:\d{2} [ap]m\s+/i, '');
  const presenterMatch = afterDateTime.match(/^(.+?(?:Presents?|PRESENTS?))\s+/i);
  const presenter = presenterMatch?.[1]?.trim() || '';
  const withMatch = allText.match(/\bwith\s+(.+?)(?:\s*TICKETS|$)/i);
  const subtitleRaw = withMatch?.[1]?.trim() || '';
  return { slug, url, titleRaw, subtitleRaw, presenter,
           date: parseDate(dateStr), show_time: parseTime(timeStr) };
});
JSON.stringify(events)
```

Save output to `.tmp/motorco_raw.json`.

**DOM structure (as of 2026-05):**
- Each event lives in a `<section>` containing `a[href*="/event/"]`
- First `<a>` is the image link (empty text) — **skip it**; title is in the second `<a>`
- Date + time appear at the start of the section's text content: `"Wed May 6, 2026 7:30 pm"`
- Presenter appears after date/time and ends with "Presents" (e.g. `"andmoreagain Presents"`)
- Support acts appear after "with " in the text, before "TICKETS"

## Pre-processing before writing raw JSON

- **Strip tour suffixes from titles:** `"YOT CLUB : SIMPLETON TOUR"` → title `"YOT CLUB"`, `"BELMONT – Performing 10 Years of ..."` → title `"BELMONT"`
- **Split ` / ` in `subtitleRaw`** (support acts): `"REMO DRIVE / RESTRAINING ORDER / PICTURES OF VERNON"` → `"with REMO DRIVE, RESTRAINING ORDER, PICTURES OF VERNON"`
- **Presenter without "Presents":** Some listings (e.g. `"Cat's Cradle JOHN R. MILLER"`) show presenter name without the word "Presents" — the extractor's presenter regex will return `""`. Set manually if you can tell from the listing.
- **False subtitle matches from "with" in titles:** Event titles like `"CURFEW CLUB : A Dance Party for Babes with a Bedtime"` cause the `with` regex to extract `"a Bedtime"` as a subtitle. Clear these before writing the raw JSON (set `subtitleRaw: ""`).

## Pricing (Step 1, continued)

Individual event pages are server-rendered. Use `WebFetch` on each `/event/<slug>/` URL:

```
Ticket Type Price Qty. Cart
EVENT NAME - Advance $XX.XX
```

Motorco uses Tickera. Prices include all fees; NC sales tax added at checkout.
- Most shows list only an advance price; day-of pricing appears as `"- Day Of $XX.XX"` on the show date itself.
- VIP / Fast Track tiers appear for some shows alongside the GA advance price — record the GA advance price as admission.
- If the event links out to Eventbrite instead of using Tickera, the Motorco event page won't show a price — leave `admission: ""`.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/motorco_raw.json \
                                       --out .tmp/scraped_motorco.json \
                                       [--days 90]
```

## Post-scrape review (Step 3)

**Always check after scraping:**

1. **`&` in band names** — the scraper can split `"HOUSE & HOME"` into `["HOUSE", "HOME"]` or `"NATHAN ARIZONA & THE NEW MEXICANS"` into two entries. Check the `artists` array for any band whose name contains `&` and merge if split.

2. **`is_live_music` on dance/theme nights** — Motorco hosts many recurring dance parties that the scraper incorrectly marks `true`. Mark the following types `false` and set `artists: []`:
   - Named dance parties / club nights: `"Hot in Herre"`, `"GOODIES : 2000S HIP HOP NITE"`, `"One Direction Night"`, `"DRIZZY'S ROOM : DRAKE NIGHT"`, `"CRASH THE COTTAGE"`, etc.
   - Food/non-music events on the Veranda or Parts & Labor (e.g. "Veggie Lovers Grill Out")
   - Singalong dance parties (e.g. "Boogie Down Broadway")
   - Bad Bunny / themed DJ nights

3. **Title `: Tour Name`** — strip tour/edition suffixes from headliner names.

## Diff and save

```bash
python3 pipeline/cli.py diff motorco-id .tmp/scraped_motorco.json --report .tmp/motorco_changes.md
```
