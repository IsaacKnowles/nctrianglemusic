# Kings — Scraping Notes

**URL:** https://www.kingsraleigh.com/ (homepage — `/shows` renders empty)
**Event ID Tag:** `kings-id`

## Extraction

`WebFetch` the homepage. Event data is server-rendered. The page has two representations
of each event — use the **email-template section** (it has all fields including price):

```html
<a href="https://www.kingsraleigh.com/shows/<slug>">
  <p class="date">Thursday, April 2nd, 2026</p>
  <h3>Scarhaven</h3>
  <h4> with Honeyknife, Sub Empty</h4>
  <p><strong>Time:</strong> 8:00PM</p>
  <p><strong>Admission:</strong> $15 adv / $18 day-of</p>
  <p><strong>Doors:</strong> 7:00PM</p>
</a>
```

Parse all events within the lookahead window and write to `.tmp/kings_raw.json`:

```json
[
  { "title": "Scarhaven w/ Honeyknife, Sub Empty", "date": "Thursday, April 2nd, 2026",
    "time": "8:00PM", "price": "$15 adv / $18 day-of",
    "url": "https://www.kingsraleigh.com/shows/scarhaven" }
]
```

## Normalization / Diff

```bash
python3 pipeline/cli.py scrape kings
python3 pipeline/cli.py diff kings-id .tmp/scraped_kings.json --report .tmp/kings_changes.md
```
