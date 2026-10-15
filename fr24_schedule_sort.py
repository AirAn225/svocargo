import json
import subprocess, sys, time, os
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
logging.info("4️⃣ Начинаем сортировку данных о чартерах с FR24")
tsfile = os.path.join(DATA_DIR, 'tomorrow_schedule.json')
fr24splanesfile = os.path.join(DATA_DIR, 'fr24_splanes.json')
def sort_schedule_file(filename=tsfile):
    # Загружаем файл
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    endlist = []

    # Сортируем вылеты по времени (scheduled_time)
    for i in data["departures"]:
        airline = i.get("airline")
        if airline in ("Global Sky"):
            endlist.append(i)

    for i in data["arrivals"]:
        airline = i.get("airline")
        if airline in ("Global Sky"):
            endlist.append(i)


    #Перезаписываем отсортированный файл
    with open(fr24splanesfile, "w", encoding="utf-8") as f:
        json.dump(endlist, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    sort_schedule_file()
    time.sleep(2)
    subprocess.run([sys.executable, "flightradar24.py"])
