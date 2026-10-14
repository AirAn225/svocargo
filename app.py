import json
import re
import telebot
import os
from pathlib import Path
from datetime import datetime, time as dtime, timezone, timedelta
from zoneinfo import ZoneInfo
from telebot.handler_backends import SkipHandler
from telebot import types
import logging
import subprocess
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
####################################################################
TOKEN = os.environ["TOKEN"]
MY_CHAT_ID = int(os.environ["MY_CHAT_ID"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GETSCHEDULE_PATH   = os.path.join(BASE_DIR, "getschedule.py")
FLIGHTRADAR24_PATH = os.path.join(BASE_DIR, "flightradar24.py")
TZ = ZoneInfo("Europe/Moscow")
print("Локальное время: %s, UTC: %s", datetime.now(), datetime.now(timezone.utc))
bot = telebot.TeleBot(TOKEN, use_class_middlewares=True)
BAN_FILE = "banned_users.json"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
####################################################################
print(f"[DEBUG] BASE_DIR = {BASE_DIR}")
print(f"[DEBUG] files here: {os.listdir(BASE_DIR)}")
####################################################################
# Настройки "технических работ"
# Список интервалов техработ: [(начало, конец), ...]
MAINTENANCE_INTERVALS = [
    (dtime(3, 0),  dtime(3, 20)),    # ночью
    (dtime(9, 30), dtime(9, 40)),    # утром
    (dtime(21, 30), dtime(21, 50)),  # вечером
    (dtime(23, 30), dtime(23, 50)),   # вечером 2
]

def is_maintenance_now() -> bool:
    now = datetime.now(TZ).time()   # ← время в нужном поясе
    for start, end in MAINTENANCE_INTERVALS:
        if start <= end:
            if start <= now <= end:
                return True
        else:
            if now >= start or now <= end:
                return True
    return False

# Middleware для сообщений
class MaintenanceMiddleware(telebot.BaseMiddleware):
    def __init__(self):
        self.update_types = ['message', 'edited_message']

    def pre_process(self, message, data):
        if is_maintenance_now():
            bot.reply_to(message, f"🛠 Попробуйте позже. Бот обновляет данные. Ещё немного =)")
            return SkipHandler()  # ← вот это остановит хендлер
        # ничего не возвращаем, если работы не идут

    def post_process(self, message, data, exception):
        pass

# Подключаем middleware ко всем сообщениям
bot.setup_middleware(MaintenanceMiddleware())
# Middleware для кнопок
class MaintenanceCallbackMiddleware(telebot.BaseMiddleware):
    def __init__(self):
        self.update_types = ['callback_query']

    def pre_process(self, call, data):
        if is_maintenance_now():
            bot.answer_callback_query(
                call.id,
                "🛠 Идут технические работы. Попробуйте позже.",
                show_alert=True
            )
            return SkipHandler()

    def post_process(self, call, data, exception):
        pass

bot.setup_middleware(MaintenanceCallbackMiddleware())

####################################################################
def test_scheduler():
    log.warning("ПЛАНИРОВЩИК РАБОТАЕТ: %s", datetime.now())
####################################################################
def run_script(script_path):
  TZ = ZoneInfo("Europe/Moscow")
  now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

  print(f"⏰ Планировщик запускает скрипт: {script_path} в {now_str}")

  # Открываем общий файл логов в режиме добавления ('a')
  with open("bot.log", "a", encoding="utf-8") as log_file:
    # Записываем разделитель сеанса в общий файл
    log_file.write(f"\n{'='*50}\n")
    log_file.write(f"🚀 Запуск {script_path} через планировщик: {now_str}\n")
    log_file.write(f"{'='*50}\n")

    try:
      # Запускаем скрипт и перенаправляем stdout и stderr в общий лог-файл
      subprocess.run(
          [sys.executable, script_path],
          stdout=log_file,
          stderr=log_file,
          text=True,
          check=True,
      )
      log_file.write(f"✅ Скрипт {script_path} успешно завершен.\n")

    except subprocess.CalledProcessError as e:
      err_msg = f"❌ Ошибка в скрипте {script_path} (код выхода: {e.returncode})"
      print(err_msg)
      log_file.write(f"{err_msg}\n")
    except Exception as e:
      err_msg = f"❌ Непредвиденная ошибка при запуске {script_path}: {e}"
      print(err_msg)
      log_file.write(f"{err_msg}\n")


scheduler = BackgroundScheduler(timezone="Europe/Moscow")

# --- Задача 1: other_script.py, 6 раз в день ---я

# Задача 1: каждый день в 21:30
scheduler.add_job(
    run_script,
    CronTrigger(hour=21, minute=30, timezone="Europe/Moscow"),
    args=[GETSCHEDULE_PATH],
    id="one_time_schedule",
    misfire_grace_time=600,
    coalesce=True,
    max_instances=1,
)

# Задача 2: каждый день в 03:31, 09:31, 23:31
scheduler.add_job(
    run_script,
    CronTrigger(hour="3, 9, 23", minute="31", timezone="Europe/Moscow"),
    args=[FLIGHTRADAR24_PATH],
    id="three_matches_per_day",
    misfire_grace_time=600,
    coalesce=True,
    max_instances=1,
)

scheduler.start()

#####################################################################################
#####################################################################################
USERS_FILE = "users.json"

def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_user(user):
    users = load_users()
    uid = str(user.id)          # ключи в JSON — только строки

    if uid not in users:
        users[uid] = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "first_seen": datetime.now(TZ).isoformat(),
        }
    else:
        # обновим данные, если поменялись
        users[uid]["username"] = user.username
        users[uid]["first_name"] = user.first_name
        users[uid]["last_name"] = user.last_name

    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
#####################################################################################
#####################################################################################

@bot.message_handler(commands=['start'])
# Главное меню
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "Главное меню",
        reply_markup=get_main_keyboard()
    )
    save_user(message.from_user)
