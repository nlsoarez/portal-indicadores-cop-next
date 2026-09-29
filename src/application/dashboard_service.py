from __future__ import annotations

from src.application.access_service import AccessService
from src.domain.entities import AccessContext
from src.infrastructure.repositories import IndicatorRepository, ScaleRepository


class DashboardService:
    def __init__(
        self,
        access: AccessService | None = None,
        indicators: IndicatorRepository | None = None,
        scales: ScaleRepository | None = None,
    ):
        self.access = access or AccessService()
        self.indicators = indicators or IndicatorRepository()
        self.scales = scales or ScaleRepository()

    def analyst_payload(
        self,
        ctx: AccessContext,
        segment_id: int,
        target_user_id: int | None = None,
    ) -> dict:
        target_user_id = target_user_id or ctx.user.id
        self.access.assert_can_view_user(ctx, segment_id, target_user_id)
        return {
            "individual": self.indicators.results_for_user(segment_id, target_user_id),
            "summary": self.indicators.monthly_summary_for_user(segment_id, target_user_id),
            "team_averages": self.indicators.team_monthly_summary(segment_id),
            "freshness": self.indicators.freshness(segment_id),
            "scale": self.scales.for_user(segment_id, target_user_id),
        }
