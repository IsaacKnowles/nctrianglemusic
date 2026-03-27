# Genre Display on Event Cards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface artist genre tags on event cards and in text search, pulling genre data from `artists_db.json` via the Cloudflare Worker.

**Architecture:** The Worker fetches `live_music_events.json` and `artists_db.json` in parallel from R2, builds a slim `{ slug: string[] }` genre map, and injects it as `window.__GENRES__`. The frontend resolves genres per event at render time using artist slugs, renders up to 3 genre chips (headliner-biased), and includes genres in the text search haystack.

**Tech Stack:** Cloudflare Workers (ES modules), vanilla JS, inline CSS in a single `index.html`.

**Spec:** `docs/superpowers/specs/2026-03-21-genre-display-design.md`

---

## File Map

| File | Change |
|------|--------|
| `worker.js` | Replace single R2 fetch with parallel fetch; inject `window.__GENRES__` |
| `index.html:497` | Add `.genre-tags` and `.genre-chip` CSS after `.event-admission` rule |
| `index.html:982` | Add `resolveGenres()` function before `renderCard` |
| `index.html:983–1024` | Update `renderCard` to call `resolveGenres` and render genre chips |
| `index.html:833–835` | Update `getFilteredEvents` to include genres in search haystack |

No new files. No new dependencies.

---

## Task 1: Worker — parallel R2 fetch with genre map injection

**Files:**
- Modify: `worker.js` (full file, currently 28 lines)

### Context

The current worker fetches only `live_music_events.json`. We're adding a parallel fetch of `artists_db.json`, building a slim genre map from it, and injecting `window.__GENRES__` alongside the existing `window.__EVENTS__`.

The existing 503 guard for the events file must be preserved. If `artists_db.json` is absent, genre map falls back to `{}`.

- [ ] **Step 0: Create the feature branch**

The current branch is `seo-and-time-block-polish`. Cut the genre branch from here before making any changes:

```bash
git checkout -b genre-display
```

- [ ] **Step 1: Replace the worker fetch logic**

Open `worker.js`. Replace the entire contents with:

```js
import indexHtml from './index.html';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/' || path === '/index.html') {
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

      return new Response(injected, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-cache',
        },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

- [ ] **Step 2: Verify `window.__GENRES__` is injected**

Run: `wrangler dev --remote`

Open the browser, open DevTools → Console, run:
```js
typeof window.__GENRES__
// expected: "object"

Object.keys(window.__GENRES__).length
// expected: > 0 (currently 77 enriched artists)

Object.entries(window.__GENRES__).slice(0, 3)
// expected: array of [slug, [genre, ...]] pairs
```

- [ ] **Step 3: Verify site still loads when `artists_db.json` fetch fails**

This can't easily be tested without removing the file from R2. Confirm the code path by code review: the `if (artistsObj)` guard ensures `genreMap` stays `{}` if the fetch returns null.

- [ ] **Step 4: Commit**

```bash
git add worker.js
git commit -m "feat: inject window.__GENRES__ from artists_db.json via parallel R2 fetch"
```

---

## Task 2: Frontend — `resolveGenres` function, CSS, and card rendering

**Files:**
- Modify: `index.html:497` (CSS block)
- Modify: `index.html:982` (JS — add function before `renderCard`)
- Modify: `index.html:983–1024` (`renderCard` function)

### Context

`renderCard` is at line 983. It builds HTML strings and returns a card. We need to:
1. Call `resolveGenres` to get up to 3 genre strings
2. Render them as chips between the presenter line and admission line
3. Emit nothing when the array is empty

The `esc()` helper already exists at line 1037 — use it for genre chip content.

CSS lives inline in `<style>` in `<head>`. The `.event-admission` rule is at line 497.

- [ ] **Step 1: Add CSS for genre chips**

In `index.html`, find the `.event-admission` rule at line 497:
```css
    .event-admission { font-size: 12px; color: var(--text-muted); white-space: nowrap; margin-top: 4px; }
```

Add immediately after it:
```css
    .genre-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .genre-chip { font-size: 11px; color: var(--text-muted); border: 1px solid var(--border); border-radius: 3px; padding: 1px 5px; white-space: nowrap; }
