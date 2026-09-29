from __future__ import annotations


def build_tips(individual: list[dict], team_averages: list[dict]) -> list[str]:
    if not individual:
        return ["Ainda não há dados individuais processados para este segmento."]

    avg_index = {(row["period"], row["indicator_key"]): row for row in team_averages}
    tips: list[str] = []
    for row in individual[:6]:
        team = avg_index.get((row["period"], row["indicator_key"]))
        value = row.get("value")
        if value is None or not team or team.get("team_avg") is None:
            continue
        delta = float(value) - float(team["team_avg"])
        if abs(delta) < 0.01:
            continue
        direction = "acima" if delta > 0 else "abaixo"
        tips.append(
            f"{row['name']}: você está {abs(delta):.1f} p.p. {direction} da média da equipe em {row['period']}."
        )
    return tips or ["Seu desempenho está próximo da média da equipe nos indicadores disponíveis."]
