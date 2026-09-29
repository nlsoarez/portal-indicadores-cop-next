from __future__ import annotations

from datetime import date, datetime

from src.application.access_service import AccessService
from src.domain.entities import AccessContext
from src.infrastructure.repositories import IndicatorRepository, UploadRepository


class IndicatorFreshnessService:
    def __init__(self, access=None, indicators=None, uploads=None):
        self.access = access or AccessService()
        self.indicators = indicators or IndicatorRepository()
        self.uploads = uploads or UploadRepository()

    def start_upload(self, ctx: AccessContext, segment_id: int, source_key: str, filename: str) -> int:
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem registrar uploads")
        return self.uploads.create(segment_id, source_key, filename, ctx.user.id)

    def record_indicator_data_through(self, ctx, segment_id, indicator_key, data_through, source_key, upload_id=None):
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem atualizar a cobertura dos indicadores")
        definition = self.indicators.get_definition(segment_id, indicator_key)
        if not definition:
            raise ValueError(f"Indicador não cadastrado no segmento: {indicator_key}")
        self.indicators.upsert_freshness(segment_id, int(definition["id"]), _normalize_date(data_through), source_key, upload_id)

    def freshness(self, ctx, segment_id):
        self.access.assert_segment_access(ctx, segment_id)
        return self.indicators.freshness(segment_id)


def _normalize_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Data inválida para cobertura do indicador: {value}")
