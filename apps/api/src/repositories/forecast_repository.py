from datetime import date, timedelta

_BASE_PRODUCTION: dict[str, float] = {
    "POZO-001": 150.0,
    "POZO-002": 220.0,
    "POZO-003": 95.0,
}

# Exponential decline rate per day (Arps model, simplified)
_DAILY_DECLINE = 0.002


ForecastRow = dict[str, str | float]


def generate(id_well: str, date_start: date, date_end: date) -> list[ForecastRow]:
    base = _BASE_PRODUCTION.get(id_well)
    if base is None:
        return []

    result: list[ForecastRow] = []
    current = date_start
    day = 0

    while current <= date_end:
        prod = round(base * ((1 - _DAILY_DECLINE) ** day), 2)
        result.append({"date": current.isoformat(), "prod": prod})
        current += timedelta(days=1)
        day += 1

    return result
