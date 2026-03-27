"""Generic scraper for plain-HTML venues.

Delegates to live_music/scrapers/generic.py. Used via:
    python3 pipeline/cli.py scrape generic --raw .tmp/<venue>_raw.json --out .tmp/scraped_<venue>.json

See live_music/scrapers/generic.py for the raw input format spec (slug, title, date, show_time, etc.).
"""
from live_music.scrapers.generic import run, main  # noqa: F401
