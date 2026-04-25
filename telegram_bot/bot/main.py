"""Bot entry point."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import get_bot_settings
from bot.handlers import start, optimize, settings, history
from bot.middlewares.auth import AuthMiddleware

logging.basicConfig(level=logging.INFO)


async def main():
    bot_settings = get_bot_settings()
    bot = Bot(
        token=bot_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    auth_mw = AuthMiddleware()
    dp.message.middleware(auth_mw)
    dp.callback_query.middleware(auth_mw)
    dp.include_router(start.router)
    dp.include_router(settings.router)
    dp.include_router(history.router)
    dp.include_router(optimize.router)

    if bot_settings.webhook_url:
        app = web.Application()
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        await web.TCPSite(
            web.AppRunner(app), host="0.0.0.0", port=8080
        ).start()
        await asyncio.Event().wait()
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
