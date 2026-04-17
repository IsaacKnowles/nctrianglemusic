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

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

ARTISTS_DB = str(pathlib.Path(__file__).parent / "artists_db.json")
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
    if resp.status_code == 401:
        print("ERROR: Spotify credentials rejected (HTTP 401). Check SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.", file=sys.stderr)
        sys.exit(1)
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
    """Given Spotify artist IDs, return {id: [genres]}. Fetches one at a time (batch endpoint requires extended API access)."""
    result = {}
    headers = {"Authorization": f"Bearer {token}"}
    total = len(ids)
    for i, sp_id in enumerate(ids, 1):
        print(f"  [{i}/{total}] fetching {sp_id}", flush=True)
        for attempt in range(5):
            resp = requests.get(f"{ARTISTS_URL}/{sp_id}", headers=headers, timeout=10)
            if resp.status_code == 401:
                print("\n❌ Spotify token expired (HTTP 401). Re-run the script to get a fresh token.", file=sys.stderr)
                sys.exit(1)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
                print(f"  ⏳ Spotify rate-limited — waiting {retry_after}s (attempt {attempt + 1}/5)", flush=True)
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            data = resp.json()
            result[data["id"]] = data.get("genres", [])
            break
        time.sleep(0.2)
    return result


def search_spotify(name: str, token: str, min_score: float) -> dict | None:
    """Search Spotify by name. Returns {id, name, genres, score} or None.
    Raises SystemExit on 401 (token expired) so the operator knows to re-run."""
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(5):
        resp = requests.get(
            SEARCH_URL,
            headers=headers,
            params={"q": name, "type": "artist", "limit": 5},
            timeout=10,
        )
        if resp.status_code == 401:
            print("\n❌ Spotify token expired (HTTP 401). Re-run the script to get a fresh token.", file=sys.stderr)
            sys.exit(1)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
            print(f"  ⏳ Spotify rate-limited searching '{name}' — waiting {retry_after}s")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        break
    candidates = resp.json().get("artists", {}).get("items", [])
    best, best_score = None, 0.0
    for c in candidates:
        score = name_similarity(name, c["name"])
        if score > best_score:
            best_score, best = score, c
    if best and best_score >= min_score:
        return {"id": best["id"], "name": best["name"], "genres": best.get("genres", []), "score": best_score}
    return None


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
    except requests.RequestException as exc:
        print(f"  ⚠️  Bandcamp fetch failed for {url}: {exc}")
        return []
    # Bandcamp artist pages contain: <a class="tag" href="/tag/indie-rock">indie rock</a>
    tags = re.findall(r'class="tag"[^>]*>([^<]+)<', resp.text)
    # Cap at 5; tags can include location info so strip anything suspiciously long.
    # 40 chars is the ceiling before genre phrases get clipped; location strings like 'Seattle, Washington' run ~20 chars.
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
    except requests.RequestException as exc:
        print(f"  ⚠️  Bandcamp search request failed for '{name}': {exc}")
        return None

    html = resp.text

    # Bandcamp search results: artist name + URL appear in heading divs.
    # The name is on its own indented line after the <a> tag, so re.DOTALL is needed.
    # Cross-card bleeding is prevented by bounding the match up to class="subhead".
    # <div class="heading">
    #     <a href="https://slug.bandcamp.com?from=search&...">
    #     Name
    #     </a>
    # </div>
    # <div class="subhead">...
    pattern = re.compile(
        r'class="heading"([\s\S]{0,800}?)class="subhead"'
    )
    href_re = re.compile(r'href="(https://[^"]+\.bandcamp\.com[^"]*)"')
    # Artist name sits on its own indented line followed by optional whitespace then </a>
    # Assumes Bandcamp serves pretty-printed HTML; will miss matches if minified.
    name_re = re.compile(r'>\s*\n\s+([^\s<][^<\n]+?)\s*\n')
    for block_match in pattern.finditer(html):
        block = block_match.group(1)
        url_m = href_re.search(block)
        name_m = name_re.search(block)
        if not url_m or not name_m:
            continue
        url = url_m.group(1).split("?")[0].rstrip("/")
        found_name = name_m.group(1).strip()
        # Normalise to artist root (drop any path like /music)
        root = "/".join(url.split("/")[:3])
        score = name_similarity(name, found_name)
        if score >= min_score:
            genres = fetch_bandcamp_genres(root)
            return {"url": root, "name": found_name, "genres": genres, "score": score}
    return None


def enrich(db: dict, token: str, dry_run: bool, limit: int | None, min_score: float, no_bandcamp: bool) -> dict:
    """Run enrichment (Spotify pass then Bandcamp fallback). Returns stats dict."""
    stats = {"spotify_updated": 0, "bandcamp_updated": 0, "not_found": 0}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    needs_genre = [(slug, entry) for slug, entry in db.items() if not entry.get("genre")]
    if limit:
        needs_genre = needs_genre[:limit]
    print(f"Artists needing genre: {len(needs_genre)}\n", flush=True)

    # ── Spotify Pass 1a: batch-fetch artists that already have a Spotify URL ──
    has_url = [(s, e) for s, e in needs_genre if spotify_id_from_url(e.get("links", {}).get("spotify", ""))]
    still_need: list[tuple[str, dict]] = []  # populated by both Pass 1a and 1b; consumed by Bandcamp pass

    if has_url:
        print(f"── Spotify: batch-fetching {len(has_url)} artists with existing URLs", flush=True)
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
    print(f"\n── Spotify: searching for {len(no_url)} artists without Spotify URL", flush=True)
    for i, (slug, entry) in enumerate(no_url):
        name = entry["name"]
        print(f"  [{i+1}/{len(no_url)}] searching: {name}", flush=True)
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

    print(f"\n── Bandcamp: searching for {len(still_need)} artists not resolved by Spotify", flush=True)
    for i, (slug, entry) in enumerate(still_need):
        name = entry["name"]
        print(f"  [{i+1}/{len(still_need)}] Bandcamp: {name}", flush=True)
        try:
            result = search_bandcamp(name, min_score)
        except Exception as exc:
            print(f"  ❌ {name}: Bandcamp error — {exc}")
            stats["not_found"] += 1
            time.sleep(1)  # defensive: search_bandcamp may have thrown before its own internal sleep
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


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars", file=sys.stderr)
        sys.exit(1)

    start_time = time.monotonic()
    token = get_token(client_id, client_secret)
    print(f"✅ Got Spotify token\n", flush=True)

    with open(ARTISTS_DB) as f:
        db = json.load(f)

    stats = enrich(db, token, args.dry_run, args.limit, args.min_score, args.no_bandcamp)
    elapsed = time.monotonic() - start_time

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
    print(f"  Elapsed:          {elapsed:.0f}s")
    if args.no_bandcamp and stats["not_found"] > 0:
        print("  (Bandcamp pass skipped — run without --no-bandcamp to process remaining)")
    if args.dry_run:
        print("  (DRY RUN — nothing written)")
