import asyncio
import logging

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from .config import config
from .handlers import cmd_start, cmd_packages, on_callback, on_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def build_app() -> Application:
    config.validate()

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("packages", cmd_packages))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return app

def main():
    # Важно для PTB на Python 3.11 + run_webhook: должен быть текущий loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = build_app()

    if config.DEBUG:
        logger.info("Starting in polling mode")
        app.run_polling(drop_pending_updates=True)
        return

    logger.info(f"Starting in webhook mode on port {config.PORT}")
    app.run_webhook(
        listen="0.0.0.0",
        port=config.PORT,
        url_path="webhook",
        webhook_url=f"{config.WEBHOOK_URL}/webhook",
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )

if __name__ == "__main__":
    main()
