from __future__ import annotations

import pandas as pd

from src.features.ingestion.excel import (
    ImportValidationError,
    daily_adherence,
    filter_latest_anomes,
    normalize_login,
    read_excel,
)
from src.features.ingestion.models import ParsedIndicatorBatch

SOURCE_KEY = "toa_validation"
INDICATOR_KEY = "validacao_20m"
SHEET_CANDIDATES = ("TOA", "Planilha1", "Sheet1", "Analitico", "Analítico", "INDICADORES")
INDICATOR_NAME = "TEMPO DE VALIDAÇÃO DO FORMULÁRIO"
COL_NAME = "INDICADOR_NOME"
COL_LOGIN = "LOGIN"
COL_INDICATOR = "INDICADOR"
COL_ANOMES = "ANOMES"
COL_REGIONAL = "IN_REGIONAL"
COL_DATE = "DATA"
COL_START = "DT_INICIO_FORM"


def parse_toa_validation(raw_bytes: bytes, allowed_logins: set[str]) -> ParsedIndicatorBatch:
    df = read_excel(raw_bytes, SHEET_CANDIDATES)
    required = {COL_NAME, COL_LOGIN, COL_INDICATOR}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ImportValidationError(f"Indicadores TOA sem colunas obrigatórias: {', '.join(missing)}")

    df = df[df[COL_NAME].astype(str).str.strip().str.upper() == INDICATOR_NAME].copy()
    if df.empty:
        raise ImportValidationError("O arquivo não contém o indicador Tempo de Validação do Formulário.")

    df[COL_LOGIN] = normalize_login(df[COL_LOGIN])
    df = filter_latest_anomes(df, COL_ANOMES)
    if COL_REGIONAL in df.columns:
        df = df[df[COL_REGIONAL].astype(str).str.strip().str.upper() == "LESTE"].copy()

    allowed = {str(login).strip().upper() for login in allowed_logins}
    df = df[df[COL_LOGIN].isin(allowed)].copy()
    if df.empty:
        raise ImportValidationError("O arquivo de Validação não possui dados dos analistas deste segmento.")

    df[COL_INDICATOR] = pd.to_numeric(df[COL_INDICATOR], errors="coerce")
    df = df[df[COL_INDICATOR].isin([0, 1])].copy()
    df["_ADHERENT"] = (df[COL_INDICATOR] == 1).astype(int)

    date_col = COL_DATE if COL_DATE in df.columns else COL_START
    if date_col not in df.columns:
        raise ImportValidationError("O arquivo de Validação não possui coluna de data reconhecida.")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    if df.empty:
        raise ImportValidationError("O arquivo de Validação não possui datas válidas.")

    rows = daily_adherence(df, login_col=COL_LOGIN, date_col=date_col, adherent_col="_ADHERENT")
    if not rows:
        raise ImportValidationError("Não foi possível consolidar o indicador Tempo de Validação.")

    data_through = max(row["period"] for row in rows)
    months = tuple(sorted({row["period"][:7] for row in rows}))
    return ParsedIndicatorBatch(SOURCE_KEY, INDICATOR_KEY, data_through, rows, months)
