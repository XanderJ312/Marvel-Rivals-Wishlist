"""MediaWiki API client for the Marvel Rivals Wiki (Fandom).

Follows https://www.mediawiki.org/wiki/API:Etiquette:
- requests are sequential, never parallel, with `request_delay` between them,
- descriptive User-Agent with a contact,
- maxlag=5, so we back off when the wiki servers are under load,
- 429/503 responses are retried after Retry-After.
"""

import asyncio
import logging
import time

import httpx

from .config import settings

log = logging.getLogger("wiki")


class WikiError(Exception):
    pass


class Wiki:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._last_request = 0.0
        self.requests_made = 0

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent, "Accept-Encoding": "gzip"},
            timeout=30,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def _throttle(self, delay: float | None = None):
        wait = self._last_request + (settings.request_delay if delay is None else delay) - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def api(self, **params) -> dict:
        """Call api.php once, retrying on rate limits and network errors."""
        params = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
        for attempt in range(1, 6):
            await self._throttle()
            self.requests_made += 1
            try:
                r = await self._client.get(settings.api_url, params=params)
            except httpx.TransportError as e:
                log.warning("Cannot reach the wiki (%s), attempt %d/5", type(e).__name__, attempt)
                await asyncio.sleep(5 * attempt)
                continue

            retry_after = _retry_after(r, default=5 * attempt)
            if r.status_code in (429, 503):
                log.warning("Wiki asked us to slow down (%d), waiting %d s", r.status_code, retry_after)
                await asyncio.sleep(retry_after)
                continue
            if r.status_code >= 400:
                raise WikiError(f"HTTP {r.status_code} for {params.get('action')}")

            data = r.json()
            err = data.get("error")
            if err and err.get("code") == "maxlag":
                log.info("Wiki servers are lagging (maxlag), waiting %d s", retry_after)
                await asyncio.sleep(retry_after)
                continue
            if err:
                raise WikiError(f"{err.get('code')}: {err.get('info')}")
            return data
        raise WikiError("No valid response from the wiki after 5 attempts")

    async def query_all(self, **params) -> list[dict]:
        """Run action=query and follow continuation, returning all pages."""
        pages: list[dict] = []
        cont: dict = {}
        while True:
            data = await self.api(action="query", **params, **cont)
            pages.extend(data.get("query", {}).get("pages", []))
            if "continue" not in data:
                return pages
            cont = data["continue"]

    async def parse_html(self, page: str) -> str:
        data = await self.api(action="parse", page=page, prop="text", disablelimitreport="1")
        return data["parse"]["text"]

    async def download(self, url: str) -> bytes:
        """Download an image from the wiki CDN (same throttling as API calls)."""
        for attempt in range(1, 4):
            await self._throttle(settings.image_delay)
            try:
                r = await self._client.get(url)
                if r.status_code == 200:
                    return r.content
                if r.status_code in (429, 503):
                    await asyncio.sleep(_retry_after(r, default=5 * attempt))
                    continue
                raise WikiError(f"HTTP {r.status_code} while downloading an image")
            except httpx.TransportError:
                await asyncio.sleep(3 * attempt)
        raise WikiError("Image download failed")


def _retry_after(r: httpx.Response, default: int) -> int:
    try:
        return max(1, min(120, int(r.headers.get("retry-after", default))))
    except ValueError:
        return default
