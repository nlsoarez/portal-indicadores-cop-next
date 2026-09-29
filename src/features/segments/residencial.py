from src.features.segments.common import GENERIC_OPERATIONAL_INDICATORS

RESIDENTIAL_ANALYSTS = (
    ("N5772086", "THIAGO PEREIRA DA SILVA", "Thiago"),
    ("N0239871", "LEONARDO FERREIRA LIMA DE ALMEIDA", "Leonardo"),
    ("N5972428", "CRISTIANE HERMOGENES DA SILVA", "Cristiane"),
    ("N4014011", "ALAN MARINHO DIAS", "Alan"),
    ("F106664", "RAISSA LIMA DE OLIVEIRA", "Raissa"),
    ("F104752", "MARCELO DE SOUZA ALMEIDA", "Marcelo"),
)

RESIDENTIAL_INDICATORS: tuple[dict, ...] = (
    {
        "indicator_key": "res_etit_fibra_hfc",
        "name": "ETIT Fibra HFC",
        "target_value": 90.0,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "res_etit_gpon",
        "name": "ETIT GPON",
        "target_value": None,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "res_assert_fibra_hfc",
        "name": "Assertividade Acionamento Fibra HFC",
        "target_value": None,
        "direction": "higher_is_better",
        "unit": "percent",
    },
    {
        "indicator_key": "res_assert_gpon",
        "name": "Assertividade Acionamento GPON",
        "target_value": None,
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
        "target_value": None,
        "direction": "lower_is_better",
        "unit": "percent",
    },
    *GENERIC_OPERATIONAL_INDICATORS,
)
