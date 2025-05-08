import os
import json
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor

# Получение токена из переменных окружения
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise RuntimeError("Не задана переменная окружения BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Загрузка и сохранение JSON
def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Команда /start
@dp.message_handler(commands=['start'])
async def cmd_start(msg: types.Message):
    data = load_json('channels.json')
    text = 'Привет! Выбери канал и тариф для подписки:' + '\n'
    for ch in data['channels']:
        text += f"\n{ch['id']}. {ch['title']}"
    text += '\n\nИспользуй команду /subscribe <номер канала>'
    await msg.answer(text)

# Команда /subscribe
@dp.message_handler(commands=['subscribe'])
async def cmd_subscribe(msg: types.Message):
    args = msg.get_args().split()
    if not args or not args[0].isdigit():
        return await msg.answer('Укажи номер канала: /subscribe <номер канала>')
    ch_id = int(args[0])
    data = load_json('channels.json')
    channel = next((c for c in data['channels'] if c['id'] == ch_id), None)
    if not channel:
        return await msg.answer('Канал не найден.')
    kb = types.InlineKeyboardMarkup()
    for days, pay_link in channel['tariffs'].items():
        kb.add(types.InlineKeyboardButton(f"{days} дней", url=pay_link, callback_data=f"paid:{ch_id}:{days}"))
    await msg.answer(f"Тарифы для «{channel['title']}»: выбери длительность и нажми кнопку:", reply_markup=kb)

# Обработка оплаты (callback)
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('paid:'))
async def cb_paid(call: types.CallbackQuery):
    _, ch_id, days = call.data.split(':')
    ch_id, days = int(ch_id), int(days)
    user_id = call.from_user.id

    channels = load_json('channels.json')['channels']
    channel = next(c for c in channels if c['id'] == ch_id)

    subs_data = load_json('subscriptions.json')
    # Проверяем существующую подписку
    for sub in subs_data['subscriptions']:
        if sub['user_id'] == user_id and sub['channel_id'] == ch_id:
            return await call.answer('У тебя уже есть активная подписка на этот канал!', show_alert=True)

    expire = datetime.utcnow() + timedelta(days=days)
    subs_data['subscriptions'].append({
        'user_id': user_id,
        'channel_id': ch_id,
        'expires_at': expire.isoformat()
    })
    save_json('subscriptions.json', subs_data)

    # Отправляем приглашение
    invite_link = channel['invite_link']
    await bot.send_message(
        user_id,
        f"Оплата за {days} дней прошла успешно!\nПерейди по ссылке, чтобы войти в канал «{channel['title']}»:\n{invite_link}"
    )
    await call.answer()

# Фоновая задача для удаления просроченных подписок
async def cleaner():
    while True:
        await asyncio.sleep(3600)  # проверять раз в час
        subs_data = load_json('subscriptions.json')
        now = datetime.utcnow()
        changed = False
        for sub in subs_data['subscriptions'][:]:
            exp = datetime.fromisoformat(sub['expires_at'])
            if exp < now:
                # Удаляем пользователя из канала
                channels = load_json('channels.json')['channels']
                channel = next(c for c in channels if c['id'] == sub['channel_id'])
                try:
                    await bot.kick_chat_member(chat_id=channel['chat_id'], user_id=sub['user_id'])
                except Exception:
                    pass
                subs_data['subscriptions'].remove(sub)
                changed = True
        if changed:
            save_json('subscriptions.json', subs_data)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(cleaner())
    executor.start_polling(dp, skip_updates=True)
