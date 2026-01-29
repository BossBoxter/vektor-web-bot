# src/bot.py
from __future__ import annotations

import json
import logging
import uuid
import html
from datetime import datetime, timezone
from typing import Optional

from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from .antispam import AntiSpam
from .config import config
from .handlers import cmd_start, cmd_packages, on_callback, on_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("vektor-web-bot")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_allowed_origins() -> set[str]:
    raw = (config.ALLOWED_ORIGINS or "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


ALLOWED_ORIGINS = _parse_allowed_origins()


def _cors_origin(request: web.Request) -> Optional[str]:
    origin = (request.headers.get("Origin") or "").strip()
    if not origin:
        return None
    if not ALLOWED_ORIGINS:
        return None
    if origin in ALLOWED_ORIGINS:
        return origin
    return None


def _with_cors(request: web.Request, resp: web.StreamResponse) -> web.StreamResponse:
    origin = _cors_origin(request)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Lead-Secret"
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


# Anti-spam for /lead (per IP)
_LEAD_GUARD = AntiSpam(
    ip_capacity=20.0,        # burst
    ip_refill_per_sec=0.7,   # ~1 req / 1.4 sec per IP
    user_capacity=1.0,       # unused here
    user_refill_per_sec=0.1,
)


def build_telegram_app() -> Application:
    config.validate()

    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("packages", cmd_packages))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


async def telegram_webhook_handler(request: web.Request) -> web.Response:
    tg_app: Application = request.app["tg_app"]

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    try:
        update = Update.de_json(data, tg_app.bot)
        await tg_app.process_update(update)
    except Exception:
        log.exception("Failed to process telegram update")
        return web.Response(status=200, text="ok")  # do not retry storms

    return web.Response(status=200, text="ok")


def _sanitize(s: str, limit: int = 2000) -> str:
    s = (s or "").replace("\x00", "").strip()
    if len(s) > limit:
        s = s[:limit]
    return s


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _client_ip(request: web.Request) -> str:
    # Fly header (most common)
    ip = (request.headers.get("Fly-Client-IP") or "").strip()
    if ip:
        return ip
    # fallback
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.remote or "unknown"


async def lead_options(request: web.Request) -> web.Response:
    resp = web.Response(status=204)
    return _with_cors(request, resp)


async def lead_post(request: web.Request) -> web.Response:
    # CORS: only allow known origins if configured
    if ALLOWED_ORIGINS:
        if not _cors_origin(request):
            return web.json_response({"ok": False, "code": "cors_blocked"}, status=403)

    # Optional shared secret
    if config.LEAD_SECRET:
        got = (request.headers.get("X-Lead-Secret") or "").strip()
        if got != config.LEAD_SECRET:
            return web.json_response({"ok": False, "code": "bad_secret"}, status=403)

    # IP rate limit (anti-ddos)
    ip = _client_ip(request)
    ok, retry = _LEAD_GUARD.allow_ip(ip, cost=1.0)
    if not ok:
        resp = web.json_response({"ok": False, "code": "rate_limited", "retry_after": retry}, status=429)
        return _with_cors(request, resp)

    try:
        payload = await request.json()
    except Exception:
        resp = web.json_response({"ok": False, "code": "bad_json"}, status=400)
        return _with_cors(request, resp)

    # Expected fields from site
    name = _sanitize(str(payload.get("name", "")), 120)
    contact = _sanitize(str(payload.get("contact", "")), 200)
    package = _sanitize(str(payload.get("package", "")), 120)
    message = _sanitize(str(payload.get("message", "")), 2500)

    # Optional meta
    page = _sanitize(str(payload.get("page", "")), 300)
    utm = payload.get("utm") if isinstance(payload.get("utm"), dict) else {}
    utm_str = json.dumps(utm, ensure_ascii=False) if utm else ""
    source = _sanitize(str(payload.get("source", "site")), 60)

    # Validation
    if not (contact or message or name):
        resp = web.json_response({"ok": False, "code": "empty"}, status=400)
        return _with_cors(request, resp)

    request_id = uuid.uuid4().hex[:12]
    ua = _sanitize(request.headers.get("User-Agent", ""), 200)

    # Build manager message (HTML-safe)
    lines = [
        "<b>Новая заявка с сайта</b>",
        f"<b>request_id:</b> <code>{_esc(request_id)}</code>",
        f"<b>ts:</b> <code>{_esc(_now_iso())}</code>",
        f"<b>source:</b> {_esc(source)}",
    ]
    if name:
        lines.append(f"<b>Имя:</b> {_esc(name)}")
    if contact:
        lines.append(f"<b>Контакт:</b> {_esc(contact)}")
    if package:
        lines.append(f"<b>Пакет:</b> {_esc(package)}")
    if page:
        lines.append(f"<b>Страница:</b> {_esc(page)}")
    if ip:
        lines.append(f"<b>IP:</b> <code>{_esc(ip)}</code>")
    if ua:
        lines.append(f"<b>UA:</b> <code>{_esc(ua)}</code>")
    if utm_str:
        lines.append(f"<b>UTM:</b> <code>{_esc(_sanitize(utm_str, 1200))}</code>")
    if message:
        lines.append(f"<b>Сообщение:</b>\n{_esc(message)}")

    text_html = "\n".join(lines)

    # Send to manager
    tg_app: Application = request.app["tg_app"]
    if not config.MANAGER_CHAT_ID:
        log.warning("MANAGER_CHAT_ID empty: lead accepted but not delivered. request_id=%s", request_id)
    else:
        try:
            chat_id = int(config.MANAGER_CHAT_ID)
            await tg_app.bot.send_message(
                chat_id=chat_id,
                text=text_html,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            log.exception("Failed to send lead to manager. request_id=%s", request_id)

    resp = web.json_response({"ok": True, "request_id": request_id})
    return _with_cors(request, resp)


async def health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "ts": _now_iso(),
            "webhook": f"{config.WEBHOOK_URL}/webhook" if config.WEBHOOK_URL else "",
            "allowed_origins": sorted(list(ALLOWED_ORIGINS)),
        }
    )


async def on_startup(app: web.Application) -> None:
    tg_app: Application = app["tg_app"]
    await tg_app.initialize()
    await tg_app.start()

    if not config.DEBUG:
        await tg_app.bot.set_webhook(
            url=f"{config.WEBHOOK_URL}/webhook",
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
        log.info("Webhook set: %s/webhook", config.WEBHOOK_URL)


async def on_cleanup(app: web.Application) -> None:
    tg_app: Application = app["tg_app"]
    try:
        await tg_app.stop()
    finally:
        await tg_app.shutdown()


def build_web_app(tg_app: Application) -> web.Application:
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app["tg_app"] = tg_app

    app.router.add_post("/webhook", telegram_webhook_handler)
    app.router.add_route("OPTIONS", "/lead", lead_options)
    app.router.add_post("/lead", lead_post)
    app.router.add_get("/health", health)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    config.validate()

    if config.DEBUG:
        log.info("Starting in polling mode")
        tg_app = build_telegram_app()
        tg_app.run_polling(drop_pending_updates=True)
        return

    tg_app = build_telegram_app()
    web_app = build_web_app(tg_app)

    log.info("Starting HTTP server on 0.0.0.0:%s", config.PORT)
    web.run_app(web_app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
