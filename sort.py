import json
import subprocess, sys, time
import logging
import os

sortsp = []
dep = []
arr = []
notcheck = []

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
logging.info("2️⃣ Начинаем полную сортировку...🚀")
#####Отсев ненужных бортов#####

schedulefile = os.path.join(DATA_DIR, 'schedule.json')
with open(schedulefile, "r", encoding="utf-8") as f:
    air = json.load(f)


for i in range(len(air)):
    company = str(((air[i]).get("flight_number"))[:2])
    status = str((air[i]).get("status"))
    if company not in ("SU", "0E", "UZ", "S7", "FV", "DP", "JP", "5N", "D2", "U6", "RL", "A4", "E7", "UT", "N4", "EO", "B2", "4B") and status == "PLN":
        sortsp.append(air[i])
sortedfile = os.path.join(DATA_DIR, 'sorted.json')
with open(sortedfile, "w", encoding="utf-8") as fxx:
    json.dump(sortsp, fxx, ensure_ascii=False, indent=4)
    print('✅ sorted.json создан')
  
time.sleep(0.5)
#####Отсев интересных бортов#####

with open(sortedfile, "r", encoding="utf-8") as ff:
    air = json.load(ff)
for ij in range(len(air)):
    dest = str(air[ij].get("destination"))
    company = str(((air[ij]).get("flight_number"))[:2])
    aircraft = str((air[ij]).get("aircraft_type"))
    if company in ("WZ", "QE", "U3", "VI", "DZ", "AL", "GL", "FG", "G6", "XX", "JS", "SH", "IR", "W5", "T5", "VN", "R3", "UJ", "YC") or aircraft in ("CCX"):
        if company == "VN" and dest == "SVO":
            arr.append(air[ij])
        if company == "VN" and dest != "SVO":
            dep.append(air[ij])
        notcheck.append(air[ij])
    elif dest == "SVO":
        arr.append(air[ij])
    else:
        dep.append(air[ij])
arrfile = os.path.join(DATA_DIR, 'arr.json')
depfile = os.path.join(DATA_DIR, 'dep.json')
with open(arrfile, "w", encoding="utf-8") as aj:
    json.dump(
        arr,
        aj,
        ensure_ascii=False,
        indent=4
    )
    print('✅ arr.json создан')

with open(depfile, "w", encoding="utf-8") as dj:
    json.dump(
        dep,
        dj,
        ensure_ascii=False,
        indent=4
    )
    print('✅ dep.json создан')
ncfile = os.path.join(DATA_DIR, 'notcheck.json')
with open(ncfile, "w", encoding="utf-8") as nc:
    json.dump(
        notcheck,
        nc,
        ensure_ascii=False,
        indent=4
    )
    print('✅ nocheck.json создан')

endlist = []
with open(ncfile, "r", encoding="utf-8") as fff:
    air = json.load(fff)

for ii in range(len(air)):
    if (air[ii].get("flight_number"))[:2] == 'R3':
        if air[ii].get("aircraft_type") not in ("738", "737", "73H"):
            endlist.append(air[ii])
    elif (air[ii].get("flight_number"))[:2] == 'VN':
        if air[ii].get("aircraft_type") not in ("787", "788", "789"):
            endlist.append(air[ii])
    elif (air[ii].get("flight_number"))[:2] == 'UJ':
        if air[ii].get("aircraft_type") not in ("320", "321", "32N", "32A", "32B", "32Q"):
            endlist.append(air[ii])
    elif (air[ii].get("flight_number"))[:2] == 'YC':
        if air[ii].get("aircraft_type") not in ("320", "321", "32N", "32A", "32B", "32Q"):
            endlist.append(air[ii])
    else:
        endlist.append(air[ii])
splanesfile = os.path.join(DATA_DIR, 'splanes.json')
with open(splanesfile, "w", encoding="utf-8") as spl:
    json.dump(
        endlist,
        spl,
        ensure_ascii=False,
        indent=4
    )
    print('✅ splanes.json создан')


time.sleep(2)
subprocess.run([sys.executable, "fr24_data.py"])
