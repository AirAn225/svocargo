import requests
import json
from datetime import datetime, timedelta
import subprocess, sys, time
from zoneinfo import ZoneInfo
import os
import logging


DATA_DIR = os.getenv('DATA_DIR', '/app/data')
logfile = os.path.join(DATA_DIR, 'bot.log')

# Настройка логирования для записи в тот же общий файл
logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)

# Теперь вместо print можно писать так (или оставить print, они тоже попадут в лог через subprocess):
logging.info("1️⃣ Получаем расписание с Moscow Cargo... 🚀")



TZ = ZoneInfo("Europe/Moscow")
def get_formatted_date():
    # Сдвигаем время на 3 часа назад для смены даты в 21:00
    shifted_now = datetime.now(TZ) + timedelta(hours=2)+timedelta(minutes=31)
    tomorrow = shifted_now + timedelta(days=1)
    # Форматируем в строку "день-месяц-год"
    return shifted_now.strftime('%Y-%m-%d')

print(f'Будем искать расписание на {get_formatted_date}')


url_api = 'https://moscow-cargo.com/intapi/schedule'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': 'https://moscow-cargo.com',
    'Referer': 'https://moscow-cargo.com/uslugi/flights'
}

SERVER_LIMIT = 300  # Жесткий лимит сервера


def fetch_flights(dir_type, flight_pattern):
    """Отправляет запрос к API с заданным шаблоном номера рейса"""
    payload = {
        'dir': dir_type,
        'dest': '',
        'ac': '',
        'flight': flight_pattern,
        'date_from': get_formatted_date(),
        'date_to': get_formatted_date(),
        'version': '5.1'
    }
    try:
        res = requests.post(url_api, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            resp = res.json()
            return resp.get('data', []) if isinstance(resp, dict) else resp
    except Exception as e:
        print(f"Ошибка запроса [{dir_type} | '{flight_pattern}']: {e}")
    return []


all_flights = []

print(f"--- Адаптивный сбор всех рейсов на {get_formatted_date()} ---")

for dir_type in ['DEP', 'ARR']:
    print(f"\nНаправление: {dir_type}")

    # Начинаем с однозначных цифр 0-9
    for digit in range(10):
        pattern = str(digit)
        flights = fetch_flights(dir_type, pattern)
        count = len(flights) if isinstance(flights, list) else 0

        # ПРОВЕРКА ГАРАНТИИ: Если получили 300 — значит сработал лимит!
        if count >= SERVER_LIMIT:
            print(f"  ВНИМАНИЕ: Патерн '{pattern}' уперся в лимит 300! Включаем детальное расщепление 10-19...")
            # Автоматически уходим на второй уровень (10, 11, 12 ... 19)
            for sub_digit in range(10):
                sub_pattern = f"{pattern}{sub_digit}"
                sub_flights = fetch_flights(dir_type, sub_pattern)
                if isinstance(sub_flights, list):
                    print(f"    [Уточнение '{sub_pattern}']: получено {len(sub_flights)} рейсов")
                    all_flights.extend(sub_flights)
        else:
            print(f"  Патерн '{pattern}': получено {count} рейсов (Лимит не превышен)")
            if isinstance(flights, list):
                all_flights.extend(flights)

# --- ДЕДУПЛИКАЦИЯ ---
unique_flights = []
seen = set()

for flight in all_flights:
    flight_key = json.dumps(flight, sort_keys=True)
    if flight_key not in seen:
        seen.add(flight_key)
        unique_flights.append(flight)

print(f"\n==========================================")
print(f"ГАРАНТИРОВАННЫЙ ИТОГ: Собрано {len(unique_flights)} уникальных рейсов!")
print(f"==========================================")

filename = os.path.join(DATA_DIR, 'schedule.json')
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(unique_flights, f, ensure_ascii=False, indent=4)


time.sleep(2)
subprocess.run([sys.executable, "sort.py"])