```

- [ ] **Step 2: Add `resolveGenres` function**

Find the comment line just before `renderCard` (line 982):
```js
// ── Card renderers ────────────────────────────────────────────────────────────
function renderCard(e) {
```

Insert the new function between the comment and `renderCard`:
```js
// ── Card renderers ────────────────────────────────────────────────────────────
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

function renderCard(e) {
```

- [ ] **Step 3: Wire `resolveGenres` into `renderCard`**

> **Note:** Step 2 inserted ~17 lines before `renderCard`. All line numbers below are **pre-Step-2** values. Use content matching (the exact code strings quoted below) rather than line numbers when making these edits.

Inside `renderCard`, find the block of `const *Html` variable declarations (pre-edit: lines 986–989):
```js
  const subtitleHtml = e.subtitle   ? `<div class="event-subtitle">${esc(e.subtitle)}</div>` : '';
  const presenterHtml= e.presenter  ? `<span class="presenter">${esc(e.presenter)}</span>` : '';
  const admissionHtml= e.admission  ? `<div class="event-admission">${esc(e.admission)}</div>` : '';
  const linksHtml    = renderMusicLinks(e.music_links || {});
```

Add the genre resolution immediately after `linksHtml`:
```js
  const subtitleHtml = e.subtitle   ? `<div class="event-subtitle">${esc(e.subtitle)}</div>` : '';
  const presenterHtml= e.presenter  ? `<span class="presenter">${esc(e.presenter)}</span>` : '';
  const admissionHtml= e.admission  ? `<div class="event-admission">${esc(e.admission)}</div>` : '';
  const linksHtml    = renderMusicLinks(e.music_links || {});
  const genres       = resolveGenres(e.artists || []);
  const genreHtml    = genres.length
    ? `<div class="genre-tags">${genres.map(g => `<span class="genre-chip">${esc(g)}</span>`).join('')}</div>`
    : '';
```

Then find the card body template (lines 1019–1021):
```js
        ${presenterHtml ? `<div class="event-meta">${presenterHtml}</div>` : ''}
        ${admissionHtml}
        ${linksHtml}
```

Insert `genreHtml` between presenter and admission:
```js
        ${presenterHtml ? `<div class="event-meta">${presenterHtml}</div>` : ''}
        ${genreHtml}
        ${admissionHtml}
        ${linksHtml}
```

- [ ] **Step 4: Verify genre chips render correctly**

With `wrangler dev --remote` running, open the site in the browser. Find an event whose headliner has a known genre (check `artists_db.json` for a slug with a `genre` array).

Verify:
- Genre chips appear on that event card, below any presenter line, above admission/price
- No more than 3 chips per card
- Events with no genre data show no chip elements and no gap

Open DevTools → Elements and inspect an event without genre data. Confirm no `.genre-tags` div is present (not just hidden — completely absent).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: render genre chips on event cards (headliner-biased, max 3)"
```

---

## Task 3: Frontend — genre in text search

**Files:**
- Modify: `index.html:833–835` (`getFilteredEvents` search haystack)

### Context

**Requires Task 2 to be complete** — `resolveGenres` must be defined before this change takes effect.

`getFilteredEvents` at line 827 filters `allEvents`. The search haystack is built inside the `if (searchQuery)` guard at line 833. We need to call `resolveGenres` there and spread the result into the haystack. Calling `resolveGenres` twice per event (here + `renderCard`) is intentional — simplicity over caching, and cost is negligible.

- [ ] **Step 1: Update the search haystack in `getFilteredEvents`**

Find the search block inside `getFilteredEvents` (lines 833–836):
```js
    if (searchQuery) {
      const hay = [e.title, e.subtitle, e.presenter, e.venueName].join(' ').toLowerCase();
      if (!hay.includes(searchQuery)) return false;
    }
```

Replace with:
```js
    if (searchQuery) {
      const genres = resolveGenres(e.artists || []);
      const hay = [e.title, e.subtitle, e.presenter, e.venueName, ...genres].join(' ').toLowerCase();
      if (!hay.includes(searchQuery)) return false;
    }
```

- [ ] **Step 2: Verify genre search works**

With `wrangler dev --remote` running:

1. Find an event with a known genre chip visible on its card (from Task 2)
2. Note the genre string (e.g. "indie rock")
3. Type that genre into the search box
4. Verify matching events appear and non-matching events are filtered out
5. Clear the search — verify all events return

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: include genres in text search haystack"
```

---

## Task 4: Push and open PR

- [ ] **Step 1: Push**

```bash
git push -u origin genre-display
```

- [ ] **Step 3: Open PR**

Target branch: `seo-and-time-block-polish` (the branch `genre-display` was cut from)

PR title: `Add genre display to event cards with search support`

Body:
```
## Summary
- Worker fetches `artists_db.json` in parallel with events; injects `window.__GENRES__` (slim slug→genres map)
- `resolveGenres()` merges genres headliner-first, max 3, deduped
- Genre chips rendered on event cards between presenter and admission
- Genre strings included in text search haystack

## Test plan
- [ ] Genre chips visible on cards for enriched artists
- [ ] Cards without genre data show no chip element
- [ ] Text search for a genre term surfaces matching events
- [ ] Site functions normally with `artists_db.json` absent from R2
```
