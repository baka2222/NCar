import asyncio
from conf import bot, dp
from aiogram.types import BotCommand
from handlers.base_commands import base_commands_router
from handlers.menu_handler import menu_router


async def set_commands(bot):
    commands = [
        BotCommand(command="start", description="Регистрация"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="menu", description="Меню"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await set_commands(bot)
    dp.include_router(base_commands_router)
    dp.include_router(menu_router)
    await dp.start_polling(bot, skip_updates=True)


if __name__=='__main__':
    asyncio.run(main())