from datetime import datetime, timedelta, timezone

import pytest

from app import storage, updater
from app.config import settings

TZ = timezone(timedelta(hours=1))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 20, 10, 0, tzinfo=TZ), datetime(2026, 11, 15, tzinfo=TZ)),  # after the 15th
        (datetime(2026, 11, 15, 0, 0, tzinfo=TZ), datetime(2026, 11, 15, tzinfo=TZ)),  # exactly at midnight
        (datetime(2026, 11, 3, 10, 0, tzinfo=TZ), datetime(2026, 10, 15, tzinfo=TZ)),  # before: previous month
        (datetime(2026, 1, 10, 10, 0, tzinfo=TZ), datetime(2025, 12, 15, tzinfo=TZ)),  # across the new year
    ],
)
def test_last_heroes_due(now, expected):
    assert updater.last_heroes_due(now) == expected


def test_heroes_day_of_month_is_limited_to_days_every_month_has():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(heroes_day_of_month=31)


def test_recently_failed():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    assert updater._recently_failed({"skinsFailedAt": "2026-11-20T11:30:00+00:00"}, "skins", now)
    assert not updater._recently_failed({"skinsFailedAt": "2026-11-20T10:00:00+00:00"}, "skins", now)
    assert not updater._recently_failed({"skinsFailedAt": None}, "skins", now)
    assert not updater._recently_failed({"skinsFailedAt": "garbage"}, "skins", now)


# --- what does a scheduled run decide to do? ---------------------------------------
class Recorder:
    """Replaces the real update functions and the wiki client."""

    def __init__(self, monkeypatch, unmatched=()):
        self.calls = []
        self.unmatched = list(unmatched)

        class DummyWiki:
            requests_made = 0

            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *exc):
                return False

        async def fake_heroes(wiki):
            self.calls.append("heroes")
            storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso(), "heroes": []})

        async def fake_skins(wiki, heroes, full=False):
            self.calls.append(f"skins(full={full})")
            storage.write_json(storage.SKINS_FILE, {"updatedAt": storage.now_iso(), "skins": []})
            result, self.unmatched = self.unmatched, []  # the second run finds a matching hero
            return result

        monkeypatch.setattr(updater, "Wiki", DummyWiki)
        monkeypatch.setattr(updater, "update_heroes", fake_heroes)
        monkeypatch.setattr(updater, "update_skins", fake_skins)


def _ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")


async def test_first_run_downloads_heroes_and_all_skins(data_dir, monkeypatch):
    rec = Recorder(monkeypatch)
    await updater.run(scheduled=True)
    assert rec.calls == ["heroes", "skins(full=True)"]


async def test_nothing_to_do_when_data_is_fresh(data_dir, monkeypatch):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": storage.now_iso()})
    rec = Recorder(monkeypatch)
    await updater.run(scheduled=True)
    assert rec.calls == []


async def test_daily_run_updates_only_changed_skins(data_dir, monkeypatch):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": _ago(days=2)})
    rec = Recorder(monkeypatch)
    await updater.run(scheduled=True)
    assert rec.calls == ["skins(full=False)"]


async def test_recent_failure_postpones_the_retry(data_dir, monkeypatch):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": _ago(days=2)})
    storage.write_json(storage.STATE_FILE, {"skinsFailedAt": _ago(minutes=10)})
    rec = Recorder(monkeypatch)
    await updater.run(scheduled=True)
    assert rec.calls == []


async def test_new_unmatched_template_triggers_hero_refresh(data_dir, monkeypatch):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": _ago(days=2)})
    rec = Recorder(monkeypatch, unmatched=["Brand New Hero"])
    await updater.run(scheduled=True)

    assert rec.calls == ["skins(full=False)", "heroes", "skins(full=False)"]
    assert storage.read_json(storage.STATE_FILE)["unmatched"] == []


async def test_failed_update_is_recorded_and_old_data_stays(data_dir, monkeypatch):
    Recorder(monkeypatch)

    async def broken_skins(wiki, heroes, full=False):
        raise RuntimeError("wiki is down")

    monkeypatch.setattr(updater, "update_skins", broken_skins)
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": _ago(days=2), "skins": [{"id": "old"}]})

    await updater.run(scheduled=True)

    assert storage.read_json(storage.STATE_FILE)["skinsFailedAt"] is not None
    assert storage.read_json(storage.SKINS_FILE)["skins"] == [{"id": "old"}]


async def test_manual_run_does_exactly_what_was_asked(data_dir, monkeypatch):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso()})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": storage.now_iso()})
    rec = Recorder(monkeypatch)
    await updater.run(skins=True, full=True)
    assert rec.calls == ["skins(full=True)"]


def test_settings_default_day():
    assert 1 <= settings.heroes_day_of_month <= 28
