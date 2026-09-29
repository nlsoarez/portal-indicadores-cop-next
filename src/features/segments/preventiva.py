PREVENTIVA_ANALYSTS = (
    ("N5604148", "DANIEL MARCELO FELISBERTO OLIVEIRA", "Daniel"),
    ("N5941223", "ROSANA RIEGER MATOS", "Rosana"),
    ("N0158974", "CARLOS EDUARDO BARRETO DE ABREU", "Carlos"),
    ("N5577565", "MARISTELLA MARCIA DOS SANTOS", "Maristella"),
)

PREVENTIVA_INDICATORS: tuple[dict, ...] = (
    {
        "indicator_key": "chat_10m",
        "name": "Chat 10 min",
        "target_value": 75.0,
        "direction": "higher_is_better",
    },
    {
        "indicator_key": "validacao_20m",
        "name": "Tempo de Validação do Formulário",
        "target_value": 80.0,
        "direction": "higher_is_better",
    },
)
