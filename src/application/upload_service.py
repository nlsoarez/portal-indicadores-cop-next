from __future__ import annotations

from dataclasses import dataclass

from src.application.access_service import AccessService
from src.application.indicator_freshness_service import IndicatorFreshnessService
from src.domain.entities import AccessContext
from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.registry import SOURCE_ADAPTERS
from src.features.ingestion.source_catalog import UPLOAD_SOURCE_BY_KEY
from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository


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
    def __init__(self, access=None, users=None, indicators=None, segments=None, freshness=None):
        self.access = access or AccessService()
        self.users = users or UserRepository()
        self.indicators = indicators or IndicatorRepository()
        self.segments = segments or SegmentRepository()
        self.freshness = freshness or IndicatorFreshnessService(access=self.access, indicators=self.indicators)

    def process(self, ctx: AccessContext, segment_id: int, source_key: str, filename: str, raw_bytes: bytes) -> UploadProcessingResult:
        results = self._process_adapter(ctx, segment_id, source_key, filename, raw_bytes, upload_source_key=source_key)
        if not results:
            raise ImportValidationError("O arquivo não possui dados válidos para o segmento selecionado.")
        return results[0]

    def process_global_source(self, ctx: AccessContext, source_key: str, filename: str, raw_bytes: bytes) -> list[tuple[str, UploadProcessingResult]]:
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem processar planilhas")
        source = UPLOAD_SOURCE_BY_KEY.get(source_key)
        if source is None:
            raise ValueError(f"Fonte de upload desconhecida: {source_key}")
        adapter = SOURCE_ADAPTERS.get(source.adapter_key)
        if adapter is None:
            raise ValueError(f"Adapter não configurado para a fonte '{source.label}'")

        targets: list[tuple[object, dict[str, int]]] = []
        union_logins: set[str] = set()
        for slug in source.target_segment_slugs:
            segment = self.segments.get_by_slug(slug)
            if not segment or not segment.active or segment.id not in ctx.segment_ids:
                continue
            people = self.users.list_performance_users_for_segment(segment.id)
            login_map = {person.login.upper(): person.id for person in people}
            if login_map:
                targets.append((segment, login_map))
                union_logins.update(login_map)

        if not union_logins:
            raise ImportValidationError(f"Não há usuários cadastrados para a fonte '{source.label}'.")

        batches = adapter.parser(raw_bytes, union_logins)
        output: list[tuple[str, UploadProcessingResult]] = []
        for target_index, (segment, login_map) in enumerate(targets):
            filtered: list[ParsedIndicatorBatch] = []
            for batch in batches:
                rows = tuple(row for row in batch.rows if str(row.get("login", "")).upper() in login_map)
                if not rows:
                    continue
                breakdowns = tuple(
                    breakdown
                    for breakdown in batch.breakdowns
                    if (
                        str(breakdown.get("scope") or "team") == "team"
                        and str(breakdown.get("login") or "").upper() in login_map
                    )
                    or (
                        str(breakdown.get("scope") or "") == "external"
                        and target_index == 0
                    )
                )
                filtered.append(
                    ParsedIndicatorBatch(
                        source_key=batch.source_key,
                        indicator_key=batch.indicator_key,
                        data_through=max(str(row["period"]) for row in rows),
                        rows=rows,
                        months=batch.months,
                        breakdowns=breakdowns,
                    )
                )
            results = self._persist_batches(
                ctx,
                segment.id,
                filtered,
                login_map,
                filename,
                upload_source_key=source.key,
            )
            output.extend((segment.slug, result) for result in results)

        if not output:
            raise ImportValidationError(f"A fonte '{source.label}' não possui dados dos usuários cadastrados no portal.")
        return output

    def _process_adapter(self, ctx, segment_id, adapter_key, filename, raw_bytes, *, upload_source_key):
        self.access.assert_segment_access(ctx, segment_id)
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem processar planilhas")
        adapter = SOURCE_ADAPTERS.get(adapter_key)
        if adapter is None:
            raise ValueError(f"Fonte não suportada: {adapter_key}")
        people = self.users.list_performance_users_for_segment(segment_id)
        login_map = {person.login.upper(): person.id for person in people}
        if not login_map:
            return []
        batches = adapter.parser(raw_bytes, set(login_map))
        return self._persist_batches(ctx, segment_id, list(batches), login_map, filename, upload_source_key=upload_source_key)

    def _persist_batches(self, ctx, segment_id, batches, login_map, filename, *, upload_source_key):
        eligible = []
        for batch in batches:
            definition = self.indicators.get_definition(segment_id, batch.indicator_key)
            if definition:
                eligible.append((batch, definition))
        if not eligible:
            return []

        upload_id = self.freshness.start_upload(ctx, segment_id, source_key=upload_source_key, filename=filename)
        results = []
        for batch, definition in eligible:
            self.indicators.replace_results_for_months(
                segment_id=segment_id,
                indicator_definition_id=int(definition["id"]),
                login_to_user_id=login_map,
                rows=batch.rows,
                months=batch.months,
            )
            self.indicators.replace_breakdowns_for_months(
                segment_id=segment_id,
                indicator_definition_id=int(definition["id"]),
                rows=batch.breakdowns,
                months=batch.months,
            )
            self.freshness.record_indicator_data_through(
                ctx, segment_id, batch.indicator_key, batch.data_through, upload_source_key, upload_id
            )
            results.append(
                UploadProcessingResult(
                    source_key=upload_source_key,
                    indicator_key=batch.indicator_key,
                    indicator_name=str(definition["name"]),
                    data_through=batch.data_through,
                    analyst_count=batch.analyst_count,
                    total_volume=batch.total_volume,
                    daily_points=len(batch.rows),
                )
            )
        return results
