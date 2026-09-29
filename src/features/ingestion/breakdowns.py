from __future__ import annotations

from collections import defaultdict


BreakdownBucket = dict[tuple[int, str, str, str, str, str], list[float]]


def new_bucket() -> BreakdownBucket:
    # successes, volume, tma_seconds_sum, tma_count, tmr_seconds_sum, tmr_count
    return defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


def add_ratio(
    bucket: BreakdownBucket,
    *,
    anomes: int,
    scope: str,
    login: str,
    period: str,
    dimension: str,
    dimension_value: object | None,
    successes: float,
    volume: float,
    tma_seconds: float | None = None,
    tmr_seconds: float | None = None,
) -> None:
    value = "" if dimension_value is None else str(dimension_value).strip()
    login = str(login or "").strip().upper()
    if anomes <= 0 or not login or not period or not dimension or not value or volume <= 0:
        return
    key = (anomes, scope, login, period, dimension, value)
    state = bucket[key]
    state[0] += float(successes)
    state[1] += float(volume)
    if tma_seconds is not None and tma_seconds >= 0:
        state[2] += float(tma_seconds)
        state[3] += 1.0
    if tmr_seconds is not None and tmr_seconds >= 0:
        state[4] += float(tmr_seconds)
        state[5] += 1.0


def materialize(bucket: BreakdownBucket, latest_anomes: int) -> tuple[dict, ...]:
    if latest_anomes <= 0:
        return ()
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows: list[dict] = []
    for key, state in sorted(bucket.items()):
        anomes, scope, login, period, dimension, dimension_value = key
        successes, volume, tma_sum, tma_count, tmr_sum, tmr_count = state
        if anomes != latest_anomes or volume <= 0:
            continue
        losses = max(volume - successes, 0.0)
        rows.append(
            {
                "scope": scope,
                "login": login,
                "period": period,
                "data_month": data_month,
                "dimension": dimension,
                "dimension_value": dimension_value,
                "value": round(successes / volume * 100, 1),
                "volume": int(round(volume)),
                "successes": int(round(successes)),
                "losses": int(round(losses)),
                "tma_seconds_sum": float(tma_sum),
                "tma_count": int(round(tma_count)),
                "tmr_seconds_sum": float(tmr_sum),
                "tmr_count": int(round(tmr_count)),
            }
        )
    return tuple(rows)


def is_night(hour: int | None, turn: object | None = None) -> bool:
    if hour is not None:
        return hour >= 22 or hour <= 5
    return str(turn or "").strip().upper() == "MADRUGADA"


def turn_from_hour(hour: int | None) -> str:
    if hour is None:
        return "Madrugada"
    if 6 <= int(hour) <= 13:
        return "Manhã"
    if 14 <= int(hour) <= 21:
        return "Tarde"
    return "Madrugada"


def decimal_hours_to_seconds(value: object | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number * 3600.0


def minutes_to_seconds(value: object | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number * 60.0


def toa_tmr_to_seconds(value: object | None) -> float | None:
    """Replica a heurística do dashboard legado e normaliza TMR para segundos."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    if ":" in raw:
        parts = raw.split(":")
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            numbers = []
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]

    try:
        number = float(raw)
    except ValueError:
        return None
    if number < 0:
        return None
    if number < 1:
        return number * 24 * 3600
    if number < 300:
        return number * 60
    return number
