from __future__ import annotations

from collections import defaultdict


BreakdownBucket = dict[tuple[int, str, str, str, str, str], list[float]]


def new_bucket() -> BreakdownBucket:
    return defaultdict(lambda: [0.0, 0.0])


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
) -> None:
    value = str(dimension_value or "").strip()
    login = str(login or "").strip().upper()
    if anomes <= 0 or not login or not period or not dimension or not value or volume <= 0:
        return
    key = (anomes, scope, login, period, dimension, value)
    bucket[key][0] += float(successes)
    bucket[key][1] += float(volume)


def materialize(bucket: BreakdownBucket, latest_anomes: int) -> tuple[dict, ...]:
    if latest_anomes <= 0:
        return ()
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows: list[dict] = []
    for (anomes, scope, login, period, dimension, dimension_value), (successes, volume) in sorted(bucket.items()):
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
            }
        )
    return tuple(rows)


def is_night(hour: int | None, turn: object | None = None) -> bool:
    if hour is not None:
        return hour >= 22 or hour <= 5
    return str(turn or "").strip().upper() == "MADRUGADA"
