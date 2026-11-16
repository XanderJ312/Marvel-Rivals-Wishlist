"""Read and write data files in the data/ directory."""

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

HEROES_FILE = "heroes.json"
SKINS_FILE = "skins.json"
STATE_FILE = "state.json"


def path(name: str) -> Path:
    return settings.data_dir / name


def read_json(name: str, default=None):
    p = path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name: str, data) -> None:
    """Write atomically: temp file first, then replace, so a crash never leaves a broken file."""
    p = path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def write_bytes(rel: str, content: bytes) -> None:
    p = path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, p)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"
