from FlightRadarAPI import FlightRadar24API
import json
import os
import time
import random
import subprocess, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging

# Настройка логирования для записи в тот же общий файл
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)

# Теперь вместо print можно писать так (или оставить print, они тоже попадут в лог через subprocess):
logging.info("3️⃣ Получаем данные о чартерах с FlightRadar24...🚀 ")

fr_api = FlightRadar24API()

airport_code = "UUEE"  # Шереметьево (ICAO)
OUTPUT_FILE = "tomorrow_schedule.json"


def fetch_clean_tomorrow_schedule():
    tz_msk = ZoneInfo("Europe/Moscow")

    # Считаем завтрашнюю дату (плюс 1 день)
    tomorrow = datetime.now(tz_msk) + timedelta(hours=2)+timedelta(minutes=35)
    target_date_str = tomorrow.strftime("%Y-%m-%d")

    print(f"🛫 Загружаем чистое расписание для {airport_code} на завтра ({target_date_str})...")

    daily_schedule = {
        "date": target_date_str,
        "airport": airport_code,
        "departures": [],
        "arrivals": []
    }

    for board_type in ["departures", "arrivals"]:
        page = 1
        print(f"\n🔍 Обработка секции [{board_type}]...")

        while page <= 10:
            try:
                time.sleep(random.uniform(1.0, 2.0))
                airport_details = fr_api.get_airport_details(airport_code, page=page)
            except Exception as e:
                print(f"❌ Ошибка на странице {page} для {board_type}: {e}")
                time.sleep(5)
                break

            plugin_data = airport_details.get("airport", {}).get("pluginData", {}).get("schedule", {})
            flights = plugin_data.get(board_type, {}).get("data", [])

            if not flights:
                print(f"🏁 Конец списка для {board_type} на странице {page}.")
                break

            added_count = 0
            for flight_item in flights:
                flight_info = flight_item.get("flight", {}) or {}

                time_info = flight_info.get("time", {}) or {}
                scheduled_block = time_info.get("scheduled", {}) or {}

                sched_ts = None
                if board_type == "departures":
                    sched_ts = scheduled_block.get("departure")
                else:
                    sched_ts = scheduled_block.get("arrival")

                if not sched_ts:
                    continue

                dt = datetime.fromtimestamp(sched_ts, tz=tz_msk)
                flight_date_str = dt.strftime("%Y-%m-%d")

                # Фильтруем строго по завтрашнему дню
                if flight_date_str != target_date_str:
                    continue

                ident = flight_info.get("identification", {}) or {}
                flight_num = ident.get("number", {}).get("default") or ident.get("callsign", "N/A")

                aircraft = flight_info.get("aircraft", {}) or {}
                reg = aircraft.get("registration", "N/A")
                model = aircraft.get("model", {}).get("code", "N/A")

                airline = flight_info.get("airline", {}) or {}
                airline_name = airline.get("name", "N/A")

                airport_info = flight_info.get("airport", {}) or {}
                origin = airport_info.get("origin", {}).get("code", {}).get("iata", "N/A")
                destination = airport_info.get("destination", {}).get("code", {}).get("iata", "N/A")

                clean_flight = {
                    "flight_number": flight_num,
                    "airline": airline_name,
                    "origin": origin,
                    "destination": destination,
                    "registration": reg,
                    "aircraft_type": model,
                    "scheduled_time": dt.strftime("%H:%M"),
                    "status": "Scheduled"
                }

                daily_schedule[board_type].append(clean_flight)
                added_count += 1

            print(f"   📄 Страница {page}: найдено рейсов на завтра — {added_count}")
            page += 1

    # Сохраняем в файл
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(daily_schedule, f, ensure_ascii=False, indent=4)

    total_dep = len(daily_schedule["departures"])
    total_arr = len(daily_schedule["arrivals"])
    print(f"\n✅ Готово! Расписание на завтра сохранено в {OUTPUT_FILE}")
    print(f"   - Вылетов: {total_dep}")
    print(f"   - Прилётов: {total_arr}")


if __name__ == "__main__":
    fetch_clean_tomorrow_schedule()
    time.sleep(2)
    subprocess.run([sys.executable, "fr24_schedule_sort.py"])