from __future__ import annotations

import io

import pandas as pd


class ImportValidationError(ValueError):
    pass


def read_excel(raw_bytes: bytes, sheet_candidates: tuple[str, ...], *, header: int = 0) -> pd.DataFrame:
    if not raw_bytes:
        raise ImportValidationError("Arquivo vazio.")

    last_error: Exception | None = None
    for engine in ("calamine", "openpyxl"):
        try:
            with pd.ExcelFile(io.BytesIO(raw_bytes), engine=engine) as workbook:
                if not workbook.sheet_names:
                    raise ImportValidationError("A planilha não possui abas.")
                sheet = next(
                    (name for name in sheet_candidates if name in workbook.sheet_names),
                    workbook.sheet_names[0],
                )
                return workbook.parse(sheet_name=sheet, header=header)
        except ImportValidationError:
            raise
        except Exception as exc:
            last_error = exc

    raise ImportValidationError(f"Não foi possível ler a planilha: {last_error}")


def normalize_login(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


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
    working["_period"] = pd.to_datetime(working[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
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
