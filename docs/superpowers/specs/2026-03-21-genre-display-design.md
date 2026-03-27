# Genre Display on Event Cards

**Date:** 2026-03-21
**Repo:** triangle-live-music-site
**Branch:** Cut from `seo-and-time-block-polish`. That branch contains SEO meta, time block alignment polish, and this design doc — none of which have been merged to `main` yet. The genre feature builds on top of it.

---

## Summary

Add genre display to event cards on the Triangle Live Music site. Genre data lives in `artists_db.json` in the data pipeline repo. This feature surfaces it on the frontend without modifying the data pipeline — keeping backend and frontend work decoupled.

---

## Scope

- **In scope:** Worker changes to inject a genre map, frontend card rendering of genre chips, genre included in text search
- **Out of scope:** Artist enrichment (handled separately in the data pipeline repo), genre filter chips, any changes to `live_music_events.json` schema or the CLI

---

## Architecture

### Data Flow

1. Worker fetches `live_music_events.json` and `artists_db.json` from R2 in parallel via `Promise.all()`
2. Worker builds a slim `{ slug: string[] }` genre map — only entries with a non-empty `genre` array
3. Both `window.__EVENTS__` and `window.__GENRES__` are injected into the HTML in a single `<script>` block
4. Frontend resolves genres per event using artist slugs: once in the search path, once in card rendering

### Payload size

- Current genre map (77 enriched artists): ~3.8KB (~50 bytes per entry: slug + 2 genre strings + JSON punctuation)
- Projected at full enrichment (~800 artists, avg 2 genres): ~25–30KB
- No performance concern relative to the existing 543KB events payload

### Worker fallback

If `artists_db.json` is missing or the R2 fetch fails, `window.__GENRES__` falls back to `{}`. The existing 503 guard for `live_music_events.json` is retained. Site remains fully functional; genre chips are simply absent.

### Deployment consistency

The Worker sets `Cache-Control: no-cache`, so Worker and HTML are always served as a matched pair. No stale-HTML / new-Worker mismatch risk.

### Local dev

Two local dev paths exist:

1. **`wrangler dev --remote`** — fetches from R2 and injects both globals correctly. Genres work.
2. **Without `--remote`** — `window.__EVENTS__` is `undefined`, so `loadData()` falls back to `fetch('./live_music_events.json')` from disk. `window.__GENRES__` is also `undefined`. `resolveGenres` handles this via optional-chaining (`window.__GENRES__?.[slug]`) — no genre chips shown, no errors.

---

## Worker Changes (`worker.js`)

Replace the existing single fetch with a parallel fetch. Preserve the existing 503 guard for `eventsObj`:

```js
const [eventsObj, artistsObj] = await Promise.all([
  env.DATA_BUCKET.get('live_music_events.json'),
  env.DATA_BUCKET.get('artists_db.json'),
]);

if (!eventsObj) return new Response('Data unavailable', { status: 503 });

const eventsJson = await eventsObj.text();

let genreMap = {};
if (artistsObj) {
  const artists = JSON.parse(await artistsObj.text());
  for (const [slug, data] of Object.entries(artists)) {
    if (data.genre?.length) genreMap[slug] = data.genre;
  }
}

const injected = indexHtml.replace(
  '<head>',
  `<head>\n<script>window.__EVENTS__=${eventsJson};window.__GENRES__=${JSON.stringify(genreMap)};</script>`
);
```

Note: both `eventsJson` and `JSON.stringify(genreMap)` are injected into a `<script>` block using the same strategy as the existing code. A value containing `</script>` would break HTML parsing. This is a pre-existing limitation of the injection approach and is out of scope for this feature.

---

## Frontend Changes (`index.html`)

### Genre merge function

```js
function resolveGenres(artists) {
  const seen = new Set();
  const result = [];
  const ordered = [
    ...artists.filter(a => a.role === 'headliner'),
    ...artists.filter(a => a.role !== 'headliner'),
  ];
  for (const a of ordered) {
    for (const g of (window.__GENRES__?.[a.slug] || [])) {
      if (!seen.has(g) && result.length < 3) {
        seen.add(g);
        result.push(g);
      }
    }
  }
  return result;
}
```

- Headliner genres come first
- Support act genres fill remaining slots (up to 3 total)
- Deduplication across all artists
- Returns `[]` when `artists` is empty, missing, or no genre data is available

`resolveGenres` is called separately in two places (search and rendering). This is intentional — simplicity over caching. Both call sites use the same input (`e.artists || []`) and produce the same result, so they cannot diverge.

### Text search

`resolveGenres` is called inside the `if (searchQuery)` guard in `getFilteredEvents()`, consistent with how the rest of the haystack is built:

```js
if (searchQuery) {
  const genres = resolveGenres(e.artists || []);
  const hay = [e.title, e.subtitle, e.presenter, e.venueName, ...genres].join(' ').toLowerCase();
  if (!hay.includes(searchQuery)) return false;
}
```

### Card rendering

`resolveGenres(e.artists || [])` is called inside `renderCard(e)`. When non-empty, render a `.genre-tags` wrapper with `.genre-chip` spans. When empty, emit nothing — no wrapper, no empty space:

```js
const genres = resolveGenres(e.artists || []);
const genreHtml = genres.length
  ? `<div class="genre-tags">${genres.map(g => `<span class="genre-chip">${esc(g)}</span>`).join('')}</div>`
  : '';
```

Uses the existing `esc()` helper already present in `index.html`.

**Position in `.event-body`:** Genre chips are inserted after the presenter line and before the admission line. The numbered list below describes only the children of `.event-body` (the time block, venue bar, and outer card wrapper are outside this scope):

1. Venue badge (`event-top`)
2. Title (with optional link)
3. Subtitle
4. Presenter (`event-meta`)
5. **Genre chips** (`.genre-tags`) ← new
6. Admission
7. Music links

---

## Styling

```css
.genre-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.genre-chip {
  font-size: 11px;
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
  white-space: nowrap;
}
```

- No color coding — genres are not venue-specific
- Consistent with existing card metadata density

---

## Testing Checklist

- [ ] Events with genre data show correct chips (headliner-biased, max 3)
- [ ] Events without genre data show no `.genre-tags` element and no empty space
- [ ] Multi-artist events deduplicate genres across the bill
- [ ] Text search for a genre term (e.g. "punk", "jazz") returns matching events
- [ ] Site loads and functions normally when `artists_db.json` is absent from R2 (`window.__GENRES__` = `{}`)
- [ ] Site loads and functions normally via `wrangler dev --remote` with `artists_db.json` present
- [ ] Site loads and functions normally in local dev without `--remote` (`window.__EVENTS__` and `window.__GENRES__` both `undefined`, data loaded from disk)
