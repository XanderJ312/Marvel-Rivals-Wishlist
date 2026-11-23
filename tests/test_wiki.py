import httpx
import pytest

from app import wiki as wiki_mod
from app.wiki import Wiki, WikiError


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch, data_dir):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(wiki_mod.asyncio, "sleep", instant)


def make_wiki(responses):
    """Wiki client whose HTTP layer returns the given responses one by one."""
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    w = Wiki()
    w._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return w, seen


async def test_api_sends_polite_default_params():
    w, seen = make_wiki([httpx.Response(200, json={"query": {}})])
    await w.api(action="query", list="allpages")

    params = seen[0].url.params
    assert params["format"] == "json"
    assert params["formatversion"] == "2"
    assert params["maxlag"] == "5"
    assert params["list"] == "allpages"
    assert w.requests_made == 1


async def test_user_agent_contains_contact():
    async with Wiki() as w:
        assert "tests@example.com" in w._client.headers["User-Agent"]


async def test_api_retries_on_maxlag_and_rate_limit():
    w, seen = make_wiki([
        httpx.Response(200, json={"error": {"code": "maxlag", "info": "Waiting"}}, headers={"Retry-After": "2"}),
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.ConnectError("offline"),
        httpx.Response(200, json={"ok": True}),
    ])
    assert await w.api(action="query") == {"ok": True}
    assert len(seen) == 4


async def test_api_raises_on_api_error():
    w, _ = make_wiki([httpx.Response(200, json={"error": {"code": "missingtitle", "info": "No page"}})])
    with pytest.raises(WikiError, match="missingtitle"):
        await w.api(action="parse", page="Nope")


async def test_api_raises_on_http_error():
    w, _ = make_wiki([httpx.Response(404)])
    with pytest.raises(WikiError, match="HTTP 404"):
        await w.api(action="parse")


async def test_api_gives_up_after_five_attempts():
    w, seen = make_wiki([httpx.Response(503) for _ in range(5)])
    with pytest.raises(WikiError):
        await w.api(action="query")
    assert len(seen) == 5


async def test_query_all_follows_continuation():
    w, seen = make_wiki([
        httpx.Response(200, json={"query": {"pages": [{"title": "A"}]}, "continue": {"gapcontinue": "B", "continue": "gapcontinue||"}}),
        httpx.Response(200, json={"query": {"pages": [{"title": "B"}]}}),
    ])
    pages = await w.query_all(generator="allpages")
    assert [p["title"] for p in pages] == ["A", "B"]
    assert seen[1].url.params["gapcontinue"] == "B"


async def test_parse_html():
    w, seen = make_wiki([httpx.Response(200, json={"parse": {"text": "<div>hi</div>"}})])
    assert await w.parse_html("Heroes") == "<div>hi</div>"
    assert seen[0].url.params["page"] == "Heroes"


async def test_download_retries_then_returns_bytes():
    w, _ = make_wiki([httpx.Response(503), httpx.Response(200, content=b"PNG")])
    assert await w.download("https://cdn.example/a.png") == b"PNG"


async def test_download_raises_on_missing_image():
    w, _ = make_wiki([httpx.Response(404)])
    with pytest.raises(WikiError):
        await w.download("https://cdn.example/missing.png")


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, 7), ("3", 3), ("0", 1), ("999", 120), ("soon", 7)],
)
def test_retry_after_is_clamped(header, expected):
    headers = {"Retry-After": header} if header is not None else {}
    assert wiki_mod._retry_after(httpx.Response(429, headers=headers), default=7) == expected
