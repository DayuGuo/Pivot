"""Explicitly synthetic, immutable editorial workbench fixtures."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_cases() -> list[dict]:
    """Load bundled fixture data. Callers must not mutate the cached records."""
    return json.loads(Path(__file__).with_name("dataset.json").read_text(encoding="utf-8"))["cases"]
