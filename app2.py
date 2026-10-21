import json
import re
import telebot
import os
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

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)   # ← ИЗМЕНЕНО: создаём папку, если её нет
logfile = os.path.join(DATA_DIR, "bot.log")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GETSCHEDULE_PATH   = os.path.join(BASE_DIR, "getschedule.py")
FLIGHTRADAR24_PATH = os.path.join(BASE_DIR, "flightradar24.py")
TZ = ZoneInfo("Europe/Moscow")

# ← ИЗМЕНЕНО: правильное форматирование print
print(f"Локальное время: {datetime.now()}, UTC: {datetime.now(timezone.utc)}")

bot = telebot.TeleBot(TOKEN, use_class_middlewares=True)
BAN_FILE = os.path.join(DATA_DIR, "banned_users.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
# ← ИЗМЕНЕНО: info.txt и hot-tab.txt — рядом с кодом, а не в DATA_DIR
INFO_FILE = os.path.join(DATA_DIR, "info.txt")
HOTTAB_FILE = os.path.join(DATA_DIR, "hot-tab.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
####################################################################
print(f"[DEBUG] BASE_DIR = {BASE_DIR}")
print(f"[DEBUG] files here: {os.listdir(BASE_DIR)}")
####################################################################
# ───────────────────────────────────────────────────────────
# ALLOW-LIST
# ───────────────────────────────────────────────────────────
ALLOWLIST_FILE = os.path.join(DATA_DIR, "allowlist.json")


def load_allowlist() -> set:
    """Читает allowlist.json. Возвращает set разрешённых user_id."""
    if not os.path.exists(ALLOWLIST_FILE):
        return {MY_CHAT_ID}

    try:
        with open(ALLOWLIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        log.exception("Ошибка чтения allowlist.json")
        return {MY_CHAT_ID}

    if not isinstance(data, dict):
        log.warning("allowlist.json должен быть словарём, получен %s", type(data).__name__)
        return {MY_CHAT_ID}

    allowed = set()
    for key, value in data.items():
        if key.startswith("_"):      # на случай _comment, если захотите
            continue
        if value is True:
            try:
                allowed.add(int(key))
            except ValueError:
                log.warning("Некорректный ID в allowlist.json: %r", key)
    return allowed or {MY_CHAT_ID}


def save_allowlist(ids: set):
    # читаем текущий файл, чтобы не потерять false
    existing = {}
    if os.path.exists(ALLOWLIST_FILE):
        try:
            with open(ALLOWLIST_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    new_data = {}

    # сохраняем явные false
    for key, value in existing.items():
        if key.startswith("_"):
            continue
        if value is False:
            new_data[key] = False

    # добавляем/перезаписываем true
    for uid in sorted(ids):
        new_data[str(uid)] = True

    with open(ALLOWLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)


allowed_user_ids = load_allowlist()


# ───────────────────────────────────────────────────────────
# MIDDLEWARE
# ───────────────────────────────────────────────────────────
class AllowListMiddleware(telebot.BaseMiddleware):
    def __init__(self, allowed_ids: set):
        self.allowed_ids = allowed_ids
        self.update_types = ['message', 'edited_message', 'callback_query']

    def _get_user_id(self, obj):
        user = getattr(obj, "from_user", None)
        return getattr(user, "id", None)

    def _is_private(self, obj) -> bool:
        chat = getattr(obj, "chat", None)
        if chat is not None:
            return chat.type == "private"
        inner = getattr(obj, "message", None)
        if inner is not None:
            return getattr(inner.chat, "type", None) == "private"
        return False

    def pre_process(self, message, data):
        user_id = self._get_user_id(message)
        if user_id in self.allowed_ids:
            return   # разрешён — пропускаем

        # не разрешён — отвечаем только в личке, чтобы не спамить в группах
        if self._is_private(message):
            try:
                bot.send_message(
                    message.chat.id,
                    "🔒 Доступ к боту ограничен.\n"
                    "Если вы считаете, что это ошибка — напишите администратору @RA73220.",
                )
            except Exception:
                log.exception("Не удалось отправить отказ пользователю %s", user_id)

        return SkipHandler()

    def post_process(self, message, data, exception):
        pass


# ───────────────────────────────────────────────────────────
# ПОДКЛЮЧЕНИЕ (порядок важен!)
# ───────────────────────────────────────────────────────────

####################################################################
# Настройки "технических работ"
MAINTENANCE_INTERVALS = [
    (dtime(7, 30), dtime(7, 40)),
    (dtime(12, 30), dtime(12, 40)),
    (dtime(21, 30), dtime(21, 50)),
    (dtime(23, 30), dtime(23, 40)),
]

def is_maintenance_now() -> bool:
    now = datetime.now(TZ).time()
    for start, end in MAINTENANCE_INTERVALS:
        if start <= end:
            if start <= now <= end:
                return True
        else:
            if now >= start or now <= end:
                return True
    return False


# ← ИЗМЕНЕНО: универсальная функция ответа в ту же ветку
def reply(message, text, **kwargs):
    """Отвечает в ту же ветку, где пришло сообщение (для форумов)."""
    thread_id = getattr(message, "message_thread_id", None)
    return bot.send_message(
        message.chat.id,
        text,
        message_thread_id=thread_id,
        **kwargs,
    )


# Middleware для сообщений
class MaintenanceMiddleware(telebot.BaseMiddleware):
    def __init__(self, allowed_thread_id=None, allowed_chat_id=None):
        self.update_types = ['message', 'edited_message']
        self.allowed_thread_id = allowed_thread_id
        self.allowed_chat_id = allowed_chat_id

    def _in_allowed_place(self, message) -> bool:
        """True, если сообщение в личке или в разрешённой ветке разрешённой группы."""
        chat = message.chat
        if chat.type == "private":
            return True
        if self.allowed_chat_id is not None and chat.id != self.allowed_chat_id:
            return False
        return getattr(message, "message_thread_id", None) == self.allowed_thread_id

    def pre_process(self, message, data):
        if not self._in_allowed_place(message):
            return   # не наше место — молча пропускаем, фильтр веток решит дальше
        if is_maintenance_now():
            reply(message, "🛠 Попробуйте позже. Бот обновляет данные. Ещё немного =)")
            return SkipHandler()

    def post_process(self, message, data, exception):
        pass


# Middleware для кнопок
class MaintenanceCallbackMiddleware(telebot.BaseMiddleware):
    def __init__(self, allowed_thread_id=None, allowed_chat_id=None):
        self.update_types = ['callback_query']
        self.allowed_thread_id = allowed_thread_id
        self.allowed_chat_id = allowed_chat_id

    def _in_allowed_place(self, call) -> bool:
        chat = call.message.chat
        if chat.type == "private":
            return True
        if self.allowed_chat_id is not None and chat.id != self.allowed_chat_id:
            return False
        thread_id = getattr(call.message, "message_thread_id", None)
        return thread_id == self.allowed_thread_id

    def pre_process(self, call, data):
        if not self._in_allowed_place(call):
            return
        if is_maintenance_now():
            bot.answer_callback_query(
                call.id,
                "🛠 Идут технические работы. Попробуйте позже.",
                show_alert=True
            )
            return SkipHandler()

    def post_process(self, call, data, exception):
        pass


ALLOWED_THREAD_ID = 231466
ALLOWED_CHAT_ID = -1001571945990


class TopicFilterMiddleware(telebot.BaseMiddleware):
    """Пропускает личку и разрешённую ветку разрешённой группы."""
    def __init__(self, allowed_thread_id, allowed_chat_id=None):
        self.allowed_thread_id = allowed_thread_id
        self.allowed_chat_id = allowed_chat_id
        self.update_types = ['message', 'edited_message', 'callback_query']

    def _get_thread_id(self, obj):
        thread_id = getattr(obj, "message_thread_id", None)
        inner = getattr(obj, "message", None)
        if inner is not None:
            thread_id = getattr(inner, "message_thread_id", thread_id)
        return thread_id

    def pre_process(self, message, data):
        try:
            chat = message.chat

            # ← ИЗМЕНЕНО: админ проходит всегда (опционально)
            sender_id = getattr(getattr(message, "from_user", None), "id", None)
            if sender_id == MY_CHAT_ID:
                return

            # 1. Личка — пропускаем всегда
            if chat.type == "private":
                return

            # 2. Конкретная группа
            if self.allowed_chat_id is not None and chat.id != self.allowed_chat_id:
                return SkipHandler()

            # 3. Конкретная ветка
            if self._get_thread_id(message) != self.allowed_thread_id:
                return SkipHandler()
        except Exception as e:
            log.exception("TopicFilterMiddleware error: %s", e)

    def post_process(self, message, data, exception):
        pass


# Подключение middleware
bot.setup_middleware(AllowListMiddleware(allowed_user_ids))
bot.setup_middleware(MaintenanceMiddleware())
bot.setup_middleware(MaintenanceCallbackMiddleware())
bot.setup_middleware(TopicFilterMiddleware(
    allowed_thread_id=ALLOWED_THREAD_ID,
    allowed_chat_id=ALLOWED_CHAT_ID,
))


####################################################################
def test_scheduler():
    log.warning("ПЛАНИРОВЩИК РАБОТАЕТ: %s", datetime.now())


def run_script(script_path):
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"⏰ Планировщик запускает скрипт: {script_path} в {now_str}")

    with open(logfile, "a", encoding="utf-8") as log_file:
        log_file.write(f"\n{'='*50}\n")
        log_file.write(f"🚀 Запуск {script_path} через планировщик: {now_str}\n")
        log_file.write(f"{'='*50}\n")

        try:
            subprocess.run(
                [sys.executable, script_path],
                stdout=log_file,
                stderr=log_file,
                text=True,
                check=True,
            )
            log_file.write(f"✅ Скрипт {script_path} успешно завершен.\n")
        except subprocess.CalledProcessError as e:
            log_file.write(f"❌ Ошибка в скрипте {script_path} (код: {e.returncode})\n")
        except Exception as e:
            log_file.write(f"❌ Непредвиденная ошибка при запуске {script_path}: {e}\n")


# ← ИЗМЕНЕНО: планировщик создаётся, но start() — внутри main
scheduler = BackgroundScheduler(timezone="Europe/Moscow")

scheduler.add_job(
    run_script,
    CronTrigger(hour=21, minute=30, timezone="Europe/Moscow"),
    args=[GETSCHEDULE_PATH],
    id="one_time_schedule",
    misfire_grace_time=600,
    coalesce=True,
    max_instances=1,
)

scheduler.add_job(
    run_script,
    CronTrigger(hour="7, 12, 23", minute="31", timezone="Europe/Moscow"),
    args=[FLIGHTRADAR24_PATH],
    id="three_matches_per_day",
    misfire_grace_time=600,
    coalesce=True,
    max_instances=1,
)


#####################################################################################
def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        try:
            data = json.load(f)
            if not isinstance(data, dict):   # ← ИЗМЕНЕНО: защита от []
                return {}
            return data
        except json.JSONDecodeError:
            return {}


def save_user(user):
    users = load_users()
    uid = str(user.id)

    if uid not in users:
        users[uid] = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "first_seen": datetime.now(TZ).isoformat(),
        }
    else:
        users[uid]["username"] = user.username
        users[uid]["first_name"] = user.first_name
        users[uid]["last_name"] = user.last_name

    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


#####################################################################################
# --- СПИСОК БАНОВ ---
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


# --- КЛАВИАТУРА ---
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_feedback = types.KeyboardButton("💌Написать админу💌")
    btn_gethot = types.KeyboardButton("🔥Список горячих рейсов🔥")
    btn_info = types.KeyboardButton("📃Информация о боте📃")
    keyboard.row(btn_gethot)
    keyboard.row(btn_info, btn_feedback)
    return keyboard


#####################################################################################
@bot.message_handler(commands=['start'])
def start_cmd(message):
    # ← ИЗМЕНЕНО: reply() вместо send_message()
    reply(message, "Главное меню", reply_markup=get_main_keyboard())
    save_user(message.from_user)


# --- ФИДБЕК ---
@bot.message_handler(func=lambda msg: msg.text == "💌Написать админу💌")
@bot.message_handler(commands=["feedback"])
def handle_feedback_cmd(message):
    user_id = message.chat.id

    if user_id in banned_users:
        reply(message, "🚫 Вы заблокированы и не можете отправлять сообщения.")
        return

    cancel_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cancel_kb.add(types.KeyboardButton("❌ Отмена"))
    msg = reply(
        message,
        "Напишите ваше сообщение для администратора:\n\n"
        "*(Нажмите «❌ Отмена», если передумали)*",
        parse_mode="Markdown",
        reply_markup=cancel_kb,
    )
    bot.register_next_step_handler(msg, process_feedback)


def process_feedback(message):
    user_id = message.chat.id

    if user_id in banned_users:
        return

    if message.text == "❌ Отмена":
        reply(message, "👌 Отправка сообщения отменена.", reply_markup=get_main_keyboard())
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

        keyboard = telebot.types.InlineKeyboardMarkup()
        ban_btn = telebot.types.InlineKeyboardButton(
            text="🚫 Забанить пользователя", callback_data=f"ban_{user_id}"
        )
        keyboard.add(ban_btn)

        bot.send_message(MY_CHAT_ID, caption, parse_mode="Markdown", reply_markup=keyboard)
        reply(message, "✅ Ваше сообщение доставлено!")
    except Exception as e:
        log.exception("Ошибка отправки фидбека: %s", e)
        reply(message, "⚠️ Ошибка при отправке сообщения.")


# --- АДМИН: бан через кнопку ---
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


# --- ИНФО ---
@bot.message_handler(func=lambda msg: msg.text == "📃Информация о боте📃")
@bot.message_handler(commands=["info"])
def send_info(message):
    if os.path.exists(INFO_FILE):
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            sendinfo = f.read()
    else:
        sendinfo = "⚠️ Информация временно недоступна."
    reply(message, sendinfo, disable_web_page_preview=True, parse_mode="HTML")

@bot.message_handler(commands=["allow"], func=lambda m: m.chat.id == MY_CHAT_ID)
def allow_cmd(message):
    try:
        target = int(message.text.split()[1])
        allowed_user_ids.add(target)
        save_allowlist(allowed_user_ids)
        bot.send_message(MY_CHAT_ID, f"✅ `{target}` добавлен в allow-list.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "Использование: `/allow <USER_ID>`", parse_mode="Markdown")


@bot.message_handler(commands=["disallow"], func=lambda m: m.chat.id == MY_CHAT_ID)
def disallow_cmd(message):
    try:
        target = int(message.text.split()[1])
        allowed_user_ids.discard(target)
        save_allowlist(allowed_user_ids)
        bot.send_message(MY_CHAT_ID, f"✅ `{target}` удалён из allow-list.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "Использование: `/disallow <USER_ID>`", parse_mode="Markdown")


# --- ГОРЯЧИЕ РЕЙСЫ ---
@bot.message_handler(func=lambda msg: msg.text == "🔥Список горячих рейсов🔥")
@bot.message_handler(commands=["gethot"])
def send_hot(message):
    if os.path.exists(HOTTAB_FILE):
        with open(HOTTAB_FILE, "r", encoding="utf-8") as f:
            sendhot = f.read()
    else:
        sendhot = "⚠️ Информация временно недоступна."
    reply(message, sendhot, disable_web_page_preview=True, parse_mode="HTML")


# --- БАН / РАЗБАН ---
@bot.message_handler(commands=["ban"], func=lambda msg: msg.chat.id == MY_CHAT_ID)
def ban_command(message):
    try:
        target_id = int(message.text.split()[1])
        banned_users.add(target_id)
        save_banned_users(banned_users)
        bot.send_message(MY_CHAT_ID, f"🚫 Пользователь `{target_id}` забанен.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "⚠️ Использование: `/ban <USER_ID>`", parse_mode="Markdown")


@bot.message_handler(commands=["unban"], func=lambda msg: msg.chat.id == MY_CHAT_ID)
def unban_command(message):
    try:
        target_id = int(message.text.split()[1])
        banned_users.discard(target_id)
        save_banned_users(banned_users)
        bot.send_message(MY_CHAT_ID, f"✅ Пользователь `{target_id}` разбанен.")
    except (IndexError, ValueError):
        bot.send_message(MY_CHAT_ID, "⚠️ Использование: `/unban <USER_ID>`", parse_mode="Markdown")


# --- ОТВЕТ АДМИНА ПОЛЬЗОВАТЕЛЮ ---
@bot.message_handler(func=lambda msg: msg.chat.id == MY_CHAT_ID and msg.reply_to_message)
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
############################################################

@bot.message_handler(commands=['sayall'])
def cmd_sayall(message):
    user_id = message.from_user.id

    # 1. Проверка прав (ИСПРАВЛЕНО)
    if user_id != MY_CHAT_ID:
        bot.reply_to(message, '⛔ У вас нет прав для выполнения этой команды')
        return

    # 2. Получение текста
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, '⚠️ Напишите текст: `/sayall Текст`', parse_mode='Markdown')
        return
    text_to_send = parts[1]

    # 3. Чтение файла
    if not os.path.exists(USERS_FILE):
        bot.reply_to(message, f'❌ Файл `{USERS_FILE}` не найден.')
        return

    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if isinstance(data, dict):
            user_ids = [int(uid) for uid in data.keys()] # ← вот тут магия
        elif isinstance(data, list):
            user_ids = [int(uid) for uid in data]
        else:
            user_ids = []
            
    except Exception as e:
        bot.reply_to(message, f'❌ Ошибка чтения JSON: {e}')
        return

    if not user_ids:
        bot.reply_to(message, '⚠️ Список пользователей пуст.')
        return

    # 4. Рассылка
    status_msg = bot.reply_to(message, f'⏳ Начинаю рассылку для {len(user_ids)} пользователей...')
    
    success_count = 0
    fail_count = 0
    
    for uid in user_ids:
        try:
            # Отправляем без parse_mode, чтобы Markdown в тексте не сломал рассылку
            bot.send_message(uid, text_to_send)
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"Не доставлено {uid}: {e}", flush=True) # Для отладки
            
        time.sleep(0.05) # Защита от лимитов Telegram (не более 20 сообщений в секунду)

    # 5. Отчет
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        text=f'✅ Рассылка завершена.\n\nУспешно: {success_count}\nОшибок: {fail_count}'
    )
############################################################
if __name__ == "__main__":
    print("Бот запущен!")
    print("TZ:", TZ)
    print("Время в TZ:", datetime.now(TZ))
    print("Время сервера:", datetime.now())
    print("Техработы сейчас:", is_maintenance_now())

    scheduler.start()   # ← ИЗМЕНЕНО: start() теперь тут, а не на верхнем уровне
    log.info("Планировщик запущен, задач: %d", len(scheduler.get_jobs()))

    bot.infinity_polling()
