import json
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import logging
import os

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
logging.info("6️⃣ Финальная сортировка и составление hottab.txt...🚀")

TZ = ZoneInfo("Europe/Moscow")
def tomorrow_date():
    tomorrow = datetime.now(TZ) + timedelta(days=1)+timedelta(hours=2)+timedelta(minutes=35)
    return tomorrow.strftime("%d.%m.%Y")

def get_formatted_date():
    # Сдвигаем время на 3 часа назад для смены даты в 21:35
    shifted_now = datetime.now(TZ) + timedelta(hours=2)+timedelta(minutes=35)

    # Форматируем в строку "день-месяц-год"
    return shifted_now.strftime("%d.%m.%Y")
print(datetime.now())

# Текущий результат работы функции:
print(get_formatted_date())
splanesfile = os.path.join(DATA_DIR, 'splanes.json')


try:
    with open(splanesfile, "r", encoding="utf-8") as file:
        data = json.load(file)
except FileNotFoundError:
    print("Ошибка: Файл nocheck.json не найден.")
    exit()

# 2. Шаг 1: Находим самое раннее время для каждой авиакомпании
airline_first_flight = {}

for flight in data:
    code = flight.get("flight_number", "")[:2]
    time = flight.get("sheduled_time", "")

    if code and time:
        # Если авиакомпании еще нет в словаре или нашли рейс еще раньше — обновляем время
        if code not in airline_first_flight or time < airline_first_flight[code]:
            airline_first_flight[code] = time

# 3. Шаг 2: Сортируем список
sorted_data = sorted(
    data,
    key=lambda x: (
        # 1. Время САМОГО ПЕРВОГО рейса этой авиакомпании за день (задает порядок блоков компаний)
        airline_first_flight.get(x.get("flight_number", "")[:2], "9999-12-31 23:59:59"),
        # 2. Код авиакомпании (на случай, если первые рейсы совпали минута в минуту)
        x.get("flight_number", "")[:2],
        # 3. Точное время текущего рейса внутри блока авиакомпании
        x.get("sheduled_time", "")
    )
)

# 4. Записываем отсортированные данные обратно
with open(splanesfile, "w", encoding="utf-8") as file0:
    json.dump(sorted_data, file0, ensure_ascii=False, indent=4)


specialfile = os.path.join(DATA_DIR, 'special.json')
try:
    with open(specialfile, "r", encoding="utf-8") as file1:
        data = json.load(file1)
except FileNotFoundError:
    print("Ошибка: Файл special.json не найден.")
    exit()

# 2. Шаг 1: Находим самое раннее время для каждой авиакомпании
airline_first_flight = {}

for flight in data:
    code = flight.get("flight_number", "")[:2]
    time = flight.get("sheduled_time", "")

    if code and time:
        # Если авиакомпании еще нет в словаре или нашли рейс еще раньше — обновляем время
        if code not in airline_first_flight or time < airline_first_flight[code]:
            airline_first_flight[code] = time

# 3. Шаг 2: Сортируем список
sorted_data = sorted(
    data,
    key=lambda x: (
        # 1. Время САМОГО ПЕРВОГО рейса этой авиакомпании за день (задает порядок блоков компаний)
        airline_first_flight.get(x.get("flight_number", "")[:2], "9999-12-31 23:59:59"),
        # 2. Код авиакомпании (на случай, если первые рейсы совпали минута в минуту)
        x.get("flight_number", "")[:2],
        # 3. Точное время текущего рейса внутри блока авиакомпании
        x.get("sheduled_time", "")
    )
)

# 4. Записываем отсортированные данные обратно
with open(specialfile, "w", encoding="utf-8") as file2:
    json.dump(sorted_data, file2, ensure_ascii=False, indent=4)

print("Табло успешно отсортировано по хронологии авиакомпаний!")

slovar = {"WZ":'Red Wings', "QE":'FARS QESHM', "U3":'Sky Gates', "VI":'Volga-Dnepr',
          "DZ":'Algerian Air', "AL":'TransAviaExport', "GL":'Gelix',"G6":'', "S5":'Abakan Air',
          "XX":'ALPHA CRUX', "JS":'Air Koryo', "SH":'Qeshm Air', "IR":'Iran Air',
          "W5":'Mahan Air', "T5":'Turkmenistan', "VN":'Vietnam Airlines', "R3":'Yakutia', "UJ":'AlMasria', "FG":'Ariana Afghan Airlines',
         "RF":'E-Cargo', "V8":'Atran', "B2":'Belarus - Government (Belavia)'}

