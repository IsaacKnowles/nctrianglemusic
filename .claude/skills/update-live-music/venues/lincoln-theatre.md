# Lincoln Theatre — Scraping Notes

**URL:** `https://lincolntheatre.com/events/`
**Event ID Tag:** `lincoln-id`

## Site Quirks

**Do NOT use `WebFetch` for this venue.** The events are JavaScript-rendered (custom `rhp-events` plugin). WebFetch returns an incomplete HTML snapshot that silently truncates to ~21 events — no error, no warning. A full calendar season (50+ events) will be silently missed.

Always use the **Chrome browser plugin** (`javascript_tool`) to extract events from the live DOM.

**Slug drift:** Lincoln Theatre updates event slugs as details are confirmed — e.g. `harvey-street-w-tba` becomes `harvey-street-w-the-wallabies` once support is announced. This means every scrape will produce a handful of `possibly_removed` orphans (old slugs) alongside new entries with the updated slugs. This is expected behavior, not a bug. The old slugs will stay in state until `prune` cleans them up.

**Pricing:** The listing page shows per-tier prices inline (e.g. ADVANCED, GA Balcony). Capture the full price block — it's richer than what's on the individual event pages.

## Extraction (Step 1)

Navigate to `https://lincolntheatre.com/events/` in Chrome, wait for the page to fully render, then run:

```javascript
JSON.stringify((() => {
  const seen = new Set();
  const events = [];
  document.querySelectorAll('[class*="rhp-event__"]').forEach(block => {
    const link = block.querySelector('a[href*="/event/"]');
    if (!link) return;
    const slug = link.href.match(/\/event\/([^/]+)\//)?.[1];
    if (!slug || seen.has(slug)) return;
    seen.add(slug);

    const container = block.closest('[class*="eventItem"], .rhp-events-loop__item') || block;
    const dateEl = container.querySelector('[class*="eventDateListTop"]');
    const titleEl = block.querySelector('h2, h3, h4, [class*="eventTitle"], [class*="title"]');
    const timeEl = block.querySelector('[class*="eventTime"], [class*="time"], [class*="schedule"]');
    const priceEl = block.querySelector('[class*="price"], [class*="ticket"]');
    // Grab all price lines (multi-tier)
    const priceLines = Array.from(block.querySelectorAll('[class*="price"], [class*="ticket"]'))
      .map(el => el.innerText.trim()).filter(Boolean).join(' | ');

    events.push({
      slug,
      date_raw: dateEl?.innerText.trim() || '',
      title: titleEl?.innerText.trim() || link.innerText.trim(),
      time_raw: timeEl?.innerText.trim() || '',
      admission: priceLines,
      url: link.href.replace(/\/(lincoln-theatre|raleigh-north-carolina)\/$/, '/').replace(/\/$/, '/'),
    });
  });
  return events;
})())
```

Save output to `.tmp/lincoln_theatre_raw_dom.json`. Then write `.tmp/lincoln-theatre_raw.json` applying the usual title-splitting and normalization rules (the snippet returns raw site titles — pre-split `w/`, `;`, `//`, `,` before writing).

**Date parsing:** The site returns dates like `"FRI, APR 17"` — resolve to full `YYYY-MM-DD` using the current year (or next year if the month has already passed).

**Time parsing:** Time fields show `"Doors: 7:30 pm // Show: 8:30 pm"` format. Extract show time for `show_time` and doors time for patching `doors`/`doors_datetime` in the scraped output.

## Normalization / Diff

```bash
python3 pipeline/cli.py scrape generic --raw .tmp/lincoln-theatre_raw.json \
                                       --out .tmp/scraped_lincoln-theatre.json \
                                       --days 90

python3 pipeline/cli.py diff lincoln-id .tmp/scraped_lincoln-theatre.json \
  --report .tmp/lincoln-theatre_changes.md
```

## Known non-live-music events

Flag these as `is_live_music: false` and clear `artists`:
- Film screenings (e.g. "A Love Letter to Handsome John — Screening")
- "Anthem of the Sundays" recurring series (check each occurrence — sometimes no named performers)

Tribute bands (e.g. Trial By Fire, Bearly Dead, Disciple of the Garden) are `is_live_music: true`.
