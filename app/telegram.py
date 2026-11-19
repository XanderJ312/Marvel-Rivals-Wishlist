"""Connects the Mini App to the Telegram bot.

The bot's menu button opens the Mini App at PUBLIC_URL or, if it is empty, at the
Cloudflare quick tunnel URL, which changes on every restart and is re-checked
periodically. Messages are received with long polling, so Telegram never has to
reach the tunnel.
"""

import asyncio
import logging

import httpx

from .config import settings

log = logging.getLogger("telegram")

state = {"bot": None, "url": None, "connected": False}

TEXTS = {
    "pl": {
        "start": "Cześć! 👋 Tu znajdziesz wszystkie skiny z Marvel Rivals. Dodawaj do koszyka te, które chcesz kupić, i oznaczaj te, które już masz.",
        "other": "Otwórz aplikację przyciskiem poniżej.",
        "button": "🛒 Otwórz Rivals Wishlist",
        "offline": "Aplikacja właśnie się uruchamia – spróbuj za minutę.",
    },
    "en": {
        "start": "Hi! 👋 Browse every Marvel Rivals skin, add the ones you want to your cart and mark the ones you own.",
        "other": "Open the app with the button below.",
        "button": "🛒 Open Rivals Wishlist",
        "offline": "The app is starting up – please try again in a minute.",
    },
}


class TelegramError(Exception):
    pass


async def _call(client: httpx.AsyncClient, method: str, http_timeout: float = 15, **params):
    # the URL contains the token, so never log it
    try:
        r = await client.post(
            f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/{method}",
            json=params, timeout=http_timeout,
        )
        data = r.json()
    except Exception as e:
        raise TelegramError(f"{method}: cannot reach Telegram ({type(e).__name__})") from None
    if not data.get("ok"):
        raise TelegramError(f"{method}: {data.get('description', r.status_code)}")
    return data["result"]


async def _public_url(client: httpx.AsyncClient) -> str | None:
    if settings.public_url:
        return settings.public_url.rstrip("/")
    if not settings.tunnel_metrics_url:
        return None
    base = settings.tunnel_metrics_url.rstrip("/")
    try:
        # the URL works only once the tunnel has a live connection
        ready = (await client.get(base + "/ready", timeout=3)).json()
        if ready.get("readyConnections", 0) > 0:
            host = (await client.get(base + "/quicktunnel", timeout=3)).json().get("hostname")
            if host:
                return f"https://{host}"
    except Exception:
        pass
    return None


async def _set_menu_button(client: httpx.AsyncClient, url: str) -> bool:
    for attempt in range(1, 6):
        try:
            await _call(
                client, "setChatMenuButton",
                menu_button={"type": "web_app", "text": settings.menu_button_text, "web_app": {"url": url}},
            )
            state.update(url=url, connected=True)
            log.info("Menu button \"%s\" in @%s now opens %s", settings.menu_button_text, state["bot"], url)
            log.info("Open the bot: https://t.me/%s", state["bot"])
            return True
        except TelegramError as e:
            log.warning("Setting the menu button failed (attempt %d/5): %s", attempt, e)
            await asyncio.sleep(5 * attempt)
    return False


async def _watch_url(client: httpx.AsyncClient):
    waiting_logged = False
    while True:
        url = await _public_url(client)
        if not url:
            if not waiting_logged:
                log.info("Waiting for the Cloudflare tunnel")
                waiting_logged = True
        elif not url.startswith("https://"):
            log.error("PUBLIC_URL must start with https://, Telegram does not open other URLs")
            return
        elif url != state["url"] or not state["connected"]:
            if state["url"]:
                log.info("Tunnel URL changed, updating the menu button")
            # a fresh tunnel URL takes a moment to start resolving
            if not settings.public_url:
                await asyncio.sleep(15)
            await _set_menu_button(client, url)
            waiting_logged = False
        if settings.public_url and state["connected"]:
            return  # a permanent URL does not need watching
        await asyncio.sleep(10 if not state["connected"] else 20)


async def _reply(client: httpx.AsyncClient, update: dict):
    msg = update.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return
    t = TEXTS["pl" if (msg.get("from", {}).get("language_code") or "").startswith("pl") else "en"]
    for _ in range(45):  # right after startup the tunnel URL may not be known yet
        if state["url"]:
            break
        await asyncio.sleep(1)
    if not state["url"]:
        await _call(client, "sendMessage", chat_id=chat_id, text=t["offline"])
        return
    text = t["start"] if (msg.get("text") or "").startswith("/start") else t["other"]
    await _call(
        client, "sendMessage", chat_id=chat_id, text=text,
        reply_markup={"inline_keyboard": [[{"text": t["button"], "web_app": {"url": state["url"]}}]]},
    )


async def _poll(client: httpx.AsyncClient):
    offset = 0
    while True:
        try:
            updates = await _call(client, "getUpdates", http_timeout=60,
                                  offset=offset, timeout=50, allowed_updates=["message"])
        except TelegramError as e:
            if "Conflict" in str(e):
                log.error("This bot is already running elsewhere, stop the other instance")
                await asyncio.sleep(30)
            else:
                log.warning("Polling for messages interrupted: %s", e)
                await asyncio.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                await _reply(client, u)
            except Exception as e:
                log.error("Failed to reply: %s", e)


async def run():
    if not settings.telegram_bot_token:
        log.info("TELEGRAM_BOT_TOKEN is not set, running without the bot (browser only)")
        return
    async with httpx.AsyncClient() as client:
        try:
            me = await _call(client, "getMe")
        except TelegramError as e:
            log.error("Invalid bot token or Telegram unreachable: %s", e)
            return
        state["bot"] = me.get("username")
        try:
            await _call(client, "deleteWebhook")  # getUpdates does not work while a webhook is set
            await _call(client, "setMyCommands", commands=[{"command": "start", "description": "Open the app"}])
        except TelegramError as e:
            log.warning("Bot setup: %s", e)
        await asyncio.gather(_watch_url(client), _poll(client))
