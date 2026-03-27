# Artist Genre Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill `genre` (and missing links) for all ~722 artists in `artists_db.json` where the field is currently empty, using the Spotify Web API as the primary source and Bandcamp as a fallback for artists not found on Spotify.

**Architecture:** A standalone CLI script (`enrich_genres.py`) runs two sequential passes. Pass 1 (Spotify): artists with existing Spotify URLs get batch-fetched directly; the rest are searched by name with confidence-score filtering. Pass 2 (Bandcamp fallback): artists that still have no genre after Spotify are searched on Bandcamp's HTML search page; if a confident name match is found, the artist's Bandcamp page is fetched to extract genre tags and the Bandcamp URL is stored. Results are accumulated in memory and written atomically at completion (tmp file + `os.replace`). A `--dry-run` mode and `--no-bandcamp` flag are provided for testing.

**Tech Stack:** Python 3, `requests` (already available), Spotify Web API (free — register an app at developer.spotify.com to get `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`), Bandcamp HTML search (no API key — just HTTP), `difflib.SequenceMatcher` for name similarity scoring.

---

## Context

**File:** `artists_db.json`
Keyed by artist slug. Each entry looks like:
```json
{
  "name": "Vundabar",
  "genre": [],
  "last_enriched": "2026-03-21T00:00:00Z",
  "links": {
    "spotify": "https://open.spotify.com/artist/1W4itxt3vwhmrgLEBuVHJ6",
    "bandcamp": "",
    "instagram": "",
    "youtube": "",
    "website": ""
  }
}
```

**Current state:**
- 799 total artists
- 722 missing `genre` (empty list)
- 3 of those 722 have a Spotify URL; the remaining 719 have no links at all

**Spotify API endpoints used:**
- `POST https://accounts.spotify.com/api/token` — get bearer token (client credentials)
- `GET https://api.spotify.com/v1/artists?ids=id1,id2,...` — batch fetch up to 50 artists by ID; returns `genres` array
- `GET https://api.spotify.com/v1/search?q=<name>&type=artist&limit=5` — search by name; returns candidates to score

**Bandcamp endpoints used (no auth):**
- `GET https://bandcamp.com/search?q=<name>&item_type=b` — HTML search results page; parsed with regex
- `GET https://<slug>.bandcamp.com/` — artist page; genre tags extracted via regex

**Confidence scoring:** For both Spotify and Bandcamp search results, compare the returned artist name against the `artists_db` name using `difflib.SequenceMatcher`. Accept only if similarity ≥ 0.85. Note: this threshold does not protect against same-name collisions — a short or common name like "COLD" will score 1.0 against any same-named Spotify or Bandcamp artist. Short single-word names are flagged during verification (Task 5 Step 2).

---

## Files

| File | Action | Purpose |
|------|--------|---------|
| `enrich_genres.py` | **Create** | CLI entry point — argument parsing, Spotify pass, Bandcamp fallback pass, atomic write |
| `artists_db.json` | **Modify** | Updated in-place with genre, Spotify URL, and Bandcamp URL where found |

No new modules inside `live_music/` — this is a one-shot batch tool, not part of the regular scrape loop.

---

## Setup prerequisite (complete before Task 1)

