def analyze_fr24_data(fr24_data, target_dt, flight_type='arrival'):
    """Возвращает: reg, airline_name, is_special, aircraft_type, date_matched, has_reg"""
    TZ = ZoneInfo('Europe/Moscow')
    if not fr24_data:
        return None, '', False, None, False, False

    target_date_str = target_dt.strftime('%Y-%m-%d') if target_dt else None

    # Сначала ищем запись с известным бортом
    fallback = None  # (reg, airline, is_special, type) — борт известен, но дата/время не сошлись
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
            scheduled_ts = scheduled_dict.get('arrival') or scheduled_dict.get('departure')
        else:
            scheduled_ts = scheduled_dict.get('departure') or scheduled_dict.get('arrival')

        if not scheduled_ts:
            # Борт известен, но времени нет — запомним как fallback
            if fallback is None:
                fallback = (reg, airline_name, is_special, aircraft_type)
            continue

        flight_dt = datetime.fromtimestamp(scheduled_ts, tz=TZ)
        flight_date_str = flight_dt.strftime('%Y-%m-%d')

        if target_date_str and flight_date_str == target_date_str:
            return reg, airline_name, is_special, aircraft_type, True, True

    if fallback:
        # Борт известен, но дата/время не совпали
        return (*fallback, False, True)

    return None, '', False, None, False, False
