"""Lightweight cache helpers (optional, MVP stubs)."""

from pathlib import Path


def get_cache_dir(root: Path) -> Path:
    d = root / ".cache"
    d.mkdir(parents=True, exist_ok=True)
    return d

