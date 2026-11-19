"""Update the data from the wiki by hand.

    python -m app.update                # whatever is due
    python -m app.update all            # heroes + skins
    python -m app.update heroes         # heroes only
    python -m app.update skins          # changed skins only
    python -m app.update skins --full   # rebuild all skins
"""

import asyncio
import logging
import sys

from . import updater


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    full = "--full" in sys.argv
    what = args[0] if args else "auto"
    if what not in ("auto", "all", "heroes", "skins"):
        print(__doc__)
        sys.exit(1)
    if what == "auto":
        asyncio.run(updater.run(scheduled=True))
    else:
        asyncio.run(updater.run(
            heroes=what in ("all", "heroes"),
            skins=what in ("all", "skins"),
            full=full or what == "all",
        ))


if __name__ == "__main__":
    main()
