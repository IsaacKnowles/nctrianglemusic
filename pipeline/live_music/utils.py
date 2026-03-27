"""
live_music/utils.py — Date/hash/slug helpers and shared constants.
"""

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────
NOW_UTC = datetime.now(timezone.utc)
TODAY = NOW_UTC.date()
DEFAULT_PRUNE_DAYS = 30
DEFAULT_UPCOMING_DAYS = 14

# ── Date helpers ───────────────────────────────────────────────────────────────

def parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse a variety of ISO datetime strings to a UTC-aware datetime."""
    if not s:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def parse_event_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse naive local datetimes from event records (stored without tz)."""
    if not s:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def event_date(event: dict) -> Optional[datetime]:
    return parse_event_dt(event.get("start_datetime"))


def staleness_dt(v: dict) -> datetime:
    lu = parse_dt(v.get("last_updated"))
    return lu if lu else datetime(1970, 1, 1, tzinfo=timezone.utc)


def age_str(dt: datetime) -> str:
    delta = NOW_UTC - dt
    days = delta.days
    if days == 0:
        hours = delta.seconds // 3600
        return f"{hours}h ago"
    return f"{days}d ago"

# ── Hash helpers ───────────────────────────────────────────────────────────────

def normalize_for_hash(s: str) -> str:
    """Normalize text for stable content-hash comparison.
    Uses Unicode categories — no hard-coded code points.
    Applied only for comparison; stored text is never mutated."""
    s = unicodedata.normalize("NFKC", s)
    result = []
    for c in s:
        cat = unicodedata.category(c)
        if cat in ("Pi", "Pf"):  # any initial/final quotation mark → straight quote
            result.append("'")
        elif cat == "Pd":        # any dash/hyphen variant → ASCII hyphen
            result.append("-")
        else:
            result.append(c)
    return " ".join("".join(result).casefold().split())


def content_hash(event: dict) -> str:
    raw = "".join(normalize_for_hash(event.get(f, ""))
                  for f in ["title", "subtitle", "date_str", "time", "admission"])
    return hashlib.md5(raw.encode()).hexdigest()

# ── Slug helper ────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Lowercase, strip punctuation, replace spaces with hyphens."""
    text = name.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text
