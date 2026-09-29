from __future__ import annotations


def format_metric(value: float, unit: str | None) -> str:
    unit = (unit or "percent").lower()
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "number":
        return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value:.1f}"


def format_delta(delta: float, unit: str | None, suffix: str = "vs equipe") -> str:
    unit = (unit or "percent").lower()
    if unit == "percent":
        return f"{delta:+.1f} p.p. {suffix}"
    return f"{delta:+.1f} {suffix}"


def format_target(target: float | None, unit: str | None, direction: str | None) -> str:
    if target is None:
        return "Sem meta configurada"
    signal = "≤" if direction == "lower_is_better" else "≥"
    return f"Meta {signal} {format_metric(float(target), unit)}"
