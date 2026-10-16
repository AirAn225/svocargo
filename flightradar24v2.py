from datetime import datetime, timedelta
import json
import os
import random
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
import requests
import logging

# Все пути к .json строим от этой директории
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
logging.info("5️⃣ Начинаем проверку Moscow Cargo с FR24 для поиска специальных ливрей... 🚀")

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


def load_json(filepath):
  try:
    with open(filepath, 'r', encoding='utf-8') as f:
      return json.load(f)
  except (FileNotFoundError, json.JSONDecodeError):
    return []


def save_json(filepath, data):
  with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)


def parse_flight_time(time_str):
  TZ = ZoneInfo('Europe/Moscow')
  if not time_str:
    return None
  clean_str = str(time_str).strip()
  formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%H:%M']
  for fmt in formats:
    try:
      if fmt == '%H:%M':
        today = datetime.now(TZ).strftime('%Y-%m-%d')
        return datetime.strptime(f'{today} {clean_str}', '%Y-%m-%d %H:%M')
      return datetime.strptime(clean_str[:19], fmt)
    except ValueError:
      continue
  return None


def fetch_fr24_flight(flight_number):
  clean_num = str(flight_number).replace(' ', '').upper()
  url = (
      f'https://api.flightradar24.com/common/v1/flight/list.json'
      f'?query={clean_num}&fetchBy=flight&page=1&limit=10'
  )

  try:
    time.sleep(random.uniform(2.0, 4.0))
    response = requests.get(url, headers=HEADERS, timeout=7)
    if response.status_code == 200:
      res = response.json().get('result', {}).get('response', {})
      return res.get('data', []) or []
  except Exception as e:
    print(f'❌ Ошибка сети при запросе {clean_num}: {e}')
  return []


def fetch_fr24_by_registration(registration):
  clean_reg = str(registration).strip().upper()
  url = (
      f'https://api.flightradar24.com/common/v1/flight/list.json'
      f'?query={clean_reg}&fetchBy=reg&page=1&limit=10'
  )

  try:
    time.sleep(random.uniform(2.0, 4.0))
    response = requests.get(url, headers=HEADERS, timeout=7)
    if response.status_code == 200:
      res = response.json().get('result', {}).get('response', {})
      return res.get('data', []) or []
  except Exception as e:
    print(f'❌ Ошибка сети при запросе истории борта {clean_reg}: {e}')
  return []


def analyze_fr24_data(fr24_data, target_dt, flight_type='arrival'):
  """Анализирует данные FR24 с проверкой ТОЛЬКО по дате (без проверки времени)."""
  TZ = ZoneInfo('Europe/Moscow')
  if not fr24_data or not target_dt:
    return None, '', False, None, False

  if target_dt.tzinfo is None:
    target_dt = target_dt.replace(tzinfo=TZ)

  target_date_str = target_dt.strftime('%Y-%m-%d')

  for item in fr24_data:
    aircraft_data = item.get('aircraft') or {}
    airline_data = item.get('airline') or {}
    time_data = item.get('time') or {}

    reg = aircraft_data.get('registration')
    if not reg:
      continue

    airline_name = airline_data.get('name') or ''
    model_data = aircraft_data.get('model') or {}
    aircraft_type = model_data.get('code') or aircraft_data.get('code')

    keywords = ['livery', '(', 'special', 'sticker', 'panda', 'expo', 'color']
    is_special = any(kw in airline_name.lower() for kw in keywords)

    scheduled_dict = time_data.get('scheduled', {})

    if flight_type == 'arrival':
      scheduled_ts = scheduled_dict.get('arrival') or scheduled_dict.get(
          'departure'
      )
    else:
      scheduled_ts = scheduled_dict.get('departure') or scheduled_dict.get(
          'arrival'
      )

    if scheduled_ts:
      flight_dt = datetime.fromtimestamp(scheduled_ts, tz=TZ)
      if flight_dt.tzinfo is None:
        flight_dt = flight_dt.replace(tzinfo=TZ)

      flight_date_str = flight_dt.strftime('%Y-%m-%d')

      # Проверяем СТРОГО совпадение даты (игнорируя время)
      if flight_date_str == target_date_str:
        return reg, airline_name, is_special, aircraft_type, True

  return None, '', False, None, False


def normalize_flight_num(raw_num):
  if not raw_num:
    return ''
  clean = str(raw_num).replace(' ', '').upper()
  if len(clean) > 2:
    prefix = clean[:2]
    digits = clean[2:].lstrip('0')
    return prefix + (digits if digits else '0')
  return clean


