from __future__ import annotations

from src.application.access_service import AccessService
from src.domain.entities import AccessContext
from src.infrastructure.repositories import IndicatorRepository


class DashboardService:
    def __init__(
        self,
        access: AccessService | None = None,
        indicators: IndicatorRepository | None = None,
    ):
        self.access = access or AccessService()
        self.indicators = indicators or IndicatorRepository()

    def management_payload(self, ctx: AccessContext, segment_ids: list[int]) -> dict:
        if not (ctx.is_admin or ctx.is_subadmin):
            raise PermissionError("Visão gerencial disponível apenas para liderança")
        normalized = sorted({int(segment_id) for segment_id in segment_ids})
        for segment_id in normalized:
            self.access.assert_segment_access(ctx, segment_id)
        return self.indicators.management_payload(
            normalized,
            include_external=ctx.is_admin,
        )

    def leader_peer_averages(self, ctx: AccessContext, segment_id: int) -> list[dict]:
        """Referências agregadas dos outros líderes do mesmo setor do usuário."""
        if not ctx.is_subadmin or ctx.is_admin:
            raise PermissionError("Comparação entre líderes exige perfil de líder")
        self.access.assert_segment_access(ctx, segment_id)
        # O ID excluído é SEMPRE o usuário autenticado, nunca um ID da UI.
        return self.indicators.leader_peer_averages(segment_id, ctx.user.id)

    def analyst_payload(
        self,
        ctx: AccessContext,
        segment_id: int,
        target_user_id: int | None = None,
    ) -> dict:
        target_user_id = target_user_id or ctx.user.id
        self.access.assert_can_view_user(ctx, segment_id, target_user_id)
        return self.indicators.dashboard_payload(segment_id, target_user_id)
