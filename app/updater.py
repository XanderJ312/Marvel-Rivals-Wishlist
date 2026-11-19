"""Data update scheduler.

- monthly (HEROES_DAY_OF_MONTH): hero list and a full skin rebuild,
- daily: skins whose templates changed,
- on startup: catch up on updates missed while the app was down.

Manual run: python -m app.update [heroes|skins|all] [--full]
"""

import asyncio
import logging
from datetime import datetime, timedelta

from . import storage
from .config import settings
from .heroes import update_heroes
from .skins import update_skins
from .wiki import Wiki

log = logging.getLogger("updater")

_lock = asyncio.Lock()
RETRY_AFTER_FAILURE = timedelta(hours=1)
CHECK_EVERY = 30 * 60  # seconds


def _local(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso).astimezone() if iso else None
    except ValueError:
        return None


def last_heroes_due(now: datetime) -> datetime:
    """Return the last moment the hero list was due for a refresh."""
    day = settings.heroes_day_of_month
    due = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    if now < due:
        prev_month = (now.replace(day=1) - timedelta(days=1))
        due = prev_month.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    return due


def _recently_failed(state: dict, key: str, now: datetime) -> bool:
    failed = _local(state.get(f"{key}FailedAt"))
    return bool(failed and now - failed < RETRY_AFTER_FAILURE)


def _mark(key: str, ok: bool):
    state = storage.read_json(storage.STATE_FILE, {}) or {}
    state[f"{key}FailedAt"] = None if ok else storage.now_iso()
    storage.write_json(storage.STATE_FILE, state)


def _heroes() -> list[dict]:
    return (storage.read_json(storage.HEROES_FILE, {}) or {}).get("heroes", [])


async def run(heroes: bool = False, skins: bool = False, full: bool = False, scheduled: bool = False):
    """Run an update. With scheduled=True, decide what is due on its own."""
    async with _lock:
        now = datetime.now().astimezone()
        state = storage.read_json(storage.STATE_FILE, {}) or {}

        if scheduled:
            h_updated = _local((storage.read_json(storage.HEROES_FILE, {}) or {}).get("updatedAt"))
            s_updated = _local((storage.read_json(storage.SKINS_FILE, {}) or {}).get("updatedAt"))
            heroes = (not h_updated or h_updated < last_heroes_due(now)) and not _recently_failed(state, "heroes", now)
            full = heroes  # the monthly run also rebuilds all skins
            skins = heroes or (
                (not s_updated or s_updated.date() < now.date()) and not _recently_failed(state, "skins", now)
            )
        if not (heroes or skins):
            return

        async with Wiki() as wiki:
            if heroes:
                try:
                    await update_heroes(wiki)
                    _mark("heroes", True)
                except Exception as e:
                    log.error("Hero update failed: %s, keeping previous data", e)
                    _mark("heroes", False)

            if skins:
                try:
                    unmatched = await update_skins(wiki, _heroes(), full=full)
                    known_unmatched = set(state.get("unmatched", []))
                    if unmatched and not heroes and not set(unmatched) <= known_unmatched:
                        log.info("New templates without a hero (%s), refreshing the hero list", ", ".join(unmatched))
                        await update_heroes(wiki)
                        unmatched = await update_skins(wiki, _heroes())
                    if unmatched:
                        log.warning("Templates without a matching hero: %s", ", ".join(unmatched))
                    st = storage.read_json(storage.STATE_FILE, {}) or {}
                    st["unmatched"] = unmatched
                    storage.write_json(storage.STATE_FILE, st)
                    _mark("skins", True)
                except Exception as e:
                    log.error("Skin update failed: %s, keeping previous data", e)
                    _mark("skins", False)

            log.info("Wiki requests in this update: %d", wiki.requests_made)


async def scheduler_loop():
    while True:
        try:
            await run(scheduled=True)
        except Exception as e:  # never let one failure stop the scheduler
            log.exception("Scheduler error: %s", e)
        await asyncio.sleep(CHECK_EVERY)
