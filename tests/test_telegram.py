import httpx
import pytest

from app import telegram
from app.config import settings

TOKEN = "123456:SECRET-TOKEN"


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setattr(telegram, "state", {"bot": "rivals_bot", "url": None, "connected": False})
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(settings, "public_url", "")
    monkeypatch.setattr(settings, "tunnel_metrics_url", "")


def client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_call_returns_result():
    def handler(request):
        assert request.url.path == f"/bot{TOKEN}/getMe"
        return httpx.Response(200, json={"ok": True, "result": {"username": "rivals_bot"}})

    async with client_with(handler) as c:
        assert await telegram._call(c, "getMe") == {"username": "rivals_bot"}


async def test_call_errors_never_leak_the_token():
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    async with client_with(handler) as c:
        with pytest.raises(telegram.TelegramError) as exc:
            await telegram._call(c, "getMe")
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None


async def test_call_raises_on_api_error():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    async with client_with(handler) as c:
        with pytest.raises(telegram.TelegramError, match="Unauthorized"):
            await telegram._call(c, "getMe")


async def test_public_url_prefers_configured_address(monkeypatch):
    monkeypatch.setattr(settings, "public_url", "https://rivals.example.com/")
    async with client_with(lambda r: httpx.Response(500)) as c:
        assert await telegram._public_url(c) == "https://rivals.example.com"


async def test_public_url_reads_quick_tunnel_hostname(monkeypatch):
    monkeypatch.setattr(settings, "tunnel_metrics_url", "http://tunnel:2000")

    def handler(request):
        if request.url.path == "/ready":
            return httpx.Response(200, json={"readyConnections": 1})
        return httpx.Response(200, json={"hostname": "abc-def.trycloudflare.com"})

    async with client_with(handler) as c:
        assert await telegram._public_url(c) == "https://abc-def.trycloudflare.com"


async def test_public_url_waits_until_tunnel_is_ready(monkeypatch):
    monkeypatch.setattr(settings, "tunnel_metrics_url", "http://tunnel:2000")
    async with client_with(lambda r: httpx.Response(200, json={"readyConnections": 0})) as c:
        assert await telegram._public_url(c) is None


async def test_public_url_without_tunnel_or_address():
    async with client_with(lambda r: httpx.Response(500)) as c:
        assert await telegram._public_url(c) is None


@pytest.mark.parametrize(
    ("language", "text", "expected_start"),
    [
        ("pl", "/start", "Cześć!"),
        ("en", "/start", "Hi!"),
        ("de", "hello", "Open the app"),
        (None, "/start", "Hi!"),
    ],
)
async def test_reply_sends_mini_app_button_in_users_language(monkeypatch, language, text, expected_start):
    telegram.state["url"] = "https://rivals.example.com"
    sent = []

    async def fake_call(client, method, **params):
        sent.append((method, params))

    monkeypatch.setattr(telegram, "_call", fake_call)
    user = {"language_code": language} if language else {}
    await telegram._reply(None, {"message": {"chat": {"id": 42}, "from": user, "text": text}})

    [(method, params)] = sent
    assert method == "sendMessage"
    assert params["chat_id"] == 42
    assert params["text"].startswith(expected_start)
    [[button]] = params["reply_markup"]["inline_keyboard"]
    assert button["web_app"] == {"url": "https://rivals.example.com"}


async def test_reply_ignores_updates_without_chat(monkeypatch):
    async def fail(*a, **kw):
        raise AssertionError("should not send anything")

    monkeypatch.setattr(telegram, "_call", fail)
    await telegram._reply(None, {"edited_message": {}})


async def test_run_without_token_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    await telegram.run()  # returns immediately instead of polling forever
