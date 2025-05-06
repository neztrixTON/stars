import os
import io
import json
import random
import uuid
import requests
import telebot
from telebot import types
from telebot.types import InlineQueryResultArticle, InputTextMessageContent

# ========== Настройки ==========
BOT_TOKEN = '7882534527:AAG0OD69Waw33ENGQgNENs-HJu7ayECto4o'
ADMIN_ID = 1276928573
DEFAULT_USERNAME = 'hi77x'
DB_FILE = 'db.json'

bot = telebot.TeleBot(BOT_TOKEN)

# ========== Загрузка / сохранение БД ==========
if not os.path.exists(DB_FILE):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "permitted_users": [],      # список user_id
            "admin_contact": ADMIN_ID   # контакт админа
        }, f, ensure_ascii=False, indent=2)

with open(DB_FILE, 'r', encoding='utf-8') as f:
    db = json.load(f)


def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# ========== HTTP-заголовки и API-функции ==========
COMMON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ru,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://split.tg",
    "priority": "u=1, i",
    "referer": "https://split.tg/",
    "sec-ch-ua": "\"Not A(Brand\";v=\"8\", \"Chromium\";v=\"132\", \"YaBrowser\";v=\"25.2\", \"Yowser\";v=\"2.5\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 YaBrowser/25.2.0.0 Safari/537.36"
    )
}

