from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zipfile import ZipFile

from src.features.ingestion.excel import ImportValidationError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class PivotField:
    name: str
    shared_items: tuple[object | None, ...]


def iter_pivot_records(
    raw_bytes: bytes,
    *,
    required_fields: set[str],
    optional_fields: set[str] | None = None,
):
    optional_fields = optional_fields or set()
    if not raw_bytes:
        raise ImportValidationError("Arquivo vazio.")

    with ZipFile(io.BytesIO(raw_bytes)) as archive:
        definition_path, record_path, fields = _select_cache(
            archive,
            required_fields=required_fields,
        )
        name_to_index = {field.name: index for index, field in enumerate(fields)}
        selected_names = [
            name for name in [*required_fields, *optional_fields]
            if name in name_to_index
        ]
        selected_indexes = {name_to_index[name] for name in selected_names}

        with archive.open(record_path) as stream:
            for _, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != NS + "r":
                    continue
                children = list(elem)
                row: dict[str, object | None] = {}
                for index in selected_indexes:
                    name = fields[index].name
                    item = children[index] if index < len(children) else None
                    row[name] = _decode_record_item(item, fields[index])
                elem.clear()
                yield row


def _select_cache(
    archive: ZipFile,
    *,
    required_fields: set[str],
) -> tuple[str, str, tuple[PivotField, ...]]:
    definitions = sorted(
        path for path in archive.namelist()
        if path.startswith("xl/pivotCache/pivotCacheDefinition") and path.endswith(".xml")
    )
    for definition_path in definitions:
        fields = _parse_fields(archive.read(definition_path))
        names = {field.name for field in fields}
        if not required_fields.issubset(names):
            continue
        match = re.search(r"(\d+)\.xml$", definition_path)
        if not match:
            continue
        record_path = f"xl/pivotCache/pivotCacheRecords{match.group(1)}.xml"
        if record_path not in archive.namelist():
            continue
        return definition_path, record_path, fields
    missing = ", ".join(sorted(required_fields))
    raise ImportValidationError(f"Pivot cache compatível não encontrado. Campos esperados: {missing}")


def _parse_fields(xml_bytes: bytes) -> tuple[PivotField, ...]:
    root = ET.fromstring(xml_bytes)
    cache_fields = root.find(NS + "cacheFields")
    if cache_fields is None:
        return ()
    fields: list[PivotField] = []
    for field in list(cache_fields):
        shared = field.find(NS + "sharedItems")
        values: list[object | None] = []
        if shared is not None:
            for item in list(shared):
                values.append(_decode_shared_item(item))
        fields.append(PivotField(field.attrib.get("name", ""), tuple(values)))
    return tuple(fields)


def _decode_shared_item(item) -> object | None:
    tag = item.tag.split("}")[-1]
    raw = item.attrib.get("v")
    if tag == "m":
        return None
    if tag == "n":
        return _number(raw)
    if tag == "b":
        return raw == "1"
    return raw


def _decode_record_item(item, field: PivotField) -> object | None:
    if item is None:
        return None
    tag = item.tag.split("}")[-1]
    raw = item.attrib.get("v")
    if tag == "m":
        return None
    if tag == "x":
        try:
            return field.shared_items[int(raw)]
        except (TypeError, ValueError, IndexError):
            return None
    if tag == "n":
        return _number(raw)
    if tag == "b":
        return raw == "1"
    return raw


def _number(raw: str | None) -> int | float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value
