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

    def analyst_payload(
        self,
        ctx: AccessContext,
        segment_id: int,
        target_user_id: int | None = None,
    ) -> dict:
        target_user_id = target_user_id or ctx.user.id
        self.access.assert_can_view_user(ctx, segment_id, target_user_id)
        return self.indicators.dashboard_payload(segment_id, target_user_id)
