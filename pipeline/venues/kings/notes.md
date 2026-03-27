# Kings — Scraping Notes

**URL:** https://www.kingsraleigh.com/
**Events URL:** https://www.kingsraleigh.com/ (homepage — `/shows` renders empty)
**Event ID Tag:** `kings-id`

## Site Quirks

JS-rendered. The `/shows` page is empty — all events are on the **homepage**.
Individual show pages are also JS-rendered; extract all event data from the homepage in one JS call.

## Extraction (Step 1)

Navigate to `https://www.kingsraleigh.com/` and run in the browser console (or via `javascript_tool`):

```javascript
JSON.stringify(Array.from(document.querySelectorAll('[class*="show"], [class*="event"], article'))
  .map(el => ({
    title: el.querySelector('[class*="title"], h2, h3')?.textContent.trim() || '',
    date:  el.querySelector('[class*="date"], time')?.textContent.trim() || '',
    time:  el.querySelector('[class*="time"]')?.textContent.trim() || '',
    price: el.querySelector('[class*="price"], [class*="ticket"]')?.textContent.trim() || '',
    url:   el.querySelector('a[href*="/shows/"]')?.href || ''
  })).filter(e => e.title && e.url))
```

Save output to `.tmp/kings_raw.json`.

> Selectors are best-effort — verify output before saving. Warn if 0 events returned.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape kings
# or with overrides:
python3 pipeline/cli.py scrape kings --raw .tmp/kings_raw.json --out .tmp/scraped_kings.json --days 90
```

## Diff / Set

```bash
python3 pipeline/cli.py diff kings-id .tmp/scraped_kings.json --report .tmp/kings_changes.md
```