####################################################################
# 1. По команде /feedback переводим пользователя в режим ввода
# --- РАБОТА СО СПИСКОМ БАНОВ ---
def load_banned_users() -> set:
    if os.path.exists(BAN_FILE):
        try:
            with open(BAN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_banned_users(banned_set: set):
    with open(BAN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(banned_set), f, ensure_ascii=False, indent=2)

banned_users = load_banned_users()

# --- ХЕНДЛЕРЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ---
# Главная Клавиатура
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_feedback = types.KeyboardButton("💌Написать админу💌")
    btn_gethot = types.KeyboardButton("🔥Список горячих рейсов🔥")
    btn_info = types.KeyboardButton("📃Информация о боте📃")
    keyboard.row(btn_gethot)
    keyboard.row(btn_info, btn_feedback)
    return keyboard




# Приём обратной связи от пользователей
@bot.message_handler(func=lambda msg: msg.text == "💌Написать админу💌")
@bot.message_handler(commands=["feedback"])
def handle_feedback_cmd(message):
    user_id = message.chat.id

    # Проверка на бан
    if user_id in banned_users:
        bot.send_message(user_id, "🚫 Вы заблокированы и не можете отправлять сообщения.")
        return
    cancel_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cancel_kb.add(types.KeyboardButton("❌ Отмена"))
    msg = bot.send_message(
        user_id,
        "Напишите ваше сообщение для администратора:\n\n"
        "*(Нажмите «❌ Отмена», если передумали)*",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    bot.register_next_step_handler(msg, process_feedback)

# Отмена отправки сообщения
def process_feedback(message):
    user_id = message.chat.id

    if user_id in banned_users:
        return

    if message.text == "❌ Отмена":
        bot.send_message(
            user_id,
            "👌 Отправка сообщения отменена.",
            reply_markup=get_main_keyboard()
        )
        return
    try:
        user_name = message.from_user.first_name or "Пользователь"
        username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "нет username"
        )

        caption = (
            f"📩 **Новое сообщение!**\n"
            f"От: {user_name} ({username})\n"
            f"ID: `{user_id}`\n\n"
            f"💬 **Текст:**\n{message.text}"
        )

        # Кнопка для быстрого бана под сообщением
        keyboard = telebot.types.InlineKeyboardMarkup()
        ban_btn = telebot.types.InlineKeyboardButton(
            text="🚫 Забанить пользователя", callback_data=f"ban_{user_id}"
        )
        keyboard.add(ban_btn)

        bot.send_message(
            MY_CHAT_ID, caption, parse_mode="Markdown", reply_markup=keyboard
        )
        bot.send_message(user_id, "✅ Ваше сообщение доставлено!")

    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        bot.send_message(user_id, "⚠️ Ошибка при отправке сообщения.")


# --- ХЕНДЛЕРЫ ДЛЯ АДМИНИСТРАТОРА ---


# Нажатие на кнопку "Забанить пользователя" под сообщением
@bot.callback_query_handler(func=lambda call: call.data.startswith("ban_"))
def callback_ban_user(call):
    if call.from_user.id != MY_CHAT_ID:
        return

    target_id = int(call.data.split("_")[1])
    banned_users.add(target_id)
    save_banned_users(banned_users)

    bot.answer_callback_query(call.id, text="Пользователь заблокирован!")
    bot.send_message(
        MY_CHAT_ID,
        f"🚫 Пользователь `{target_id}` забанен. Ему запрещено отправлять фидбек.",
        parse_mode="Markdown",
    )

@bot.message_handler(func=lambda msg: msg.text == "📃Информация о боте📃")
@bot.message_handler(commands=["info"])
def send_info(message):
    user_id = message.chat.id
    if os.path.exists('info.txt'):
        with open('info.txt', 'r', encoding='utf-8') as infofile:
            sendinfo = infofile.read()
    else:
        sendinfo = "⚠️ Информация временно недоступна."
    bot.send_message(user_id, sendinfo, disable_web_page_preview=True, parse_mode='HTML')

@bot.message_handler(func=lambda msg: msg.text == "🔥Список горячих рейсов🔥")
@bot.message_handler(commands=["gethot"])
def send_info(message):
    user_id = message.chat.id
    if os.path.exists('hot-tab.txt'):
        with open('hot-tab.txt', 'r', encoding='utf-8') as hotfile:
            sendhot = hotfile.read()
    else:
        sendhot = "⚠️ Информация временно недоступна."
    bot.send_message(user_id, sendhot)



# Ручной бан по команде: /ban 123456789
@bot.message_handler(
    commands=["ban"], func=lambda msg: msg.chat.id == MY_CHAT_ID
)
# Команда бана
def ban_command(message):
    try:
        target_id = int(message.text.split()[1])
        banned_users.add(target_id)
        save_banned_users(banned_users)
        bot.send_message(MY_CHAT_ID, f"🚫 Пользователь `{target_id}` забанен.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "⚠️ Использование: `/ban <USER_ID>`", parse_mode="Markdown")


# Разбан по команде: /unban 123456789
@bot.message_handler(
    commands=["unban"], func=lambda msg: msg.chat.id == MY_CHAT_ID
)
# Команда разбана
def unban_command(message):
    try:
        target_id = int(message.text.split()[1])
        banned_users.discard(target_id)
        save_banned_users(banned_users)
        bot.send_message(MY_CHAT_ID, f"✅ Пользователь `{target_id}` разбанен.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "⚠️ Использование: `/unban <USER_ID>`", parse_mode="Markdown")


# Ответ админа на пересланное сообщение (reply)
@bot.message_handler(
    func=lambda msg: msg.chat.id == MY_CHAT_ID and msg.reply_to_message
)
def reply_to_user(message):
    try:
        reply_msg = message.reply_to_message
        original_text = reply_msg.text or reply_msg.caption or ""

        match = re.search(r"ID:\s*`?(\d+)`?", original_text)
        target_chat_id = None

        if match:
            target_chat_id = int(match.group(1))
        elif reply_msg.forward_from and reply_msg.forward_from.id:
            target_chat_id = reply_msg.forward_from.id

        if target_chat_id is None:
            bot.send_message(
                MY_CHAT_ID,
                "⚠️ Не удалось определить ID. Ответьте на сообщение со строкой `ID: ...`",
                parse_mode="Markdown",
            )
            return

        bot.send_message(
            target_chat_id,
            f"💬 **Ответ администратора:**\n\n{message.text}",
            parse_mode="Markdown",
        )
        bot.send_message(MY_CHAT_ID, "✅ Ответ доставлен!")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ Ошибка: {e}")


if __name__ == "__main__":
    print("Бот запущен!")
    print("TZ:", TZ)
    print("Время в TZ:", datetime.now(TZ))
    print("Время сервера:", datetime.now())
    print("Техработы сейчас:", is_maintenance_now())
    bot.infinity_polling()