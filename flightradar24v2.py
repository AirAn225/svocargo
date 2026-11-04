from datetime import datetime, timedelta, timezone
import json
import os
import random
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
import requests
import logging

# ─── НАСТРОЙКИ И ПУТИ ───
DATA_DIR = os.getenv('DATA_DIR', '/app/data')
logfile = os.path.join(DATA_DIR, 'bot.log')
TZ = ZoneInfo('Europe/Moscow')

logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger(__name__)

ARRIVALS_FILE = os.path.join(DATA_DIR, 'arr.json')
DEPARTURES_FILE = os.path.join(DATA_DIR, 'dep.json')
SPECIAL_FILE = os.path.join(DATA_DIR, 'special.json')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.flightradar24.com/',
}

# ─── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ───
def is_expired(dt_input, hours_limit=4):
    """Проверяет, прошло ли больше hours_limit часов с момента dt_input."""
    if isinstance(dt_input, str):
        try:
            dt = datetime.strptime(dt_input, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        except ValueError:
            return False
    else:
        dt = dt_input

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)

    return (datetime.now(TZ) - dt) > timedelta(hours=hours_limit)


def parse_flight_time(time_str):
    """Парсит строку времени и СРАЗУ добавляет часовой пояс."""
    if not time_str:
        return None
    clean_str = str(time_str).strip()
    formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%H:%M']
    for fmt in formats:
        try:
            if fmt == '%H:%M':
                today = datetime.now(TZ).strftime('%Y-%m-%d')
                # Возвращаем aware-datetime
                return datetime.strptime(f'{today} {clean_str}', '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            return datetime.strptime(clean_str[:19], fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def extract_timestamp(time_value):
    """Безопасно извлекает timestamp из ответа FR24 (число или словарь)."""
    if not time_value:
        return None
    if isinstance(time_value, dict):
        return time_value.get('utc') or time_value.get('local')
    if isinstance(time_value, (int, float)):
        return time_value
    if isinstance(time_value, str) and time_value.isdigit():
        return int(time_value)
    return None


def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def fetch_fr24_flight(flight_number):
    clean_num = str(flight_number).replace(' ', '').upper()
    url = f'https://api.flightradar24.com/common/v1/flight/list.json?query={clean_num}&fetchBy=flight&page=1&limit=10'
    try:
        time.sleep(random.uniform(2.0, 4.0)) # Защита от бана
        response = requests.get(url, headers=HEADERS, timeout=7)
        if response.status_code == 200:
            res = response.json().get('result', {}).get('response', {})
            return res.get('data', []) or []
    except Exception as e:
        log.error(f'Ошибка сети при запросе {clean_num}: {e}')
    return []


def extract_registration(item):
    """Ищет борт во всех возможных полях ответа API."""
    reg = (item.get('aircraft') or {}).get('registration')
    if reg: return str(reg).strip().upper()
    
    reg = item.get('reg') or item.get('registration')
    if reg: return str(reg).strip().upper()
    
    reg = (item.get('identification') or {}).get('registration')
    if reg: return str(reg).strip().upper()
    
    return None


def analyze_fr24_data(fr24_data, target_dt, flight_type='arrival'):
    TZ = ZoneInfo('Europe/Moscow')

    if not fr24_data or not target_dt:
        return None, '', False, None, False, False

    # Строка, которую мы ищем (например, "2026-11-03")
    target_date_str = target_dt.strftime('%Y-%m-%d')

    for item in fr24_data:
        time_data = item.get('time') or {}
        
        # 1. Достаем нужный timestamp (прилет или вылет) из вложенного словаря
        key = 'arrival' if flight_type == 'arrival' else 'departure'
        
        scheduled_ts = None
        for category in ['scheduled', 'estimated', 'real']:
            cat_data = time_data.get(category)
            if isinstance(cat_data, dict) and cat_data.get(key):
                scheduled_ts = cat_data[key]
                break
        
        # Если времени нет — идем дальше
        if not scheduled_ts:
            continue
            
        # 2. Проверяем ТОЛЬКО дату
        flight_dt = datetime.fromtimestamp(scheduled_ts, tz=TZ)
        if flight_dt.strftime('%Y-%m-%d') != target_date_str:
            continue

        # 3. Дата совпала! Достаем остальные данные
        aircraft_data = item.get('aircraft') or {}
        reg = aircraft_data.get('registration')
        
        # Если API не знает борт, возвращаем None (в process_flights возьмем из табло)
        if not reg:
            return None, '', False, None, True, False

        airline_name = (item.get('airline') or {}).get('name') or ''
        aircraft_type = (item.get('aircraft') or {}).get('model', {}).get('code')
        
        keywords = ['livery', '(', 'special', 'sticker', 'panda', 'expo', 'color']
        is_special = any(kw in airline_name.lower() for kw in keywords)

        return reg, airline_name, is_special, aircraft_type, True, True

    return None, '', False, None, False, False

def normalize_flight_num(raw_num):
    if not raw_num:
        return ''
    clean = str(raw_num).replace(' ', '').upper()
    if len(clean) > 2:
        prefix = clean[:2]
        digits = clean[2:].lstrip('0')
        return prefix + (digits if digits else '0')
    return clean


# ─── ОСНОВНАЯ ЛОГИКА ───
def process_flights():
    arr_flights = load_json(ARRIVALS_FILE)
    dep_flights = load_json(DEPARTURES_FILE)
    
    # Перезаписываем файл спецливрей с нуля перед обработкой
    specials = [] 
    
    known_special_regs = set()
    remaining_arr = []
    final_remaining_departures = []
    
    log.info('🚀 Начинаем обработку прилётов...')

    # --- ШАГ 1: ОБРАБОТКА ПРИЛЁТОВ ---
    for flight in arr_flights:
        raw_num = flight.get('flight_number', '')
        flight_num = normalize_flight_num(raw_num)

        flight_time_str = flight.get('sheduled_time') or flight.get('time')
        target_dt = parse_flight_time(flight_time_str)

        fr24_data = fetch_fr24_flight(flight_num)

        (reg, airline_name, is_special, aircraft_type, date_matched, has_reg) = analyze_fr24_data(fr24_data, target_dt)

        if has_reg and (is_special or reg in known_special_regs):
            known_special_regs.add(reg)
            log.info(f'🔥 Спецприлёт {flight_num}: {reg} ({airline_name}) | Дата совпала: {date_matched}')
            
            flight.update({
                'registration': reg, 'aircraft_type': aircraft_type,
                'status': 'FOUND', 'livery': airline_name
            })
            specials.append(flight)
            remaining_arr.append(flight)

        elif has_reg and not is_special:
            log.info(f'❌ Прилёт {flight_num}: обычный борт ({reg}). Удаляем.')
            
        else:
            log.info(f'⏳ Прилёт {flight_num}: борт неизвестен. Оставляем.')
            remaining_arr.append(flight)

    log.info('\n🚀 Обрабатываем оставшиеся вылеты...')

    # --- ШАГ 2: ОБРАБОТКА ВЫЛЕТОВ ---
    for flight in dep_flights:
        raw_num = flight.get('flight_number', '')
        flight_num = normalize_flight_num(raw_num)

        flight_time_str = flight.get('sheduled_time') or flight.get('time')
        target_dt = parse_flight_time(flight_time_str)

        fr24_data = fetch_fr24_flight(flight_num)

        (reg, airline_name, is_special, aircraft_type, date_matched, has_reg) = analyze_fr24_data(fr24_data, target_dt)

        if has_reg and (is_special or reg in known_special_regs):
            known_special_regs.add(reg)
            log.info(f'🔥 Спецвылет {flight_num}: {reg} ({airline_name}) | Дата совпала: {date_matched}')
            
            flight.update({
                'registration': reg, 'aircraft_type': aircraft_type,
                'status': 'FOUND', 'livery': airline_name
            })
            specials.append(flight)
            final_remaining_departures.append(flight)

        elif has_reg and not is_special:
            log.info(f'❌ Вылет {flight_num}: обычный борт ({reg}). Удаляем.')

        else:
            log.info(f'⏳ Вылет {flight_num}: борт неизвестен. Оставляем.')
            final_remaining_departures.append(flight)

    # --- СОХРАНЕНИЕ ВСЕХ ФАЙЛОВ ---
    save_json(SPECIAL_FILE, specials)
    save_json(ARRIVALS_FILE, remaining_arr)
    save_json(DEPARTURES_FILE, final_remaining_departures)

    log.info('\n✅ Обработка завершена! Все файлы успешно обновлены.')


if __name__ == '__main__':
    process_flights()
    time.sleep(2)
    subprocess.run([sys.executable, 'nocheck.py'])