page = f'  🗓️ Расписание на {get_formatted_date()} \n ━━━━━━━━━━━━━━━━━━━━ \n  🛬 РЕДКИЕ РЕЙСЫ 🛫 \n ━━━━━━━━━━━━━━━━━━━━ \n \n'
page2 = ' ━━━━━━━━━━━━━━━━━━━━  \n 🎨 СПЕЦЛИВРЕИ ✨ \n ━━━━━━━━━━━━━━━━━━━━ \n \n'
page1_5 = ' ━━━━━━━━━━━━━━━━━━━━  \n ✈️ Табло FLIGHTRADAR24 📡 \n ━━━━━━━━━━━━━━━━━━━━ \n \n'
with open(specialfile, "r", encoding="utf-8") as filespecial:
    airspecial = json.load(filespecial)

with open(splanesfile, "r", encoding="utf-8") as filesplanes:
    airsplanes = json.load(filesplanes)

frsplanesfile = os.path.join(DATA_DIR, 'fr24_splanes.json')

with open(frsplanesfile, "r", encoding="utf-8") as filefrsplanes:
    fr24_splanes = json.load(filefrsplanes)


def get_word(iata):
    # Метод .get() вернет слово, а если буквы нет в словаре — вернет сообщение об ошибке
    return slovar.get(iata.upper(), "Private Owner")

if len(airspecial) == 0:
    page2 = page2 + f'  📭 На {get_formatted_date()} редких ливрей нет.\n \n Подождите, пока бот обновит информацию, или возращайтесь завтра, {tomorrow_date()}!)😊  \n \n'
else:
    for k in airspecial:
        fn = k.get("flight_number")
        iata = k.get("flight_number")[:2]
        aircraft = k.get("aircraft_type")
        time = k.get("estimated_time")[11:]
        livery = k.get("livery")
        route = k.get("origin_destination")
        tag = k.get("status")
        page2 = page2 + f'{iata} · {aircraft}\n  🎨{livery}\n  ▸ {fn}  {route[:3]} ➜ {route[4:]}  🕙  {time[:5]} \n \n'


if len(airsplanes) == 0:
    page = page + f'  📭 На {get_formatted_date()} редких рейсов нет.\n \n Уверен, что {tomorrow_date()} они появятся! \n \n'
else:
    for kk in airsplanes:
        fn = kk.get("flight_number")
        aircraft = kk.get("aircraft_type")
        time = kk.get("estimated_time")[11:]
        iata = kk.get("flight_number")[:2]
        route = kk.get("origin_destination")
        airline = slovar.get(iata, "Private Owner")
        if airline == "Private Owner":
            page = page + f'{airline} · {aircraft}\n  ▸ {fn}  {route[:3]} ➜ {route[4:]}  🕙  {time[:5]} \n \n'
        else:
            page = page + f'{iata} {airline} · {aircraft}\n  ▸ {fn}  {route[:3]} ➜ {route[4:]}  🕙  {time[:5]} \n \n'

if len(fr24_splanes) == 0:
    page1_5 = page1_5 + f'  📭 Пока что даже Лукойла не ожидается( \n Подождите немного, пока информация обновится, или приходите завтра =) \n \n'
else:
    for kkk in fr24_splanes:
        fn = kkk.get("flight_number")
        airline = kkk.get("airline")
        aircraft = kkk.get("aircraft_type")
        reg = kkk.get("registration")
        time = kkk.get("scheduled_time")

        if kkk.get("origin") == "N/A":
            orig = "SVO"
            dest = kkk.get("destination")
        else:
            dest = "SVO"
            orig = kkk.get("origin")

        page1_5 = page1_5 + f'⚠️ {airline} · {aircraft} · {reg}\n  ▸ {fn}  {orig} ➜ {dest}  🕙  {time} \n \n'


endpage = page + page1_5 + page2 + '@uueeappr_bot'
hottabfile = os.path.join(DATA_DIR, 'hot-tab.txt')
with open(hottabfile, 'w', encoding='utf-8') as hottab:
    hottab.write(endpage)
