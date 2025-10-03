import os
import django
import sys
from datetime import datetime, date, time
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from io import BytesIO

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from job.models import Customer, JobDays, JobHours, JobOvertimeHours, Advance, Dispute, HourlyRate
from django.core.files import File

menu_router = Router()


def get_employee_menu():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🟢 Приход', callback_data='check_in')],
            [InlineKeyboardButton(text='🔴 Уход', callback_data='check_out')],
            [InlineKeyboardButton(text='⏰ Сверхурочка', callback_data='overtime_menu')],
            [InlineKeyboardButton(text='💰 Аванс', callback_data='advance_request')],
            [InlineKeyboardButton(text='💵 Мои деньги', callback_data='my_money')],
            [InlineKeyboardButton(text='⚡ Подать спор', callback_data='dispute_request')]
        ]
    )


def get_overtime_menu():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🟢 Начать сверхурочку', callback_data='overtime_start')],
            [InlineKeyboardButton(text='🔴 Завершить сверхурочку', callback_data='overtime_end')],
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_main')]
        ]
    )


def get_location_keyboard():
    """Reply keyboard с одной кнопкой, которая запрашивает текущую локацию пользователя."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📍 Отправить текущую', request_location=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


class CheckInStates(StatesGroup):
    waiting_geolocation = State()
    waiting_selfie = State()


class OvertimeStates(StatesGroup):
    waiting_overtime_start = State()
    waiting_overtime_end = State()
    waiting_overtime_proof = State()


class AdvanceStates(StatesGroup):
    waiting_amount = State()
    waiting_reason = State()


class DisputeStates(StatesGroup):
    waiting_reason = State()


@menu_router.message(Command('menu'))
async def show_menu(message: Message):
    customer = await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).first)()

    if customer:
        await message.answer(
            '🏢 Выберите действие:\n\n'
            '🟢 Приход - отметка начала рабочего дня\n'
            '🔴 Уход - отметка окончания рабочего дня\n'
            '⏰ Сверхурочка - работа вне рабочего времени\n'
            '💰 Аванс - запрос аванса\n'
            '💵 Мои деньги - информация о зарплате\n'
            '⚡ Спор - подача спора по отметкам',
            reply_markup=get_employee_menu()
        )
    else:
        await message.answer('❌ Вы не зарегистрированы в системе. Обратитесь к администратору.')


@menu_router.callback_query(F.data == 'back_to_main')
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        '🏢 Выберите действие:',
        reply_markup=get_employee_menu()
    )
    await callback.answer()


@menu_router.callback_query(F.data == 'overtime_menu')
async def overtime_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        '⏰ Управление сверхурочной работой:\n\n'
        '• Начать сверхурочку - запустить учет сверхурочного времени\n'
        '• Завершить сверхурочку - завершить учет\n',
        reply_markup=get_overtime_menu()
    )
    await callback.answer()


@menu_router.callback_query(F.data == 'check_in')
async def start_check_in(callback: CallbackQuery, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=callback.from_user.id).first)()
    if not customer:
        await callback.answer('❌ Вы не зарегистрированы')
        return

    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    if not job_day:
        await callback.answer('❌ Сегодня не рабочий день')
        return

    existing_entry = await sync_to_async(JobHours.objects.filter(customer=customer, date=job_day).first)()
    if existing_entry and existing_entry.work_start:
        await callback.answer('✅ Вы уже отметили приход сегодня')
        return

    await state.set_state(CheckInStates.waiting_geolocation)
    # Отправляем клавиатуру с кнопкой отправки текущей локации
    await callback.message.answer(
        '📍 Нажмите кнопку ниже — отправится ваша текущая локация (это требуется для подтверждения прихода).',
        reply_markup=get_location_keyboard()
    )
    await callback.answer()


@menu_router.message(CheckInStates.waiting_geolocation, F.location)
async def process_geolocation(message: Message, state: FSMContext):
    location = message.location
    geo_url = f"https://maps.google.com/?q={location.latitude},{location.longitude}"

    # Сохраняем в state и просим селфи; убираем клавиатуру
    await state.update_data(geolocation=geo_url)
    await state.set_state(CheckInStates.waiting_selfie)

    await message.answer('📸 Теперь отправьте селфи для подтверждения', reply_markup=ReplyKeyboardRemove())


@menu_router.message(CheckInStates.waiting_selfie, F.photo)
async def process_selfie(message: Message, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).first)()
    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    data = await state.get_data()
    geolocation = data.get('geolocation', '')

    if not customer:
        await message.answer('❌ Вы не зарегистрированы')
        await state.clear()
        return

    if not job_day:
        await message.answer('❌ Сегодня не рабочий день')
        await state.clear()
        return

    # Скачиваем фото
    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    downloaded_file = await message.bot.download_file(file_info.file_path)

    # Создаем имя файла
    filename = f"selfie_{customer.tg_id}_{today.strftime('%Y%m%d_%H%M%S')}.jpg"

    # Создаем объект File для сохранения в ImageField
    image_file = File(BytesIO(downloaded_file.read()), name=filename)

    # Создаем и сохраняем запись
    job_hours = JobHours(
        customer=customer,
        date=job_day,
        work_start=datetime.now().time(),
        geolocation=geolocation,
    )

    # Сначала сохраняем модель
    await sync_to_async(job_hours.save)()
    # Затем сохраняем изображение
    await sync_to_async(job_hours.selfie.save)(filename, image_file, save=True)

    await state.clear()
    # убедимся, что клавиатура убрана
    await message.answer('✅ Приход успешно зарегистрирован!', reply_markup=ReplyKeyboardRemove())
    await show_menu(message)


@menu_router.callback_query(F.data == 'check_out')
async def process_check_out(callback: CallbackQuery):
    customer = await sync_to_async(
        Customer.objects.filter(tg_id=callback.from_user.id).first
    )()
    today = date.today()
    job_day = await sync_to_async(
        JobDays.objects.filter(date=today).first
    )()

    if not job_day:
        await callback.answer('❌ Сегодня не рабочий день')
        return

    job_entry = await sync_to_async(
        JobHours.objects.filter(customer=customer, date=job_day).first
    )()

    if not job_entry:
        await callback.answer('❌ Сначала отметьте приход')
        return

    now_time = datetime.now().time()
    default_end = time(19, 0)

    # Проверяем: если время ухода реально установлено пользователем (не дефолт)
    if job_entry.work_end and job_entry.work_end != default_end:
        await callback.answer('✅ Вы уже отметили уход')
        return

    # Если пользователь хочет уйти раньше 19:00 — фиксируем его время
    if now_time < default_end:
        job_entry.work_end = now_time
        await sync_to_async(job_entry.save)()
        await callback.answer(f'✅ Уход зафиксирован в {now_time.strftime("%H:%M")}')
        return

    # Если позже 19:00 — оставляем дефолтное 19:00
    job_entry.work_end = default_end
    await sync_to_async(job_entry.save)()
    await callback.answer('✅ Авто-уход установлен в 19:00')

    customer = await sync_to_async(Customer.objects.filter(tg_id=callback.from_user.id).first)()
    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    if not job_day:
        await callback.answer('❌ Сегодня не рабочий день')
        return

    job_entry = await sync_to_async(JobHours.objects.filter(customer=customer, date=job_day).first)()

    if not job_entry:
        await callback.answer('❌ Сначала отметьте приход')
        return
    
    now_time = datetime.now().time()

    if job_entry.work_end and now_time > time(19, 0):
        await callback.answer('✅ Вы уже отметили уход сегодня')
        return

    job_entry.work_end = datetime.now().time()
    await sync_to_async(job_entry.save)()

    await callback.answer('✅ Уход успешно зарегистрирован!')


@menu_router.callback_query(F.data == 'overtime_start')
async def start_overtime(callback: CallbackQuery, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=callback.from_user.id).first)()
    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    if not job_day:
        await callback.answer('❌ Сегодня не рабочий день')
        return

    existing_overtime = await sync_to_async(
        JobOvertimeHours.objects.filter(customer=customer, date=job_day, work_end__isnull=True).first
    )()

    if existing_overtime:
        await callback.answer('❌ Сверхурочка уже начата')
        return

    overtime = JobOvertimeHours(
        customer=customer,
        date=job_day,
        work_start=datetime.now().time()
    )
    await sync_to_async(overtime.save)()

    await state.set_state(OvertimeStates.waiting_overtime_end)
    await callback.message.answer(
        '⏰ Сверхурочка начата! Не забудьте завершить её командой "Завершить сверхурочку"'
    )
    await callback.answer()


@menu_router.callback_query(F.data == 'overtime_end')
async def end_overtime(callback: CallbackQuery, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=callback.from_user.id).first)()
    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    overtime = await sync_to_async(
        JobOvertimeHours.objects.filter(customer=customer, date=job_day, work_end__isnull=True).first
    )()

    if not overtime:
        await callback.answer('❌ Нет активной сверхурочки')
        return

    overtime.work_end = datetime.now().time()
    await sync_to_async(overtime.save)()

    await state.set_state(OvertimeStates.waiting_overtime_proof)
    await callback.message.answer(
        '📎 Отправьте комментарий или фото-доказательство сверхурочной работы'
    )
    await callback.answer()


@menu_router.message(OvertimeStates.waiting_overtime_proof)
async def process_overtime_proof(message: Message, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).first)()
    today = date.today()
    job_day = await sync_to_async(JobDays.objects.filter(date=today).first)()

    # Находим последнюю сверхурочку для этого сотрудника и дня
    overtime = await sync_to_async(
        JobOvertimeHours.objects.filter(customer=customer, date=job_day).last
    )()

    if not overtime:
        await message.answer('❌ Не найдено записи сверхурочки')
        await state.clear()
        return

    # Обрабатываем текст или фото
    if message.text:
        overtime.proof = message.text
        await sync_to_async(overtime.save)()
    elif message.photo:
        # Скачиваем фото
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        downloaded_file = await message.bot.download_file(file_info.file_path)

        # Создаем имя файла
        filename = f"overtime_{customer.tg_id}_{today.strftime('%Y%m%d_%H%M%S')}.jpg"

        # Создаем объект File для сохранения в ImageField
        image_file = File(BytesIO(downloaded_file.read()), name=filename)

        # Сохраняем изображение
        await sync_to_async(overtime.selfie.save)(filename, image_file, save=True)

        # Если есть подпись к фото, сохраняем ее как proof
        if message.caption:
            overtime.proof = message.caption
            await sync_to_async(overtime.save)()

    await message.answer('✅ Сверхурочка завершена и отправлена на подтверждение администратору')
    await state.clear()
    await show_menu(message)


@menu_router.callback_query(F.data == 'advance_request')
async def start_advance_request(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdvanceStates.waiting_amount)
    await callback.message.answer('💰 Введите сумму аванса:')
    await callback.answer()


@menu_router.message(AdvanceStates.waiting_amount, F.text)
async def process_advance_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0:
            await message.answer('❌ Сумма должна быть положительной')
            return

        await state.update_data(amount=amount)
        await state.set_state(AdvanceStates.waiting_reason)
        await message.answer('📝 Укажите причину запроса аванса:')

    except ValueError:
        await message.answer('❌ Введите корректную сумму')


@menu_router.message(AdvanceStates.waiting_reason, F.text)
async def process_advance_reason(message: Message, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).first)()
    data = await state.get_data()
    amount = data.get('amount')

    advance = Advance(
        customer=customer,
        amount=amount,
        reason=message.text
    )
    await sync_to_async(advance.save)()

    await state.clear()
    await message.answer('✅ Запрос на аванс отправлен на рассмотрение администратору')
    await show_menu(message)


@menu_router.callback_query(F.data == 'my_money')
async def show_my_money(callback: CallbackQuery):
    customer = await sync_to_async(Customer.objects.filter(tg_id=callback.from_user.id).first)()

    if not customer:
        await callback.answer('❌ Вы не зарегистрированы')
        return

    # Используем индивидуальную ставку, если задана; иначе — глобальную
    if customer.hourly_rate is not None:
        rate = customer.hourly_rate
    else:
        hourly_rate_obj = await sync_to_async(HourlyRate.load)()
        rate = hourly_rate_obj.cash_per_hour

    paid_hours = await sync_to_async(
        lambda: sum(jh.work_hours for jh in JobHours.objects.filter(customer=customer, paid=True))
    )()

    unpaid_hours = await sync_to_async(
        lambda: sum(jh.work_hours for jh in JobHours.objects.filter(customer=customer, paid=False))
    )()

    paid_overtime = await sync_to_async(
        lambda: sum(jh.work_hours for jh in JobOvertimeHours.objects.filter(customer=customer, paid=True))
    )()

    unpaid_overtime = await sync_to_async(
        lambda: sum(jh.work_hours for jh in JobOvertimeHours.objects.filter(customer=customer, paid=False))
    )()

    advances = await sync_to_async(
        lambda: sum(adv.amount for adv in Advance.objects.filter(customer=customer, accepted=True))
    )()

    total_earned = (paid_hours + unpaid_hours + paid_overtime + unpaid_overtime) * rate
    current_balance = customer.balance

    text = (
        f'💵 Ваши финансы:\n\n'
        f'📊 Отработано часов: {paid_hours + unpaid_hours:.1f}ч\n'
        f'⏰ Сверхурочные: {paid_overtime + unpaid_overtime:.1f}ч\n'
        f'💰 Начислено: {total_earned:.2f} сом\n'
        f'💸 Выдано авансов: {advances:.2f} сом\n'
        f'💳 Текущий баланс: {current_balance:.2f} сом\n\n'
        f'*Ставка: {rate} сом/час'
    )

    await callback.message.answer(text)
    await callback.answer()


@menu_router.callback_query(F.data == 'dispute_request')
async def start_dispute(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DisputeStates.waiting_reason)
    await callback.message.answer('⚡ Опишите причину спора (проблему с отметками, расчетами и т.д.):')
    await callback.answer()


@menu_router.message(DisputeStates.waiting_reason, F.text)
async def process_dispute_reason(message: Message, state: FSMContext):
    customer = await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).first)()

    dispute = Dispute(
        customer=customer,
        reason=message.text
    )
    await sync_to_async(dispute.save)()

    await state.clear()
    await message.answer('✅ Спор отправлен на рассмотрение. Администратор свяжется с вами.')
    await show_menu(message)


@menu_router.message(Command('cancel'))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer('❌ Действие отменено', reply_markup=ReplyKeyboardRemove())
    await show_menu(message)
