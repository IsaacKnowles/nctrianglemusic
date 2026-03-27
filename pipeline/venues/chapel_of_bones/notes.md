# Chapel of Bones — Scraping Notes

**URL:** https://chapelofbones.com/events/
**Event ID Tag:** `chapel-of-bones-id`

## Site Quirks

Uses an embedded **TickPick widget** — there are no individual event pages on the venue's
own site. All event data comes from the widget DOM. Prices include a TickPick service fee
(~14.3%); the scraper strips this automatically from fractional-cent prices.

## Extraction (Step 1)

Navigate to `https://chapelofbones.com/events/` and run in the browser console:

```javascript
const items = Array.from(document.querySelectorAll('.eventGridItem_b9cc1'));
const raw = items.map(item => ({
  title: item.querySelector('.eventTitle_eacac')?.textContent.trim() || '',
  dateLocation: item.querySelector('.eventLocation_0f1cb')?.textContent.trim() || '',
  price: item.querySelector('.eventPriceButton_b33bd')?.textContent.trim() || ''
}));
JSON.stringify(raw)
```

Save output to `.tmp/chapel_of_bones_raw.json`.

> TickPick class names may change. If 0 events, inspect the widget DOM and update selectors.

## Normalization (Step 2)

```bash
python3 pipeline/cli.py scrape chapel-of-bones
# or with overrides:
python3 pipeline/cli.py scrape chapel-of-bones --raw .tmp/chapel_of_bones_raw.json --out .tmp/scraped_chapel-of-bones.json
```

## Diff / Set

```bash
python3 pipeline/cli.py diff chapel-of-bones-id .tmp/scraped_chapel-of-bones.json \
  --report .tmp/chapel-of-bones_changes.md
```
