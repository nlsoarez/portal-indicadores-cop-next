from __future__ import annotations

import io
from zipfile import BadZipFile, ZipFile, is_zipfile

MAX_WORKBOOK_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_ENTRY_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250.0
RATIO_CHECK_MIN_BYTES = 1024 * 1024


def _validation_error(message: str):
    # Lazy import avoids a module cycle because excel.py also calls this guard.
    from src.features.ingestion.excel import ImportValidationError
    return ImportValidationError(message)


def validate_workbook_bytes(raw_bytes: bytes) -> None:
    """Reject oversized or suspicious Excel archives before parser allocation."""
    if not raw_bytes:
        raise _validation_error("Arquivo vazio.")
    if len(raw_bytes) > MAX_WORKBOOK_BYTES:
        raise _validation_error("Arquivo maior que o limite de 128 MB.")

    stream = io.BytesIO(raw_bytes)
    if not is_zipfile(stream):
        return

    stream.seek(0)
    try:
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise _validation_error("Planilha possui arquivos internos em excesso.")

            total_uncompressed = 0
            for info in infos:
                size = int(info.file_size or 0)
                compressed = int(info.compress_size or 0)
                total_uncompressed += size

                if size > MAX_SINGLE_ENTRY_BYTES:
                    raise _validation_error(
                        "Planilha possui conteúdo interno descompactado acima do limite seguro."
                    )
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise _validation_error(
                        "Planilha excede o limite seguro de tamanho descompactado."
                    )
                if size >= RATIO_CHECK_MIN_BYTES:
                    ratio = size / max(compressed, 1)
                    if ratio > MAX_COMPRESSION_RATIO:
                        raise _validation_error(
                            "Planilha possui taxa de compressão anormal e foi bloqueada."
                        )
    except BadZipFile as exc:
        raise _validation_error("Arquivo XLSX inválido ou corrompido.") from exc
