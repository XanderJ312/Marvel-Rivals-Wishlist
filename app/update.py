"""Update the data from the wiki by hand.

    python -m app.update                # heroes + skins
    python -m app.update heroes         # heroes only
    python -m app.update skins          # changed skins only
    python -m app.update skins --full   # rebuild all skins
"""

import asyncio
import logging
import sys

from . import storage
from .heroes import update_heroes
from .skins import update_skins
from .wiki import Wiki

log = logging.getLogger("update")


async def run(heroes: bool, skins: bool, full: bool):
    async with Wiki() as wiki:
        if heroes:
            await update_heroes(wiki)
        if skins:
            known = (storage.read_json(storage.HEROES_FILE, {}) or {}).get("heroes", [])
            unmatched = await update_skins(wiki, known, full=full)
            if unmatched:
                log.warning("Templates without a matching hero: %s", ", ".join(unmatched))
        log.info("Wiki requests: %d", wiki.requests_made)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    what = args[0] if args else "all"
    if what not in ("all", "heroes", "skins"):
        print(__doc__)
        sys.exit(1)
    asyncio.run(run(heroes=what in ("all", "heroes"), skins=what in ("all", "skins"), full="--full" in sys.argv))


if __name__ == "__main__":
    main()