Register a free Spotify developer app to get API credentials:

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create an app (any name, redirect URI doesn't matter for client credentials)
3. Copy **Client ID** and **Client Secret**
4. Set them in your shell before running the script:
   ```bash
   export SPOTIFY_CLIENT_ID=your_client_id
   export SPOTIFY_CLIENT_SECRET=your_client_secret
   ```

No user login required — client credentials flow is read-only and free.

---

## Task 1: Spotify token helper + batch artist-ID fetch

**Files:**
- Create: `enrich_genres.py` (initial skeleton + token + batch fetch)

- [ ] **Step 1: Create the script with token fetch**

```python
#!/usr/bin/env python3
"""
enrich_genres.py — Backfill genre for artists in artists_db.json.

Pass 1: Spotify Web API (requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET env vars)
Pass 2: Bandcamp HTML search fallback (no API key needed)

Usage:
    python3 enrich_genres.py [--dry-run] [--limit N] [--min-score 0.85] [--no-bandcamp]

Options:
    --dry-run       Print what would change; don't write to disk
    --limit N       Stop after processing N artists (useful for testing)
    --min-score     Minimum name-similarity score for search matches (default 0.85)
    --no-bandcamp   Skip the Bandcamp fallback pass
"""

import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

ARTISTS_DB = "artists_db.json"
TOKEN_URL = "https://accounts.spotify.com/api/token"
ARTISTS_URL = "https://api.spotify.com/v1/artists"
SEARCH_URL = "https://api.spotify.com/v1/search"
BANDCAMP_SEARCH_URL = "https://bandcamp.com/search"
BANDCAMP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; genre-enrichment/1.0)"}


def get_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--min-score", type=float, default=0.85)
    p.add_argument("--no-bandcamp", action="store_true")
    return p.parse_args()


def name_similarity(a: str, b: str) -> float:
    """Case-insensitive similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


if __name__ == "__main__":
    args = parse_args()
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars", file=sys.stderr)
        sys.exit(1)
    token = get_token(client_id, client_secret)
    print("✅ Got Spotify token")
```

- [ ] **Step 2: Test token fetch manually**

```bash
export SPOTIFY_CLIENT_ID=your_id
export SPOTIFY_CLIENT_SECRET=your_secret
python3 enrich_genres.py --dry-run
```

Expected: `✅ Got Spotify token`

- [ ] **Step 3: Add batch fetch by Spotify ID**

Add these functions to `enrich_genres.py` (before `if __name__ == "__main__":`):

```python
def spotify_id_from_url(url: str) -> str | None:
    """Extract artist ID from https://open.spotify.com/artist/XXXXX"""
    if not url:
        return None
    parts = url.rstrip("/").split("/")
    try:
        idx = parts.index("artist")
        return parts[idx + 1].split("?")[0]
    except (ValueError, IndexError):
        return None


def fetch_artists_by_ids(ids: list[str], token: str) -> dict[str, list[str]]:
    """Given Spotify artist IDs, return {id: [genres]}. Fetches up to 50 at a time."""
    result = {}
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(0, len(ids), 50):
        batch = ids[i:i+50]
        resp = requests.get(ARTISTS_URL, headers=headers, params={"ids": ",".join(batch)}, timeout=10)
        resp.raise_for_status()
        for artist in resp.json().get("artists") or []:
            if artist:
                result[artist["id"]] = artist.get("genres", [])
        time.sleep(0.1)
    return result


def search_spotify(name: str, token: str, min_score: float) -> dict | None:
    """Search Spotify by name. Returns {id, name, genres, score} or None.
    Raises SystemExit on 401 (token expired) so the operator knows to re-run."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        SEARCH_URL,
        headers=headers,
        params={"q": name, "type": "artist", "limit": 5},
        timeout=10,
    )
    if resp.status_code == 401:
        print("\n❌ Spotify token expired (HTTP 401). Re-run the script to get a fresh token.", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    candidates = resp.json().get("artists", {}).get("items", [])
    best, best_score = None, 0.0
    for c in candidates:
        score = name_similarity(name, c["name"])
        if score > best_score:
            best_score, best = score, c
    if best and best_score >= min_score:
        return {"id": best["id"], "name": best["name"], "genres": best.get("genres", []), "score": best_score}
    return None
```

- [ ] **Step 4: Commit skeleton**

```bash
git add enrich_genres.py
git commit -m "feat: add enrich_genres.py skeleton with Spotify token + batch ID fetch"
```

---

## Task 2: Bandcamp fallback helpers

**Files:**
- Modify: `enrich_genres.py`

- [ ] **Step 1: Add Bandcamp search + genre extraction functions**

Add these functions to `enrich_genres.py` (before `if __name__ == "__main__":`):

```python
def fetch_bandcamp_genres(url: str) -> list[str]:
    """Fetch genre tags from a Bandcamp artist page URL.
    Sleeps 1 second after fetching to respect Bandcamp's rate limits."""
    try:
        resp = requests.get(url, headers=BANDCAMP_HEADERS, timeout=15)
        time.sleep(1)  # explicit throttle — search_bandcamp already slept 1s
        if resp.status_code == 429:
            print(f"  ⚠️  Bandcamp rate-limited (429) fetching {url} — skipping genre fetch")
            return []
        resp.raise_for_status()
    except requests.RequestException:
        return []
    # Bandcamp artist pages contain: <a class="tag" href="/tag/indie-rock">indie rock</a>
    tags = re.findall(r'class="tag"[^>]*>([^<]+)<', resp.text)
    # Cap at 5; tags can include location info so strip anything suspiciously long
    return [t.strip() for t in tags if t.strip() and len(t.strip()) < 40][:5]


def search_bandcamp(name: str, min_score: float) -> dict | None:
    """Search Bandcamp for an artist by name.
    Returns {url, name, genres, score} or None."""
    try:
        resp = requests.get(
            BANDCAMP_SEARCH_URL,
            params={"q": name, "item_type": "b"},
            headers=BANDCAMP_HEADERS,
            timeout=15,
        )
        time.sleep(1)  # 1 req/s to Bandcamp search
        if resp.status_code == 429:
            print(f"  ⚠️  Bandcamp rate-limited (429) searching for '{name}' — skipping")
            return None
        resp.raise_for_status()
    except requests.RequestException:
        return None

    html = resp.text

    # Bandcamp search results: artist name + URL appear in heading divs.
    # Pattern avoids DOTALL/lazy-match cross-card bleeding by using [^<]* instead of .*?
    # <div class="heading"><a href="https://slug.bandcamp.com">Name</a>
    pattern = re.compile(
        r'class="heading"[^>]*>[^<]*<a[^>]+href="(https://[^"]+\.bandcamp\.com(?:/[^"]*)?)"[^>]*>\s*([^<]+?)\s*</a>'
    )
    for match in pattern.finditer(html):
        url, found_name = match.group(1).split("?")[0].rstrip("/"), match.group(2).strip()
        # Normalise to artist root (drop any path like /music)
        root = "/".join(url.split("/")[:3])
        score = name_similarity(name, found_name)
        if score >= min_score:
            genres = fetch_bandcamp_genres(root)
            return {"url": root, "name": found_name, "genres": genres, "score": score}
    return None
```

- [ ] **Step 2: Smoke test Bandcamp search (temporary)**

Add temporarily to `if __name__ == "__main__":`:

```python
    result = search_bandcamp("Vundabar", args.min_score)
    print(f"Bandcamp test — Vundabar: {result}")
```

Run: `python3 enrich_genres.py --dry-run`

Expected: URL `vundabar.bandcamp.com` and genres like `['indie rock', ...]`

- [ ] **Step 3: Remove smoke test, commit**

```bash
git add enrich_genres.py
git commit -m "feat: add Bandcamp search + genre tag extraction fallback"
```

---

## Task 3: Main enrichment loop

**Files:**
- Modify: `enrich_genres.py`

- [ ] **Step 1: Add the main enrichment function**

```python
def enrich(db: dict, token: str, dry_run: bool, limit: int | None, min_score: float, no_bandcamp: bool) -> dict:
    """Run enrichment (Spotify pass then Bandcamp fallback). Returns stats dict."""
    stats = {"spotify_updated": 0, "bandcamp_updated": 0, "not_found": 0}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    needs_genre = [(slug, entry) for slug, entry in db.items() if not entry.get("genre")]
    if limit:
        needs_genre = needs_genre[:limit]
    print(f"Artists needing genre: {len(needs_genre)}\n")

    # ── Spotify Pass 1a: batch-fetch artists that already have a Spotify URL ──
    has_url = [(s, e) for s, e in needs_genre if spotify_id_from_url(e.get("links", {}).get("spotify", ""))]
    still_need: list[tuple[str, dict]] = []  # artists to hand off to search / Bandcamp

    if has_url:
        print(f"── Spotify: batch-fetching {len(has_url)} artists with existing URLs")
        ids = [spotify_id_from_url(e["links"]["spotify"]) for _, e in has_url]
        genres_by_id = fetch_artists_by_ids(ids, token)
        for (slug, entry), sp_id in zip(has_url, ids):
            genres = genres_by_id.get(sp_id, [])
            if genres:
                print(f"  ✅ {entry['name']}: {genres}")
                if not dry_run:
                    entry["genre"] = genres
                    entry["last_enriched"] = now
                stats["spotify_updated"] += 1
            else:
                print(f"  ⚠️  {entry['name']}: Spotify returned no genres — will try Bandcamp")
                still_need.append((slug, entry))

    # ── Spotify Pass 1b: search for artists without a Spotify URL ──
    no_url = [(s, e) for s, e in needs_genre if not spotify_id_from_url(e.get("links", {}).get("spotify", ""))]
    print(f"\n── Spotify: searching for {len(no_url)} artists without Spotify URL")
    for i, (slug, entry) in enumerate(no_url):
        name = entry["name"]
        try:
            result = search_spotify(name, token, min_score)
        except requests.RequestException as exc:
            print(f"  ❌ {name}: request error — {exc}")
            still_need.append((slug, entry))
            time.sleep(1)
            continue

        if result and result["genres"]:
            print(f"  ✅ {name} → '{result['name']}' (score={result['score']:.2f}): {result['genres']}")
            if not dry_run:
                entry["genre"] = result["genres"]
                entry["links"]["spotify"] = f"https://open.spotify.com/artist/{result['id']}"
                entry["last_enriched"] = now
            stats["spotify_updated"] += 1
        elif result:
            print(f"  ⚠️  {name} → '{result['name']}' matched but Spotify has no genres — will try Bandcamp")
            if not dry_run:
                entry["links"]["spotify"] = f"https://open.spotify.com/artist/{result['id']}"
            still_need.append((slug, entry))
        else:
            print(f"  —  {name}: no confident Spotify match — will try Bandcamp")
            still_need.append((slug, entry))

        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    # ── Bandcamp fallback pass ──
    if no_bandcamp or not still_need:
        stats["not_found"] += len(still_need)
        return stats

    print(f"\n── Bandcamp: searching for {len(still_need)} artists not resolved by Spotify")
    for i, (slug, entry) in enumerate(still_need):
        name = entry["name"]
        try:
            result = search_bandcamp(name, min_score)
        except Exception as exc:
            print(f"  ❌ {name}: Bandcamp error — {exc}")
            stats["not_found"] += 1
            time.sleep(1)
            continue

        if result and result["genres"]:
            print(f"  ✅ {name} → '{result['name']}' (score={result['score']:.2f}): {result['genres']}")
            if not dry_run:
                entry["genre"] = result["genres"]
                entry["links"]["bandcamp"] = result["url"]
                entry["last_enriched"] = now
            stats["bandcamp_updated"] += 1
        elif result:
            print(f"  ⚠️  {name} → '{result['name']}' on Bandcamp but no genre tags — storing URL")
            if not dry_run:
                entry["links"]["bandcamp"] = result["url"]
                entry["last_enriched"] = now
            stats["not_found"] += 1
        else:
            print(f"  —  {name}: not found on Bandcamp")
            stats["not_found"] += 1

        # No additional sleep here — search_bandcamp and fetch_bandcamp_genres
        # each sleep 1s internally, giving ~2s per artist (~30 req/min total).

    return stats
```

- [ ] **Step 2: Wire up the main block**

Replace the `if __name__ == "__main__":` block with:

```python
if __name__ == "__main__":
    args = parse_args()
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars", file=sys.stderr)
        sys.exit(1)

    token = get_token(client_id, client_secret)
    print(f"✅ Got Spotify token\n")

    with open(ARTISTS_DB) as f:
        db = json.load(f)

    stats = enrich(db, token, args.dry_run, args.limit, args.min_score, args.no_bandcamp)

    if not args.dry_run:
        tmp = ARTISTS_DB + ".tmp"
        with open(tmp, "w") as f:
            json.dump(db, f, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, ARTISTS_DB)  # atomic; consistent with save_artists() in live_music/state.py
        print(f"\n✅ Saved {ARTISTS_DB}")

    print(f"\n── Summary ──────────────────────────────")
    print(f"  Spotify updated:  {stats['spotify_updated']}")
    print(f"  Bandcamp updated: {stats['bandcamp_updated']}")
    print(f"  Not found:        {stats['not_found']}")
    if args.no_bandcamp:
        print("  (Bandcamp pass skipped — run without --no-bandcamp to process remaining)")
    if args.dry_run:
        print("  (DRY RUN — nothing written)")
```

- [ ] **Step 3: Test Spotify-only with --limit 10 --dry-run --no-bandcamp**

```bash
python3 enrich_genres.py --dry-run --limit 10 --no-bandcamp
```

Expected: 10 artists processed via Spotify only, nothing written.

- [ ] **Step 4: Test full pipeline with --limit 10 --dry-run**

```bash
python3 enrich_genres.py --dry-run --limit 10
```

Expected: Spotify pass runs first, then Bandcamp runs for any unresolved artists. No files changed.

- [ ] **Step 5: Test a small live run**

```bash
python3 enrich_genres.py --limit 20
```

Check `artists_db.json` — verify some artists have `genre` populated and that `bandcamp` URLs appear for artists not found on Spotify.

- [ ] **Step 6: Commit**

```bash
git add enrich_genres.py
git commit -m "feat: complete genre enrichment with Spotify + Bandcamp fallback"
```

---

## Task 4: Full run + upload

- [ ] **Step 1: Run on all missing-genre artists**

```bash
python3 enrich_genres.py
```

Expected: ~722 artists processed across both passes. Spotify is fast (~1-2 minutes). Bandcamp throttles at ~2 seconds per artist (1s search + 1s page fetch), so if half the artists fall through to Bandcamp the total run is roughly 15-20 minutes — well within the 60-minute Spotify token window. If a 401 occurs mid-run the script will exit with a clear message; re-run to get a fresh token (already-written genres won't be reprocessed).

- [ ] **Step 2: Verify results**

```bash
python3 -c "
import json
db = json.load(open('artists_db.json'))
missing = [v['name'] for v in db.values() if not v.get('genre')]
print(f'Still missing genre: {len(missing)}')
for n in missing[:20]: print(f'  {n}')

# Flag short names that may have matched the wrong artist
short = [(v['name'], v.get('genre')) for v in db.values()
         if v.get('genre') and len(v['name'].split()) <= 2 and len(v['name']) <= 8]
print(f'\nShort names with genres assigned ({len(short)}) — spot-check these:')
for name, genres in short[:20]: print(f'  {name}: {genres}')
"
```

Artists still missing genre were not found on either Spotify or Bandcamp — typically very local or obscure acts. This is expected and acceptable.

Short single-word names that matched may have received genres from the wrong artist — spot-check a sample for accuracy.

- [ ] **Step 3: Upload to R2**

```bash
python3 live_music_cli.py upload
```

- [ ] **Step 4: Commit final state**

```bash
git add artists_db.json
git commit -m "data: backfill genres for ~722 artists via Spotify + Bandcamp"
```
