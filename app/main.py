import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import storage, telegram, updater
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("app")

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.wiki_contact == "not-set":
        log.warning("Set WIKI_CONTACT in .env (contact sent to the wiki in the User-Agent)")
    tasks = [asyncio.create_task(telegram.run())]
    if settings.scheduler_enabled:
        tasks.append(asyncio.create_task(updater.scheduler_loop()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Rivals Skins", lifespan=lifespan)

_cache: dict = {"key": None, "data": None}


def _catalog() -> dict:
    """Merge heroes.json and skins.json, cached until either file changes."""
    files = [storage.path(storage.HEROES_FILE), storage.path(storage.SKINS_FILE)]
    key = tuple(f.stat().st_mtime if f.exists() else None for f in files)
    if key == _cache["key"]:
        return _cache["data"]

    h = storage.read_json(storage.HEROES_FILE, {}) or {}
    s = storage.read_json(storage.SKINS_FILE, {}) or {}
    heroes = {x["id"]: dict(x) for x in h.get("heroes", [])}
    skins = s.get("skins", [])

    for sk in skins:
        if sk["heroId"] not in heroes:  # hero missing from the Heroes page (e.g. just released)
            heroes[sk["heroId"]] = {"id": sk["heroId"], "name": sk["heroName"], "role": None,
                                    "color": None, "image": None, "wikiUrl": None}
        hero = heroes[sk["heroId"]]
        if sk.get("isDefault") and not hero.get("image"):
            hero["image"] = sk.get("image")
        if not sk.get("isDefault"):
            hero["skinCount"] = hero.get("skinCount", 0) + 1

    data = {
        "heroes": sorted(heroes.values(), key=lambda x: x["name"].lower()),
        "skins": skins,
        "heroesUpdatedAt": h.get("updatedAt"),
        "skinsUpdatedAt": s.get("updatedAt"),
    }
    _cache.update(key=key, data=data)
    return data


@app.get("/api/catalog")
def catalog():
    return _catalog()


@app.get("/api/status")
def status():
    c = _catalog()
    state = storage.read_json(storage.STATE_FILE, {}) or {}
    return {
        "heroes": len(c["heroes"]),
        "skins": len(c["skins"]),
        "heroesUpdatedAt": c["heroesUpdatedAt"],
        "skinsUpdatedAt": c["skinsUpdatedAt"],
        "heroesFailedAt": state.get("heroesFailedAt"),
        "skinsFailedAt": state.get("skinsFailedAt"),
        "unmatched": state.get("unmatched", []),
        "telegram": telegram.state,
    }


(settings.data_dir / "images").mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=settings.data_dir / "images"), name="images")
# mounted last so it does not shadow /api
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")
