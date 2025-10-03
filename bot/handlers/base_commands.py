import os
import django
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from aiogram import types
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from asgiref.sync import sync_to_async
from job.models import Customer


base_commands_router = Router()


class Form(StatesGroup):
    phone_number = State()


@base_commands_router.message(Command('help'))
async def help_command_handler(message: types.Message):
    await message.answer('Для помощи обращайтесь - https://wa.me/996507310310')


@base_commands_router.message(Command('start'))
async def start_command_handler(message: types.Message, state: FSMContext):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "Здравствуй! Это бот для учёта финансов NCar. Для проверки учетной записи нажмите на кнопку ниже.",
        reply_markup=kb
    )
    await state.set_state(Form.phone_number)


@base_commands_router.message(Form.phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    if not message.contact or not getattr(message.contact, "phone_number", None):
        await message.answer("Пожалуйста, отправьте номер телефона, используя кнопку.")
        return
    
    def normalize_phone(phone: str) -> str:
        return '+' + ''.join(filter(str.isdigit, phone))

    phone_number = normalize_phone(message.contact.phone_number)

    def _get_customer_by_phone(phone: str):
        return Customer.objects.filter(phone=phone).first()

    customer = await sync_to_async(_get_customer_by_phone, thread_sensitive=True)(phone_number)

    if customer:
        customer.tg_id = str(message.from_user.id)
        await sync_to_async(customer.save, thread_sensitive=True)()

        await state.clear()
        await message.answer(f"Добро пожаловать, {customer.name}! Теперь можете пользоваться ботом.", reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer(
            "Извините, ваш номер телефона не найден в базе данных. Пожалуйста, свяжитесь с администратором.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()
