import requests
import json
import os

DATA_DIR = os.getenv('DATA_DIR', '/app/data')
#getcard_path = 'getcard.txt'
#aircraftcard_path = 'aircraft_card.json'
getcard_path = os.path.join(DATA_DIR, 'getcard.txt')
aircraftcard_path = os.path.join(DATA_DIR, 'aircraft_card.json')

API_URL = "https://www.jetapi.dev/api"

with open(getcard_path, "r") as f:
    REGISTRATION = f.read()  # Замени на нужную регистрацию


def get_aircraft_photo(registration):
    params = {
        "reg": registration,
        "photos": 1,
        "only_fr": "true"
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30
        )

        log.info(f"HTTP статус: {response.status_code}")
        log.info(f"Запрос: {response.url}")

        response.raise_for_status()

        data = response.json()

        #print("\nПолный ответ JetAPI:")
        aircraft = data.get("Aircraft", "-")
        livery = data.get("Airline", "-")
        airline = data.get("Operator", "-")
        typecode = data.get("TypeCode", "-")
        mode_s = data.get("ModeS", "-")
        #print(aircraft)
        #print(livery)
        #print(airline)
        #print(typecode)
        #print(mode_s)


    except requests.exceptions.RequestException as error:
        log.error(f"Ошибка запроса: {error}")

    except ValueError:
        log.error("JetAPI вернул ответ, который не удалось прочитать как JSON.")
        log.error(response.text)

    response = requests.get(
        "https://www.jetapi.dev/api",
        params={
            "reg": REGISTRATION,
            "photos": 1,
            "flights": 0,
            "only_jp": "true"
        },
        timeout=30
    )

    data = response.json()
    images = data.get('Images') or []  # None/отсутствие -> []
    url = images[0]['Image'] if images else None

    if url:
        log.info(url)
    else:
        log.warning("Изображений нет")
    #print(REGISTRATION)

    try:
        with open(aircraftcard_path, "r", encoding="utf-8") as file:
            allcards = json.load(file)
        for card in allcards:
            if card.get("registration") == REGISTRATION:
                break
        else:
            allcards.append(
                {
                    "registration": REGISTRATION,
                    "airline": airline,
                    "livery": livery,
                    "aircraft_type": aircraft,
                    "type_code": typecode,
                    "mode_s": mode_s,
                    "photo": url
                }
            )
            with open(aircraftcard_path, 'w', encoding='utf-8') as cardfile:
                json.dump(allcards, cardfile, ensure_ascii=False, indent=2)

    except FileNotFoundError:
        log.error("Ошибка: Файл aircraft_card.json не найден.")
        exit()

if __name__ == "__main__":
    get_aircraft_photo(REGISTRATION)
