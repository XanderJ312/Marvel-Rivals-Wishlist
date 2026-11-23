"""Shared test setup.

Settings are read from environment variables when `app.config` is imported,
so they are set here, before any `app.*` module is imported by the tests.
"""

import os
import tempfile
from pathlib import Path

import pytest

_SESSION_DATA = Path(tempfile.mkdtemp(prefix="rivals-test-data-"))
os.environ.update(
    DATA_DIR=str(_SESSION_DATA),
    WIKI_CONTACT="tests@example.com",
    SCHEDULER_ENABLED="false",
    TELEGRAM_BOT_TOKEN="",
    PUBLIC_URL="",
    TUNNEL_METRICS_URL="",
    REQUEST_DELAY="0",
)

from app.config import settings  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    return lambda name: (FIXTURES / name).read_text("utf-8")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Every test gets its own empty data/ directory."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "request_delay", 0.0)
    monkeypatch.setattr(settings, "image_delay", 0.0)
    return tmp_path
