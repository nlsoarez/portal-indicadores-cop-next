from __future__ import annotations

from datetime import date, datetime

from src.application.access_service import AccessService
from src.domain.entities import AccessContext
from src.infrastructure.repositories import IndicatorRepository, UploadRepository


class IndicatorFreshnessService:
    """Registra até qual data cada indicador está coberto por um upload processado."""

    def __init__(
        self,
        access: AccessService | None = None,
        indicators: IndicatorRepository | None = None,
        uploads: UploadRepository | None = None,
    ):
        self.access = access or AccessService()
        self.indicators = indicators or IndicatorRepository()
        self.uploads = uploads or UploadRepository()

    def start_upload(
        self,
        ctx: AccessContext,
        segment_id: int,
        source_key: str,
        filename: str,
    ) -> int:
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem registrar uploads")
        return self.uploads.create(
            segment_id=segment_id,
            source_key=source_key,
            filename=filename,
            uploaded_by=ctx.user.id,
        )

    def record_indicator_data_through(
        self,
        ctx: AccessContext,
        segment_id: int,
        indicator_key: str,
        data_through: date | datetime | str,
        source_key: str,
        upload_id: int | None = None,
    ) -> None:
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem atualizar a cobertura dos indicadores")

        normalized = _normalize_date(data_through)
        definition = self.indicators.get_definition(segment_id, indicator_key)
        if not definition:
            raise ValueError(f"Indicador não cadastrado no segmento: {indicator_key}")

        self.indicators.upsert_freshness(
            segment_id=segment_id,
            indicator_definition_id=int(definition["id"]),
            data_through=normalized,
            source_key=source_key,
            upload_id=upload_id,
        )

    def freshness(self, ctx: AccessContext, segment_id: int) -> list[dict]:
        self.access.assert_segment_access(ctx, segment_id)
        return self.indicators.freshness(segment_id)


def _normalize_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    raw = str(value).strip()
    if not raw:
        raise ValueError("data_through vazio")

    # Contrato interno: persistir sempre YYYY-MM-DD.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Data inválida para cobertura do indicador: {value}")