def get_invoice(quantity: int, username: str):
    url = "https://api.split.tg/buy/stars"
    payload = {"username": username, "payment_method": "wata_sbp", "quantity": quantity}
    try:
        r = requests.post(url, json=payload, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


def get_recipient_info(username: str):
    url = "https://api.split.tg/recipients/stars"
    payload = {"username": username}
    try:
        r = requests.post(url, json=payload, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None

# ========== Состояния и константы ==========
user_modes    = {}   # chat_id -> "calc" или "purchase"
admin_state   = {}   # ADMIN_ID -> текущее состояние в админ-панели
admin_page    = {}   # ADMIN_ID -> текущая страница списка
PAGE_SIZE     = 5
MIN_QTY       = 50
MAX_QTY       = 15000

# ========== Утилиты и клавиатуры ==========
def is_permitted(cid):
    # Администратор всегда имеет полные права
    return cid == ADMIN_ID or cid in db["permitted_users"]


def get_change_markup(cid):
    # Если пользователь имеет права, в том числе админ, добавить кнопку для смены режима
    if is_permitted(cid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Сменить режим", callback_data="change_mode"))
        return kb
    return None


def send_mode_selection_menu(chat_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Рассчитать цену", callback_data="mode_calc"))
    if is_permitted(chat_id):
        kb.add(types.InlineKeyboardButton("Оформить покупку", callback_data="mode_purchase"))
    bot.send_message(
        chat_id,
        "👋 <b>Выберите режим работы:</b>\n"
        f"• Рассчитать цену (введите число от {MIN_QTY} до {MAX_QTY}).\n"
        + ("• Оформить покупку (доступно вам).\n" if is_permitted(chat_id) else ""),
        parse_mode='HTML',
        reply_markup=kb
    )


def send_admin_menu(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Добавить пользователя", "Удалить пользователя")
    kb.row("Список пользователей", "Сменить контакт")
    kb.row("Выход")
    bot.send_message(
        chat_id,
        "<b>Панель администратора</b>",
        parse_mode='HTML',
        reply_markup=kb
    )


def send_list_page(chat_id, edit=False, message_id=None):
    users = db["permitted_users"]
    total = len(users)
    page = admin_page.get(chat_id, 0)
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    subset = users[start:end]

    text = "<b>Список пользователей:</b>\n"
    for idx, uid in enumerate(subset, start=1+start):
        try:
            chat = bot.get_chat(uid)
            name = chat.first_name or "—"
        except:
            name = "—"
        text += f"{idx}. <a href=\"tg://user?id={uid}\">{name}</a> (ID: {uid})\n"

    kb = types.InlineKeyboardMarkup()
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data="prev_page"))
    if end < total:
        nav.append(types.InlineKeyboardButton("➡️", callback_data="next_page"))
    if nav:
        kb.row(*nav)
    kb.row(
        types.InlineKeyboardButton("Назад", callback_data="back_admin"),
        types.InlineKeyboardButton("Выход", callback_data="exit_admin")
    )

    if edit:
        bot.edit_message_text(text, chat_id, message_id, parse_mode='HTML', reply_markup=kb)
    else:
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=kb)


# ========== Обработчики команд ==========
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    user_modes.pop(msg.chat.id, None)
    send_mode_selection_menu(msg.chat.id)


@bot.message_handler(commands=['admin'])
def cmd_admin(msg):
    cid = msg.chat.id
    if cid != ADMIN_ID:
        kb = types.InlineKeyboardMarkup()
        contact = db.get("admin_contact", ADMIN_ID)
        kb.add(types.InlineKeyboardButton(
            "Связаться с администратором",
            url=f"tg://user?id={contact}"
        ))
        bot.send_message(
            cid,
            "❗ <b>У вас нет прав администратора.</b>\n"
            "Для связи с администратором нажмите кнопку ниже.",
            parse_mode='HTML',
            reply_markup=kb
        )
        return
    admin_state[cid] = 'menu'
    send_admin_menu(cid)


# ========== Обработчик inline-кнопок ==========
@bot.callback_query_handler(func=lambda c: c.data in (
    "mode_calc","mode_purchase","change_mode","cancel_change","confirm_purchase",
    "prev_page","next_page","back_admin","exit_admin"
))
def callback_inline(c):
    cid = c.message.chat.id
    data = c.data

    # Режимы
    if data == "mode_calc":
        user_modes[cid] = "calc"
        # Для сообщений с фото используем edit_message_caption
        if c.message.content_type == 'photo':
            bot.edit_message_caption(
                "✅ <b>Режим: Рассчитать цену</b>\n"
                f"Введите число от {MIN_QTY} до {MAX_QTY}.",
                cid, c.message.message_id,
                reply_markup=get_change_markup(cid),
                parse_mode='HTML'
            )
        else:
            bot.edit_message_text(
                "✅ <b>Режим: Рассчитать цену</b>\n"
                f"Введите число от {MIN_QTY} до {MAX_QTY}.",
                cid, c.message.message_id, parse_mode='HTML',
                reply_markup=get_change_markup(cid)
            )

    elif data == "mode_purchase" and is_permitted(cid):
        user_modes[cid] = "purchase"
        if c.message.content_type == 'photo':
            bot.edit_message_caption(
                "✅ <b>Режим: Оформить покупку</b>\n"
                f"Введите: <code>username количество</code> ({MIN_QTY}–{MAX_QTY}).",
                cid, c.message.message_id,
                reply_markup=get_change_markup(cid),
                parse_mode='HTML'
            )
        else:
            bot.edit_message_text(
                "✅ <b>Режим: Оформить покупку</b>\n"
                f"Введите: <code>username количество</code> ({MIN_QTY}–{MAX_QTY}).",
                cid, c.message.message_id, parse_mode='HTML',
                reply_markup=get_change_markup(cid)
            )

    # Смена режима: исправляем ошибку редактирования сообщения без текстовой части
    elif data == "change_mode" and is_permitted(cid):
        kb = types.InlineKeyboardMarkup()
        # Определяем какие кнопки показывать, в зависимости от текущего режима
        if user_modes.get(cid) == "calc":
            # если текущий режим - расчет цены, то предложим отмену и оформление покупки
            kb.add(
                types.InlineKeyboardButton("Отмена", callback_data="cancel_change"),
                types.InlineKeyboardButton("Оформление", callback_data="confirm_purchase")
            )
        elif user_modes.get(cid) == "purchase":
            # если текущий режим - оформление покупки, то предложим отмену и расчет цены
            kb.add(
                types.InlineKeyboardButton("Отмена", callback_data="cancel_change"),
                types.InlineKeyboardButton("Рассчитать цену", callback_data="mode_calc")
            )
        else:
            # По умолчанию, если режим не установлен, предложим оба варианта
            kb.add(
                types.InlineKeyboardButton("Отмена", callback_data="cancel_change"),
                types.InlineKeyboardButton("Оформление", callback_data="confirm_purchase")
            )

        # Если сообщение было отправлено с фото (например, при оформлении покупки), используем edit_message_caption
        if c.message.content_type == 'photo':
            bot.edit_message_caption(
                "Выберите действие:", cid, c.message.message_id, reply_markup=kb
            )
        else:
            bot.edit_message_text("Выберите действие:", cid, c.message.message_id, reply_markup=kb)

    elif data == "cancel_change":
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=None)
        bot.send_message(
            cid, "❗ <b>Вы отменили смену режима.</b>",
            parse_mode='HTML',
            reply_markup=get_change_markup(cid)
        )

    elif data == "confirm_purchase" and is_permitted(cid):
        user_modes[cid] = "purchase"
        if c.message.content_type == 'photo':
            bot.edit_message_caption(
                "✅ <b>Режим: Оформить покупку</b>\n"
                f"Введите: <code>username количество</code> ({MIN_QTY}–{MAX_QTY}).",
                cid, c.message.message_id, reply_markup=get_change_markup(cid), parse_mode='HTML'
            )
        else:
            bot.edit_message_text(
                "✅ <b>Режим: Оформить покупку</b>\n"
                f"Введите: <code>username количество</code> ({MIN_QTY}–{MAX_QTY}).",
                cid, c.message.message_id, parse_mode='HTML', reply_markup=get_change_markup(cid)
            )

    # Админ: листинг
    elif data in ("prev_page","next_page"):
        page = admin_page.get(cid, 0)
        if data == "prev_page" and page > 0:
            admin_page[cid] = page - 1
        elif data == "next_page":
            maxp = (len(db["permitted_users"]) - 1)//PAGE_SIZE
            if page < maxp:
                admin_page[cid] = page + 1
        send_list_page(cid, edit=True, message_id=c.message.message_id)

    elif data == "back_admin":
        bot.delete_message(cid, c.message.message_id)
        send_admin_menu(cid)
        admin_state[cid] = 'menu'

    elif data == "exit_admin":
        bot.delete_message(cid, c.message.message_id)
        bot.send_message(cid, "🔹 <b>Выход из панели администратора.</b>",
                         parse_mode='HTML',
                         reply_markup=types.ReplyKeyboardRemove())
        admin_state.pop(cid, None)

    bot.answer_callback_query(c.id)


# ========== Обработчик админ‑меню ==========
@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.chat.id in admin_state)
def admin_menu_handler(msg):
    cid = msg.chat.id
    state = admin_state[cid]
    text  = msg.text.strip()

    if state == 'menu':
        if text == "Добавить пользователя":
            admin_state[cid] = 'add'
            bot.send_message(cid, "Введите ID пользователя для добавления:")
        elif text == "Удалить пользователя":
            admin_state[cid] = 'del'
            bot.send_message(cid, "Введите ID пользователя для удаления:")
        elif text == "Список пользователей":
            admin_state[cid] = 'list'
            admin_page[cid] = 0
            send_list_page(cid)
        elif text == "Сменить контакт":
            admin_state[cid] = 'change_contact'
            bot.send_message(cid, "Введите новый ID администратора:")
        elif text == "Выход":
            bot.send_message(cid, "🔹 <b>Выход из панели администратора.</b>",
                             parse_mode='HTML',
                             reply_markup=types.ReplyKeyboardRemove())
            admin_state.pop(cid, None)

    elif state == 'add':
        if not text.isdigit():
            bot.send_message(cid, "❗ Введите числовой ID.")
        else:
            uid = int(text)
            if uid in db["permitted_users"]:
                bot.send_message(cid, "❗ Пользователь уже в списке.")
            else:
                db["permitted_users"].append(uid)
                save_db()
                bot.send_message(cid, f"✔ Пользователь {uid} добавлен.")
            admin_state[cid] = 'menu'
            send_admin_menu(cid)

    elif state == 'del':
        if not text.isdigit():
            bot.send_message(cid, "❗ Введите числовой ID.")
        else:
            uid = int(text)
            if uid not in db["permitted_users"]:
                bot.send_message(cid, "❗ Пользователь не найден.")
            else:
                db["permitted_users"].remove(uid)
                save_db()
                bot.send_message(cid, f"✔ Пользователь {uid} удалён.")
            admin_state[cid] = 'menu'
            send_admin_menu(cid)

    elif state == 'change_contact':
        if not text.isdigit():
            bot.send_message(cid, "❗ Введите числовой ID.")
        else:
            db["admin_contact"] = int(text)
            save_db()
            bot.send_message(cid, f"✔ Контакт администратора обновлён: {text}")
            admin_state[cid] = 'menu'
            send_admin_menu(cid)


