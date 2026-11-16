"""Skins parsed from the wiki templates "Template:COSMETICS - <Hero> Costumes".

The daily update makes one query for all templates with their latest revision ID
and re-parses only the templates that changed since the previous run.
"""

import logging

from bs4 import BeautifulSoup

from . import storage
from .config import settings
from .wiki import Wiki, WikiError

log = logging.getLogger("skins")

PREFIX = "Template:COSMETICS - "
SUFFIX = " Costumes"

# Template names that differ from the names on the Heroes page
ALIASES = {"hulk": "bruce-banner"}

TAB_TYPES = {"costumes": "costume", "recolors": "recolor"}


# --- Template list ---
async def list_costume_templates(wiki: Wiki) -> dict[str, dict]:
    """Return {hero name from the template title: {title, revid}}."""
    pages = await wiki.query_all(
        generator="allpages", gapnamespace="10", gapprefix=PREFIX.split(":", 1)[1],
        gaplimit="500", prop="revisions", rvprop="ids|timestamp",
    )
    result: dict[str, dict] = {}
    for p in pages:
        title = p.get("title", "")
        if not (title.startswith(PREFIX) and title.endswith(SUFFIX)):
            continue
        revs = p.get("revisions") or []
        name = title[len(PREFIX):-len(SUFFIX)].strip()
        entry = result.setdefault(name, {"title": title, "revid": None})
        if revs:
            entry["revid"] = revs[0].get("revid")
    return result


def match_hero(cosmetics_name: str, heroes: list[dict]) -> dict | None:
    slug = storage.slugify(cosmetics_name)
    by_id = {h["id"]: h for h in heroes}
    if slug in by_id:
        return by_id[slug]
    if slug in ALIASES and ALIASES[slug] in by_id:
        return by_id[ALIASES[slug]]
    # e.g. "Gorr" -> "Gorr The God Butcher"
    candidates = [h for h in heroes if h["id"].startswith(slug + "-")]
    return candidates[0] if len(candidates) == 1 else None


# --- Template parsing ---
def _img_url(item) -> str | None:
    for img in item.select("img.thumbimage"):
        for attr in ("data-src", "src"):
            v = img.get(attr)
            if v and not v.startswith("data:"):
                return v
    return None


def _icon_label(caption, selector: str, prefix: str) -> str | None:
    if not caption:
        return None
    for img in caption.select(selector):
        alt = (img.get("alt") or "").strip()
        if alt.startswith(prefix):
            return alt[len(prefix):].strip() or None
    return None


def parse_template(html: str, hero_id: str, hero_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    labels = [li.get("data-hash") or li.get_text(strip=True) for li in soup.select(".wds-tabs__tab")]
    contents = soup.select(".wds-tab__content")
    sections = list(zip(labels, contents)) if labels and len(labels) == len(contents) else [("Costumes", soup)]

    skins, used_ids = [], set()
    for label, section in sections:
        skin_type = TAB_TYPES.get(label.strip().lower(), storage.slugify(label))
        for item in section.select(".wikia-gallery-item"):
            caption = item.select_one(".lightbox-caption")
            text = caption.select_one(".emote-text") if caption else None
            link = text.select_one("a") if text else None
            name = " ".join(link.get_text().split()) if link else None
            if not name:
                img = item.select_one("img.thumbimage")
                name = (img.get("alt") or "").strip() if img else ""
            if not name:
                continue

            rarity = None
            for cls in (text.get("class") or []) if text else []:
                if cls.startswith("emote-rarity-"):
                    rarity = cls[len("emote-rarity-"):]
            cost_el = caption.select_one(".emote-cost") if caption else None
            cost = " ".join(cost_el.get_text().split()) if cost_el else ""

            sid = f"{hero_id}--{storage.slugify(name)}"
            n = 2
            while sid in used_ids:
                sid = f"{hero_id}--{storage.slugify(name)}-{n}"
                n += 1
            used_ids.add(sid)

            skins.append({
                "id": sid,
                "heroId": hero_id,
                "heroName": hero_name,
                "name": name,
                "type": skin_type,
                "rarity": rarity,
                "isDefault": (rarity or "").lower() == "default",
                "theme": _icon_label(caption, ".charcat-label img", "Theme Icon - "),
                "source": _icon_label(caption, ".charcat-icons img", "Source Icon - "),
                "cost": cost or None,
                "image": _img_url(item),
                "wikiUrl": settings.wiki_base + link["href"] if link and link.get("href") else None,
            })
    return skins


# --- Update ---
async def update_skins(wiki: Wiki, heroes: list[dict], full: bool = False) -> list[str]:
    """Update data/skins.json and return template names with no matching hero."""
    templates = await list_costume_templates(wiki)
    if not templates:
        raise WikiError("The wiki returned no costume templates, aborting")

    state = storage.read_json(storage.STATE_FILE, {}) or {}
    known = state.get("templates", {})
    old = (storage.read_json(storage.SKINS_FILE, {}) or {}).get("skins", [])
    by_hero: dict[str, list[dict]] = {}
    for s in old:
        by_hero.setdefault(s["heroId"], []).append(s)

    unmatched, new_known, current_ids = [], {}, set()
    changed = 0
    for cname, info in sorted(templates.items()):
        hero = match_hero(cname, heroes)
        if not hero:
            unmatched.append(cname)
            hero = {"id": storage.slugify(cname), "name": cname}  # placeholder until the hero list is refreshed
        hid = hero["id"]
        current_ids.add(hid)
        prev = known.get(cname, {})
        up_to_date = (
            not full and prev.get("revid") == info["revid"] and prev.get("heroId") == hid and hid in by_hero
        )
        if up_to_date:
            new_known[cname] = prev
            continue
        try:
            html = await wiki.parse_html(info["title"])
            parsed = parse_template(html, hid, hero["name"])
        except WikiError as e:
            log.error("%s: %s, keeping previous data", cname, e)
            if prev:
                new_known[cname] = prev
            continue
        if not parsed:
            log.warning("%s: no skins found in the template, keeping previous data", cname)
            continue
        by_hero[hid] = parsed
        new_known[cname] = {"revid": info["revid"], "heroId": hid}
        changed += 1
        log.info("%s: %d skins", hero["name"], len(parsed))

    skins = [s for hid in sorted(by_hero) if hid in current_ids for s in by_hero[hid]]
    storage.write_json(storage.SKINS_FILE, {"updatedAt": storage.now_iso(), "skins": skins})
    state["templates"] = new_known
    storage.write_json(storage.STATE_FILE, state)
    log.info(
        "Skins: %d (heroes updated: %d, unchanged: %d)",
        len(skins), changed, len(templates) - changed,
    )
    return unmatched
