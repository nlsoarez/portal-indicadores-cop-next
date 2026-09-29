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

SOURCE_KEY = "chat_toa"
INDICATOR_KEY = "chat_10m"
SHEET_CANDIDATES = ("Analítico CHAT TOA", "Analitico CHAT TOA", "CHAT TOA")
HEADER_ROW = 3
COL_LOGIN = "FECHAMENTO_COPREDE_LOGIN_ANALISTA"
COL_ANOMES = "ABERTURA_ANOMES"
COL_QUEUE = "FECHAMENTO_FILA"
COL_INDICATOR = "INDICADOR_TMA_DENTRO"
COL_START = "CHAT_INICIO"


def parse_chat_toa(raw_bytes: bytes, allowed_logins: set[str]) -> ParsedIndicatorBatch:
    df = read_excel(raw_bytes, SHEET_CANDIDATES, header=HEADER_ROW)
    required = {COL_LOGIN, COL_INDICATOR, COL_START}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ImportValidationError(f"Chat TOA sem colunas obrigatórias: {', '.join(missing)}")

    df = df.copy()
    df[COL_LOGIN] = normalize_login(df[COL_LOGIN])
    df = filter_latest_anomes(df, COL_ANOMES)

    if COL_QUEUE in df.columns:
        df = df[df[COL_QUEUE].astype(str).str.contains("RJO", na=False)].copy()

    allowed = {str(login).strip().upper() for login in allowed_logins}
    df = df[df[COL_LOGIN].isin(allowed)].copy()
    if df.empty:
        raise ImportValidationError("O arquivo de Chat TOA não possui dados dos analistas deste segmento.")

    df[COL_INDICATOR] = pd.to_numeric(df[COL_INDICATOR], errors="coerce")
    df = df[df[COL_INDICATOR].isin([0, 1])].copy()
    df["_ADHERENT"] = df[COL_INDICATOR].astype(int)
    df[COL_START] = pd.to_datetime(df[COL_START], errors="coerce")
    df = df.dropna(subset=[COL_START])
    if df.empty:
        raise ImportValidationError("O arquivo de Chat TOA não possui datas válidas para o indicador.")

    rows = daily_adherence(df, login_col=COL_LOGIN, date_col=COL_START, adherent_col="_ADHERENT")
    if not rows:
        raise ImportValidationError("Não foi possível consolidar o indicador Chat 10 min.")

    data_through = max(row["period"] for row in rows)
    months = tuple(sorted({row["period"][:7] for row in rows}))
    return ParsedIndicatorBatch(SOURCE_KEY, INDICATOR_KEY, data_through, rows, months)
