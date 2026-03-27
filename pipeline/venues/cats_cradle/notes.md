# Cat's Cradle — Scraping Notes

**URL:** https://catscradle.com/events/
**Event ID Tags:** `cats-cradle-id` (Main Stage), `cats-cradle-br-id` (Back Room)

## Site Quirks

Two rooms tracked separately. The events listing page does **not** show ticket prices —
prices are only on individual event pages. The scraper fetches each event's detail page
automatically (0.3s polite delay). Use `--no-fetch` to skip this (faster, empty admission).

The Events Calendar plugin changes class names periodically. If 0 events are returned,
inspect the DOM and adjust selectors.

## Extraction (Step 1)

Navigate to `https://catscradle.com/events/` and run in the browser console:

```javascript
JSON.stringify(
  Array.from(document.querySelectorAll('.tribe-events-calendar-list__event-article, article.type-tribe_events, .tribe-event'))
    .map(el => ({
      title:    el.querySelector('.tribe-event-url, .tribe-events-calendar-list__event-title a, h2 a, h3 a')?.textContent.trim() || '',
      url:      el.querySelector('.tribe-event-url, .tribe-events-calendar-list__event-title a, h2 a, h3 a')?.href || '',
      date:     el.querySelector('.tribe-event-date-start, time, .tribe-events-start-datetime')?.textContent.trim() || '',
      time:     el.querySelector('.tribe-events-start-time, .tribe-event-time')?.textContent.trim() || '',
      room:     el.querySelector('.tribe-venue-location, .tribe-venue, .tribe-events-calendar-list__event-venue')?.textContent.trim() || '',
    }))
    .filter(e => e.title && e.url)
)
```

**Fallback selector (if 0 events):**
```javascript
JSON.stringify(
  Array.from(document.querySelectorAll('h2 a[href*="/event/"], h3 a[href*="/event/"]'))
    .map(a => ({
      title: a.textContent.trim(),
      url:   a.href,
      date:  a.closest('article, li, div')?.querySelector('time, [class*="date"]')?.textContent.trim() || '',
      time:  a.closest('article, li, div')?.querySelector('[class*="time"]')?.textContent.trim() || '',
      room:  a.closest('article, li, div')?.querySelector('[class*="venue"], [class*="location"]')?.textContent.trim() || '',
    }))
    .filter(e => e.title)
)
```

Save output to `.tmp/cats_cradle_raw.json`.

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
