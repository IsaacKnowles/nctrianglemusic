#!/usr/bin/env python3
"""Entry point for the live music pipeline CLI.

Run from the repo root:
    python3 pipeline/cli.py <command> [args...]

All commands are documented in live_music/cli.py. Run with --help to see them.
"""
import sys
from pathlib import Path

# Add pipeline/ to sys.path so live_music package and venue scrapers are importable
sys.path.insert(0, str(Path(__file__).parent))

from live_music.cli import main

if __name__ == "__main__":
    main()
