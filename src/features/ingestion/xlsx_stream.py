from __future__ import annotations

import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from zipfile import ZipFile

from src.features.ingestion.excel import ImportValidationError

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def iter_rows(
    raw_bytes: bytes,
    *,
    sheet_candidates: tuple[str, ...],
    header_row: int,
    required_headers: set[str],
    optional_headers: set[str] | None = None,
    required_any: tuple[set[str], ...] = (),
):
    """Stream rows from XLSX XML without loading the worksheet into memory."""
    optional_headers = optional_headers or set()
    if not raw_bytes:
        raise ImportValidationError("Arquivo vazio.")

    with ZipFile(io.BytesIO(raw_bytes)) as archive:
        shared = _load_shared_strings(archive)
        sheet_path = _resolve_sheet_path(archive, sheet_candidates)
        header_by_col: dict[str, str] = {}
        wanted = required_headers | optional_headers
        header_seen = False

        with archive.open(sheet_path) as stream:
            for _, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != MAIN + "row":
                    continue
                row_number = int(elem.attrib.get("r", "0"))
                if row_number < header_row:
                    elem.clear(); continue

                if row_number == header_row:
                    for cell in elem.findall(MAIN + "c"):
                        value = _cell_value(cell, shared)
                        if value is None:
                            continue
                        name = normalize_header(value)
                        if name in wanted:
                            header_by_col[_column(cell.attrib.get("r", ""))] = name
                    found_headers = set(header_by_col.values())
                    missing = sorted(required_headers - found_headers)
                    if missing:
                        raise ImportValidationError(
                            f"Planilha sem colunas obrigatórias: {', '.join(missing)}"
                        )
                    for group in required_any:
                        if not (group & found_headers):
                            expected = " / ".join(sorted(group))
                            raise ImportValidationError(
                                f"Planilha sem uma das colunas obrigatórias: {expected}"
                            )
                    header_seen = True
                    elem.clear(); continue

                if not header_seen:
                    elem.clear(); continue

                row: dict[str, object | None] = {}
                for cell in elem.findall(MAIN + "c"):
                    name = header_by_col.get(_column(cell.attrib.get("r", "")))
                    if name:
                        row[name] = _cell_value(cell, shared)
                elem.clear()
                if row:
                    yield row

        if not header_seen:
            raise ImportValidationError(f"Cabeçalho não encontrado na linha {header_row}.")


def normalize_header(value: object) -> str:
    raw = str(value).strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper()


def normalize_login(value: object | None) -> str:
    raw = str(value or "").strip().upper()
    return "" if raw in {"NAN", "NONE"} else raw


def as_float(value: object | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: object | None, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def excel_date(value: object | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        serial = float(raw)
    except ValueError:
        return None
    if serial <= 1000:
        return None
    return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()


def _load_shared_strings(archive: ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    values: list[str] = []
    with archive.open(path) as stream:
        for _, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag == MAIN + "si":
                values.append("".join((node.text or "") for node in elem.iter(MAIN + "t")))
                elem.clear()
    return values


def _resolve_sheet_path(archive: ZipFile, candidates: tuple[str, ...]) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationships = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(PACKAGE_REL + "Relationship")
    }
    candidate_keys = {normalize_header(name) for name in candidates}
    sheets = workbook.find(MAIN + "sheets")
    if sheets is None:
        raise ImportValidationError("Workbook sem abas.")
    fallback: str | None = None
    for sheet in list(sheets):
        target = relationships.get(sheet.attrib.get(OFFICE_REL + "id", ""))
        if not target:
            continue
        if target.startswith("/xl/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target.lstrip("/")
        fallback = fallback or path
        if normalize_header(sheet.attrib.get("name", "")) in candidate_keys:
            return path
    if fallback:
        return fallback
    raise ImportValidationError("Nenhuma aba legível encontrada.")


def _cell_value(cell, shared: list[str]) -> object | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(MAIN + "is")
        return "".join((node.text or "") for node in inline.iter(MAIN + "t")) if inline is not None else ""
    value = cell.find(MAIN + "v")
    if value is None:
        return None
    raw = value.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError, TypeError):
            return None
    if cell_type == "b":
        return raw == "1"
    return raw


def _column(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    return match.group(1) if match else ""
