from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd


class ImportValidationError(ValueError):
    pass


def read_excel(raw_bytes: bytes, sheet_candidates: tuple[str, ...], *, header: int = 0) -> pd.DataFrame:
    from src.features.ingestion.archive_safety import validate_workbook_bytes

    validate_workbook_bytes(raw_bytes)

    last_error: Exception | None = None
    for engine in ("calamine", "openpyxl"):
        try:
            with pd.ExcelFile(io.BytesIO(raw_bytes), engine=engine) as workbook:
                if not workbook.sheet_names:
                    raise ImportValidationError("A planilha não possui abas.")
                normalized = {_normalize_text(name): name for name in workbook.sheet_names}
                selected = None
                for candidate in sheet_candidates:
                    selected = normalized.get(_normalize_text(candidate))
                    if selected:
                        break
                sheet = selected or workbook.sheet_names[0]
                return workbook.parse(sheet_name=sheet, header=header)
        except ImportValidationError:
            raise
        except Exception as exc:
            last_error = exc

    raise ImportValidationError(f"Não foi possível ler a planilha: {last_error}")


def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [_normalize_text(column) for column in out.columns]
    return out


def normalize_login(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})


def filter_latest_anomes(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        return df.copy()
    numeric = pd.to_numeric(df[column], errors="coerce")
    latest = numeric.max()
    if pd.isna(latest):
        return df.copy()
    out = df.copy()
    out[column] = numeric
    return out[out[column] == latest].copy()


def coerce_excel_datetime(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    direct = pd.to_datetime(series.where(numeric.isna()), errors="coerce")
    excel = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
    return direct.fillna(excel)


def daily_adherence(
    df: pd.DataFrame,
    *,
    login_col: str,
    date_col: str,
    adherent_col: str,
) -> tuple[dict, ...]:
    if df.empty:
        return ()
    working = df.dropna(subset=[date_col]).copy()
    if working.empty:
        return ()
    working["_period"] = coerce_excel_datetime(working[date_col]).dt.strftime("%Y-%m-%d")
    working = working.dropna(subset=["_period"])
    if working.empty:
        return ()

    grouped = (
        working.groupby([login_col, "_period"], dropna=False)
        .agg(volume=(adherent_col, "count"), adherent=(adherent_col, "sum"))
        .reset_index()
    )
    grouped["value"] = (grouped["adherent"] / grouped["volume"] * 100).round(1)
    return tuple(
        {
            "login": str(row[login_col]).strip().upper(),
            "period": str(row["_period"]),
            "value": float(row["value"]),
            "volume": int(row["volume"]),
        }
        for _, row in grouped.iterrows()
        if int(row["volume"]) > 0
    )


def daily_weighted_adherence(
    df: pd.DataFrame,
    *,
    login_col: str,
    date_col: str,
    adherent_col: str,
    volume_col: str,
) -> tuple[dict, ...]:
    if df.empty:
        return ()
    working = df.copy()
    working["_period"] = coerce_excel_datetime(working[date_col]).dt.strftime("%Y-%m-%d")
    working["_volume"] = pd.to_numeric(working[volume_col], errors="coerce").fillna(0.0)
    working["_adherent"] = pd.to_numeric(working[adherent_col], errors="coerce").fillna(0.0)
    working["_gain"] = working["_volume"] * working["_adherent"]
    working = working.dropna(subset=["_period"])
    working = working[working["_volume"] > 0]
    if working.empty:
        return ()

    grouped = (
        working.groupby([login_col, "_period"], dropna=False)
        .agg(volume=("_volume", "sum"), adherent=("_gain", "sum"))
        .reset_index()
    )
    grouped["value"] = (grouped["adherent"] / grouped["volume"] * 100).round(1)
    return tuple(
        {
            "login": str(row[login_col]).strip().upper(),
            "period": str(row["_period"]),
            "value": float(row["value"]),
            "volume": int(round(float(row["volume"]))),
        }
        for _, row in grouped.iterrows()
        if float(row["volume"]) > 0
    )


def daily_numeric_sum(
    df: pd.DataFrame,
    *,
    login_col: str,
    date_col: str,
    value_col: str,
) -> tuple[dict, ...]:
    if df.empty:
        return ()
    working = df.copy()
    working["_period"] = coerce_excel_datetime(working[date_col]).dt.strftime("%Y-%m-%d")
    working["_value"] = pd.to_numeric(working[value_col], errors="coerce").fillna(0.0)
    working = working.dropna(subset=["_period"])
    if working.empty:
        return ()
    grouped = (
        working.groupby([login_col, "_period"], dropna=False)["_value"]
        .sum()
        .reset_index()
    )
    return tuple(
        {
            "login": str(row[login_col]).strip().upper(),
            "period": str(row["_period"]),
            "value": float(round(float(row["_value"]), 1)),
            "volume": 1,
        }
        for _, row in grouped.iterrows()
    )


def batch_meta(rows: tuple[dict, ...]) -> tuple[str, tuple[str, ...]]:
    if not rows:
        raise ImportValidationError("Não há linhas válidas para consolidar o indicador.")
    data_through = max(str(row["period"]) for row in rows)
    months = tuple(sorted({str(row["period"])[:7] for row in rows}))
    return data_through, months


def _normalize_text(value: object) -> str:
    raw = str(value).strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")
    return ascii_text.upper()
