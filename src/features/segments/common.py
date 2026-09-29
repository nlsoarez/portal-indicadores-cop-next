GENERIC_OPERATIONAL_INDICATORS: tuple[dict, ...] = (
    {
        "indicator_key": "dpa_official",
        "name": "DPA Oficial",
        "target_value": 90.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "productivity_avg_daily",
        "name": "Produtividade média diária",
        "target_value": None,
        "direction": "higher_is_better",
        "unit": "number",
    },
    {
        "indicator_key": "closing_assertiveness",
        "name": "Assertividade Fechamento TOA x SIR",
        "target_value": None,
        "direction": "higher_is_better",
        "unit": "percent",
    },
)
