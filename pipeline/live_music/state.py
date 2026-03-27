"""
live_music/state.py — Load/save state file and artists database.
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

STATE_FILE = Path(__file__).parent.parent / "live_music_events.json"
ARTISTS_FILE = Path(__file__).parent.parent / "artists_db.json"
VENUES_FILE = Path(__file__).parent.parent / "venues_db.json"

# ── State file ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"ERROR: state file not found at {STATE_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(data: dict):
    # Write to a temp file first, then atomically rename — never leaves live file partially written
    tmp_path = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if STATE_FILE.exists():
        shutil.copy2(STATE_FILE, STATE_FILE.with_suffix(".json.bak"))
    os.replace(tmp_path, STATE_FILE)
    print(f"💾 State file saved: {STATE_FILE}")


def parse_key(key: str):
    """Split 'kings-id:holy-fuck' into (venue_key_for_tag, event_id).
    Searches all venues for one whose event_id_tag matches."""
    if ":" not in key:
        print(f"ERROR: event key must be in format <event_id_tag>:<event_id>, e.g. kings-id:holy-fuck")
        sys.exit(1)
    tag, event_id = key.split(":", 1)
    return tag, event_id


def find_venue_by_tag(data: dict, tag: str) -> Optional[tuple]:
    """Return (venue_key, venue_dict) for the venue with a matching event_id_tag."""
    for vk, v in data["venues"].items():
        if v.get("event_id_tag") == tag:
            return vk, v
    return None, None

# ── Venues database ────────────────────────────────────────────────────────────

def load_venues() -> dict:
    if not VENUES_FILE.exists():
        return {}
    with open(VENUES_FILE) as f:
        return json.load(f)


def save_venues(data: dict):
    tmp_path = VENUES_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    os.replace(tmp_path, VENUES_FILE)
    print(f"Venues DB saved: {VENUES_FILE}")


# ── Artists database ───────────────────────────────────────────────────────────

def load_artists() -> dict:
    if not ARTISTS_FILE.exists():
        return {}
    with open(ARTISTS_FILE) as f:
        return json.load(f)


def save_artists(data: dict):
    tmp_path = ARTISTS_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    os.replace(tmp_path, ARTISTS_FILE)
    print(f"💾 Artists DB saved: {ARTISTS_FILE}")
