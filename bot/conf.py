from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os


load_dotenv()
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("BOT_TOKEN not set in environment variables")

bot = Bot(token=token)
dp = Dispatcher(bot=bot)