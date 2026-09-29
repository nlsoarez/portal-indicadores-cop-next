from __future__ import annotations

from dataclasses import dataclass

from src.application.access_service import AccessService
from src.application.indicator_freshness_service import IndicatorFreshnessService
from src.domain.entities import AccessContext
from src.features.ingestion.registry import SOURCE_ADAPTERS
from src.features.ingestion.source_catalog import UPLOAD_SOURCE_BY_KEY
from src.infrastructure.repositories import (
    IndicatorRepository,
    SegmentRepository,
    UserRepository,
)


@dataclass(frozen=True)
class UploadProcessingResult:
    source_key: str
    indicator_key: str
    indicator_name: str
    data_through: str
    analyst_count: int
    total_volume: int
    daily_points: int


class UploadProcessingService:
    def __init__(
        self,
        access: AccessService | None = None,
        users: UserRepository | None = None,
        indicators: IndicatorRepository | None = None,
        segments: SegmentRepository | None = None,
        freshness: IndicatorFreshnessService | None = None,
    ):
        self.access = access or AccessService()
        self.users = users or UserRepository()
        self.indicators = indicators or IndicatorRepository()
        self.segments = segments or SegmentRepository()
        self.freshness = freshness or IndicatorFreshnessService(
            access=self.access,
            indicators=self.indicators,
        )

    def process(
        self,
        ctx: AccessContext,
        segment_id: int,
        source_key: str,
        filename: str,
        raw_bytes: bytes,
    ) -> UploadProcessingResult:
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem processar planilhas")

        adapter = SOURCE_ADAPTERS.get(source_key)
        if adapter is None:
            raise ValueError(f"Fonte não suportada: {source_key}")

        performance_users = self.users.list_performance_users_for_segment(segment_id)
        login_to_user_id = {user.login.upper(): user.id for user in performance_users}
        if not login_to_user_id:
            raise ValueError("O segmento não possui usuários de desempenho ativos para processar")

        batch = adapter.parser(raw_bytes, set(login_to_user_id))
        if batch.indicator_key != adapter.indicator_key:
            raise ValueError("Adapter retornou indicador incompatível com a fonte")

        definition = self.indicators.get_definition(segment_id, batch.indicator_key)
        if not definition:
            raise ValueError(f"Indicador não cadastrado no segmento: {batch.indicator_key}")

        upload_id = self.freshness.start_upload(
            ctx,
            segment_id,
            source_key=source_key,
            filename=filename,
        )
        self.indicators.replace_results_for_months(
            segment_id=segment_id,
            indicator_definition_id=int(definition["id"]),
            login_to_user_id=login_to_user_id,
            rows=batch.rows,
            months=batch.months,
        )
        self.freshness.record_indicator_data_through(
            ctx,
            segment_id,
            batch.indicator_key,
            batch.data_through,
            source_key,
            upload_id,
        )

        return UploadProcessingResult(
            source_key=source_key,
            indicator_key=batch.indicator_key,
            indicator_name=str(definition["name"]),
            data_through=batch.data_through,
            analyst_count=batch.analyst_count,
            total_volume=batch.total_volume,
            daily_points=len(batch.rows),
        )

    def process_global_source(
        self,
        ctx: AccessContext,
        source_key: str,
        filename: str,
        raw_bytes: bytes,
    ) -> list[tuple[str, UploadProcessingResult]]:
        """Processa uma das sete fontes oficiais sem depender do segmento selecionado na UI."""
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem processar planilhas")

        source = UPLOAD_SOURCE_BY_KEY.get(source_key)
        if source is None:
            raise ValueError(f"Fonte de upload desconhecida: {source_key}")
        if not source.implemented or not source.adapter_key:
            raise ValueError(f"A integração da fonte '{source.label}' ainda não está habilitada")

        adapter = SOURCE_ADAPTERS[source.adapter_key]
        results: list[tuple[str, UploadProcessingResult]] = []

        for slug in source.target_segment_slugs:
            segment = self.segments.get_by_slug(slug)
            if not segment or not segment.active or segment.id not in ctx.segment_ids:
                continue

            if not self.indicators.get_definition(segment.id, adapter.indicator_key):
                continue

            result = self.process(
                ctx,
                segment.id,
                source.adapter_key,
                filename,
                raw_bytes,
            )
            results.append((slug, result))

        if not results:
            raise ValueError(
                f"Nenhum segmento elegível possui indicador configurado para a fonte '{source.label}'"
            )
        return results