# ========== Inline‑запросы ==========
@bot.inline_handler(lambda q: True)
def inline_calc(q):
    query = q.query.strip()
    if not query.isdigit():
        return
    qty = int(query)
    if qty < MIN_QTY or qty > MAX_QTY:
        msg = f"Введите от {MIN_QTY} до {MAX_QTY}"
    else:
        res = get_invoice(qty, DEFAULT_USERNAME)
        if res and res.get("message", {}).get("invoice"):
            inv = res["message"]["invoice"]
            price     = float(inv["amount"])
            per_star  = round(price/qty, 2)
            msg = (f"{qty} ⭐ = {price} {inv.get('currency','RUB')}\n"
                   f"{per_star} за ⭐")
        else:
            msg = "Ошибка расчёта"
    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=msg,
        input_message_content=InputTextMessageContent(msg, parse_mode='HTML')
    )
    bot.answer_inline_query(q.id, [result], cache_time=1)


# ========== Основная логика сообщений ==========
@bot.message_handler(func=lambda m: True)
def process_message(msg):
    cid = msg.chat.id

    # Админ‑меню перехватывается выше
    if cid == ADMIN_ID and cid in admin_state:
        return

    if cid not in user_modes:
        send_mode_selection_menu(cid)
        return

    mode = user_modes[cid]
    text = msg.text.strip()
    waiting = bot.send_message(cid, "🔄 Выполняю запрос…")

    def valid_qty(s):
        return s.isdigit() and MIN_QTY <= int(s) <= MAX_QTY

    # ===== Расчёт цены =====
    if mode == "calc":
        if not valid_qty(text):
            bot.delete_message(cid, waiting.message_id)
            bot.send_message(cid, f"❗ Введите число от {MIN_QTY} до {MAX_QTY}.",
                             reply_markup=get_change_markup(cid))
            return
        qty = int(text)
        res = get_invoice(qty, DEFAULT_USERNAME)
        bot.delete_message(cid, waiting.message_id)
        if not res or not res.get("message", {}).get("invoice"):
            bot.send_message(cid, "🚫 Ошибка расчёта.", reply_markup=get_change_markup(cid))
            return

        inv      = res["message"]["invoice"]
        price    = float(inv["amount"])
        per_star = round(price/qty, 2)
        txt = (f"💰 Цена: <b>{price}</b> {inv.get('currency','RUB')} "
               f"(<i>{per_star}</i> за ⭐)\n")

        if is_permitted(cid):
            rec     = round(price + random.uniform(5,10), 2)
            rec_per = round(rec/qty, 2)
            txt += (f"🔝 Реком.: <b>{rec}</b> {inv.get('currency','RUB')} "
                    f"(<i>{rec_per}</i> за ⭐)")
            bot.send_message(cid, txt, parse_mode='HTML', reply_markup=get_change_markup(cid))
        else:
            bot.send_message(cid, txt, parse_mode='HTML')

    # ===== Оформить покупку =====
    else:
        if not is_permitted(cid):
            bot.delete_message(cid, waiting.message_id)
            bot.send_message(cid, "❗ У вас нет доступа к оформлению покупки.", parse_mode='HTML')
            return

        parts = text.split()
        if len(parts) != 2 or not valid_qty(parts[1]):
            bot.delete_message(cid, waiting.message_id)
            bot.send_message(
                cid,
                f"❗ Введите: <code>username количество</code> ({MIN_QTY}–{MAX_QTY}).",
                parse_mode='HTML', reply_markup=get_change_markup(cid)
            )
            return

        username, qty_str = parts
        qty = int(qty_str)

        rec_info = get_recipient_info(username)
        if not rec_info or "detail" in rec_info:
            err = rec_info.get("detail", {}).get("error_message", "Неизвестная ошибка.")
            bot.delete_message(cid, waiting.message_id)
            bot.send_message(
                cid,
                "<b>Ошибка</b>\n<blockquote expandable>"
                f"{err}"
                "</blockquote>",
                parse_mode='HTML', reply_markup=get_change_markup(cid)
            )
            return

        msg_data = rec_info["message"]
        name      = msg_data.get("name", "—")
        photo_html= msg_data.get("photo", "")
        photo_url = photo_html.split('src="')[1].split('"')[0] if 'src="' in photo_html else None

        inv_res = get_invoice(qty, username)
        bot.delete_message(cid, waiting.message_id)
        if not inv_res or not inv_res.get("message", {}).get("invoice"):
            bot.send_message(cid, "🚫 Ошибка получения счёта.", reply_markup=get_change_markup(cid))
            return

        inv      = inv_res["message"]["invoice"]
        price    = float(inv["amount"])
        per_star = round(price/qty, 2)
        rec      = round(price + random.uniform(5,10), 2)
        rec_per  = round(rec/qty, 2)
        pay_url  = inv.get("url", "")

        caption = (
            "<b>Пользователь:</b>\n"
            "<blockquote>"
            f"Имя: {name}\n"
            f"Юзернейм: @{username}"
            "</blockquote>\n\n"
            f"💰 Цена: {price} {inv.get('currency','RUB')} (<i>{per_star}</i> за ⭐)\n"
            f"🔝 Реком.: {rec} {inv.get('currency','RUB')} (<i>{rec_per}</i> за ⭐)\n\n"
            "👉 Нажмите кнопку «Оплатить»."
        )

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("Оплатить", url=pay_url),
            types.InlineKeyboardButton("Сменить режим", callback_data="change_mode")
        )
        kb.add(types.InlineKeyboardButton("Посмотреть профиль", url=f"https://t.me/{username}"))

        if photo_url:
            try:
                r = requests.get(photo_url, headers=COMMON_HEADERS, timeout=10)
                r.raise_for_status()
                bio = io.BytesIO(r.content)
                bio.name = 'avatar.jpg'
                bot.send_photo(cid, photo=bio, caption=caption, parse_mode='HTML', reply_markup=kb)
            except Exception as e:
                bot.send_message(cid, caption, parse_mode='HTML', reply_markup=kb)
        else:
            bot.send_message(cid, caption, parse_mode='HTML', reply_markup=kb)


if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