def get_next_flight_from_reg_history(reg_data, arrival_dt, remaining_departures):
  if not reg_data or not remaining_departures:
    return None

  TZ = ZoneInfo('Europe/Moscow')
  dep_dict = {}
  for dep in remaining_departures:
    raw_num = dep.get('flight_number', '')
    norm_num = normalize_flight_num(raw_num)
    dep_dict[norm_num] = dep

  for item in reg_data:
    identification = item.get('identification') or {}
    number_data = identification.get('number') or {}
    flight_code = number_data.get('default') or identification.get('callsign')

    if not flight_code:
      continue

    norm_fr24_num = normalize_flight_num(flight_code)

    if norm_fr24_num in dep_dict:
      time_data = item.get('time') or {}
      dep_ts = time_data.get('scheduled', {}).get('departure') or time_data.get(
          'estimated', {}
      ).get('departure')

      if dep_ts and arrival_dt:
        dep_dt = datetime.fromtimestamp(dep_ts, tz=TZ)
        if dep_dt.tzinfo is None:
          dep_dt = dep_dt.replace(tzinfo=TZ)
        arrival_dt = arrival_dt.replace(tzinfo=TZ)

        # Здесь сохраняем небольшое логичное условие разворота (вылет не раньше чем за час до прилёта)
        if dep_dt >= arrival_dt - timedelta(hours=1):
          print(f'🔗 Найден разворотный рейс: {flight_code}')
          return dep_dict[norm_fr24_num]
      else:
        return dep_dict[norm_fr24_num]

  return None


def process_flights():
  arr_flights = load_json(ARRIVALS_FILE)
  dep_flights = load_json(DEPARTURES_FILE)
  specials = load_json(SPECIAL_FILE) if os.path.exists(SPECIAL_FILE) else []

  known_special_regs = set()
  remaining_departures = list(dep_flights)
  remaining_arr = []

  print('🚀 Начинаем обработку прилётов...')

  # --- ШАГ 1: ОБРАБОТКА ПРИЛЁТОВ И ПОИСК РАЗВОРОТОВ ---
  for flight in arr_flights:
    raw_num = flight.get('flight_number', '')
    flight_num = normalize_flight_num(raw_num)

    flight_time_str = flight.get('sheduled_time') or flight.get('time')
    target_dt = parse_flight_time(flight_time_str)

    fr24_data = fetch_fr24_flight(flight_num)
    reg, airline_name, is_special, aircraft_type, is_matched = analyze_fr24_data(
        fr24_data, target_dt, flight_type='arrival'
    )

    if is_matched and (is_special or (reg and reg in known_special_regs)):
      if reg:
        known_special_regs.add(reg)

      print(
          f'🔥 Найден спецприлёт {flight_num}: борт {reg} ({airline_name})'
      )
      flight['registration'] = reg
      flight['aircraft_type'] = aircraft_type
      flight['status'] = 'FOUND'
      flight['livery'] = airline_name
      specials.append(flight)
      remaining_arr.append(flight)

      # Ищем разворотный вылет по истории борта
      if reg:
        print(f'🔍 Запрашиваем историю борта {reg} для поиска разворота...')
        reg_history_data = fetch_fr24_by_registration(reg)
        found_dep = get_next_flight_from_reg_history(
            reg_history_data, target_dt, remaining_departures
        )

        if found_dep:
          dep_flight_num = found_dep.get('flight_number')
          print(
              f'✨ Найден разворотный вылет для борта {reg}: рейс'
              f' {dep_flight_num}'
          )

          found_dep['registration'] = reg
          found_dep['aircraft_type'] = aircraft_type
          found_dep['status'] = 'FOUND'
          found_dep['livery'] = airline_name
          specials.append(found_dep)

    elif is_matched and reg:
      print(f'❌ Прилёт {flight_num}: обычный борт ({reg}). Удаляем из расписания.')
    else:
      print(
          f'⏳ Прилёт {flight_num}: борт еще не назначен на FR24. Оставляем.'
      )
      remaining_arr.append(flight)

  print('\n🚀 Обрабатываем оставшиеся вылеты...')

  # --- ШАГ 2: ОБРАБОТКА ОСТАВШИХСЯ ВЫЛЕТОВ ---
  final_remaining_departures = []

  for flight in remaining_departures:
    raw_num = flight.get('flight_number', '')
    flight_num = normalize_flight_num(raw_num)

    flight_time_str = flight.get('sheduled_time') or flight.get('time')
    target_dt = parse_flight_time(flight_time_str)

    fr24_data = fetch_fr24_flight(flight_num)
    reg, airline_name, is_special, aircraft_type, is_matched = analyze_fr24_data(
        fr24_data, target_dt, flight_type='departure'
    )

    if is_matched and (is_special or (reg and reg in known_special_regs)):
      if reg:
        known_special_regs.add(reg)

      print(f'🔥 Найден спецвылет {flight_num}: борт {reg} ({airline_name})')
      flight['registration'] = reg
      flight['aircraft_type'] = aircraft_type
      flight['status'] = 'FOUND'
      flight['livery'] = airline_name
      specials.append(flight)

    elif is_matched and reg:
      print(f'❌ Вылет {flight_num}: обычный борт ({reg}). Удаляем из расписания.')
    else:
      print(
          f'⏳ Вылет {flight_num}: борт еще не назначен на FR24. Оставляем.'
      )
      final_remaining_departures.append(flight)

  # --- СОХРАНЕНИЕ ВСЕХ ФАЙЛОВ ---
  save_json(SPECIAL_FILE, specials)
  save_json(ARRIVALS_FILE, remaining_arr)
  save_json(DEPARTURES_FILE, final_remaining_departures)

  print('\n✅ Обработка завершена! Все файлы успешно обновлены.')


if __name__ == '__main__':
  save_json(SPECIAL_FILE, [])
  process_flights()
  time.sleep(2)
  subprocess.run([sys.executable, 'nocheck.py'])
