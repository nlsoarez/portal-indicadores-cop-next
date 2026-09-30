from __future__ import annotations

import io
from zipfile import BadZipFile, ZipFile, is_zipfile

from src.features.ingestion.excel import ImportValidationError


MAX_WORKBOOK_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_ENTRY_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250.0
RATIO_CHECK_MIN_BYTES = 1024 * 1024


def validate_workbook_bytes(raw_bytes: bytes) -> None:
    """Reject oversized or suspicious Excel archives before parser allocation."""
    if not raw_bytes:
        raise ImportValidationError("Arquivo vazio.")
    if len(raw_bytes) > MAX_WORKBOOK_BYTES:
        raise ImportValidationError("Arquivo maior que o limite de 128 MB.")

    stream = io.BytesIO(raw_bytes)
    if not is_zipfile(stream):
        return

    stream.seek(0)
    try:
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ImportValidationError("Planilha possui arquivos internos em excesso.")

            total_uncompressed = 0
            for info in infos:
                size = int(info.file_size or 0)
                compressed = int(info.compress_size or 0)
                total_uncompressed += size

                if size > MAX_SINGLE_ENTRY_BYTES:
                    raise ImportValidationError(
                        "Planilha possui conteúdo interno descompactado acima do limite seguro."
                    )
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ImportValidationError(
                        "Planilha excede o limite seguro de tamanho descompactado."
                    )
                if size >= RATIO_CHECK_MIN_BYTES:
                    ratio = size / max(compressed, 1)
                    if ratio > MAX_COMPRESSION_RATIO:
                        raise ImportValidationError(
                            "Planilha possui taxa de compressão anormal e foi bloqueada."
                        )
    except BadZipFile as exc:
        raise ImportValidationError("Arquivo XLSX inválido ou corrompido.") from exc
