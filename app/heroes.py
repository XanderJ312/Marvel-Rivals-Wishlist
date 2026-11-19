"""Hero list from the wiki "Heroes" page: name, role, color and default skin image."""

import logging
import os
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from . import storage
from .config import settings
from .wiki import Wiki, WikiError

log = logging.getLogger("heroes")

ROLES = {"vanguard": "Vanguard", "duelist": "Duelist", "strategist": "Strategist"}


def _img_url(img) -> str | None:
    if not img:
        return None
    for attr in ("data-src", "src"):
        v = img.get(attr)
        if v and not v.startswith("data:"):
            return v
    return None


def parse_heroes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    heroes, seen = [], set()
    for card in soup.select(".herocard-wrapper"):
        name_el = card.select_one(".herocard-name")
        if not name_el:
            continue
        name = " ".join(name_el.get_text().split())
        hid = storage.slugify(name)
        if hid in seen:
            continue
        seen.add(hid)

        role = None
        role_img = card.select_one(".herocard-class img")
        if role_img:
            alt = (role_img.get("alt") or "").lower()
            role = next((v for k, v in ROLES.items() if k in alt), None)

        link = card.select_one(".herocard-link a")
        color = re.search(r"--herocard-bg:\s*([^;]+)", card.get("style", ""))
        heroes.append({
            "id": hid,
            "name": name,
            "role": role,
            "color": color.group(1).strip() if color else None,
            "imageRemote": _img_url(card.select_one(".herocard-bg-normal img")),
            "cardImageRemote": _img_url(card.select_one(".herocard-bg-hover img")),
            "wikiUrl": settings.wiki_base + link["href"] if link and link.get("href") else None,
        })
    return heroes


async def _download_images(wiki: Wiki, heroes: list[dict], previous: dict[str, dict]):
    """Download hero images that are new or changed on the wiki."""
    for h in heroes:
        url = h["imageRemote"]
        if not url:
            h["image"] = None
            continue
        ext = os.path.splitext(unquote(urlparse(url).path.split("/revision/")[0]))[1] or ".png"
        rel = f"images/heroes/{h['id']}{ext.lower()}"
        old = previous.get(h["id"], {})
        if storage.path(rel).exists() and old.get("imageRemote") == url:
            h["image"] = "/" + rel
            continue
        try:
            storage.write_bytes(rel, await wiki.download(url))
            h["image"] = "/" + rel
            log.info("Downloaded image: %s", h["name"])
        except WikiError as e:
            log.warning("Image for %s unavailable (%s), using the wiki URL", h["name"], e)
            h["image"] = url


async def update_heroes(wiki: Wiki) -> list[dict]:
    log.info("Fetching the hero list from the wiki")
    html = await wiki.parse_html("Heroes")
    heroes = parse_heroes(html)
    if len(heroes) < 10:  # the page layout probably changed, keep the old data
        raise WikiError(f"Only {len(heroes)} heroes found on the Heroes page, aborting")
    previous = {h["id"]: h for h in (storage.read_json(storage.HEROES_FILE, {}) or {}).get("heroes", [])}
    await _download_images(wiki, heroes, previous)
    heroes.sort(key=lambda h: h["name"].lower())
    storage.write_json(storage.HEROES_FILE, {"updatedAt": storage.now_iso(), "heroes": heroes})
    log.info("Heroes: %d", len(heroes))
    return heroes

