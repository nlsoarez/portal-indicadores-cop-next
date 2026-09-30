from src.features.segments.common import GENERIC_OPERATIONAL_INDICATORS

ENTERPRISE_ANALYSTS = (
    ("N0189105", "IGOR MARCELINO DE MARINS", "Igor"),
    ("N5737414", "SANDRO DA SILVA CARVALHO", "Sandro"),
    ("N5713690", "GABRIELA TAVARES DA SILVA", "Gabriela"),
    ("N5802257", "MAGNO FERRAREZ DE MORAIS", "Magno"),
    ("F201714", "FERNANDA MESQUITA DE FREITAS", "Fernanda"),
    ("N6173055", "JEFFERSON LUIS GONÇALVES COITINHO", "Jefferson"),
    ("N0125317", "ROBERTO SILVA DO NASCIMENTO", "Roberto"),
    ("N5819183", "RODRIGO PIRES BERNARDINO", "Rodrigo"),
    ("N5926003", "SUELLEN HERNANDEZ DA SILVA", "Suellen"),
    ("N5932064", "MONICA DA SILVA RODRIGUES", "Monica"),
)

ENTERPRISE_INDICATORS: tuple[dict, ...] = (
    {
        "indicator_key": "emp_etit_event",
        "name": "ETIT por Evento",
        "target_value": 90.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "chat_10m",
        "name": "Chat 10 min",
        "target_value": 75.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "validacao_20m",
        "name": "Tempo de Validação do Formulário",
        "target_value": 80.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "toa_cancellation_rate",
        "name": "Tarefas Canceladas",
        "target_value": 15.0,
        "direction": "lower_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "closing_assertiveness",
        "name": "Assertividade Fechamento TOA x SIR",
        "target_value": 80.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    *GENERIC_OPERATIONAL_INDICATORS,
)
