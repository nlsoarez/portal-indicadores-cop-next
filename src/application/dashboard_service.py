from __future__ import annotations

from src.application.access_service import AccessService
from src.domain.entities import AccessContext
from src.infrastructure.repositories import IndicatorRepository, UserRepository

CANCELLATION_KEY = "toa_cancellation_rate"


def _cancel_rate(stats: dict | None) -> float | None:
    if not stats:
        return None
    cancelled = int(stats["cancelled"])
    base = int(stats["etit_volume"])
    if base <= 0 or cancelled > base:
        return None
    return round(100.0 * cancelled / base, 1)


def _apply_personal_cancellation(payload: dict, stats: dict, segment_id: int, user_id: int) -> None:
    for row in payload.get("summary") or []:
        if row.get("indicator_key") != CANCELLATION_KEY:
            continue
        month_stats = stats.get((segment_id, user_id, str(row.get("period"))))
        cancelled = int(month_stats["cancelled"]) if month_stats else 0
        base = int(month_stats["etit_volume"]) if month_stats else 0
        row.update({
            "value": _cancel_rate(month_stats),
            "cancelled_count": cancelled,
            "etit_volume": base,
            "missing_etit_base": base <= 0,
            "incompatible_etit_base": base > 0 and cancelled > base,
        })
    # A taxa original é a proporção interna do analítico de Canceladas,
    # não a taxa sobre ETIT. Nunca mostrá-la como taxa oficial diária.
    for row in payload.get("individual") or []:
        if row.get("indicator_key") == CANCELLATION_KEY:
            row["value"] = None
    for row in payload.get("team_daily") or []:
        if row.get("indicator_key") == CANCELLATION_KEY:
            row["team_avg"] = None


def _apply_team_cancellation(row: dict, stats: dict, analyst_ids: set[int]) -> None:
    if row.get("indicator_key") != CANCELLATION_KEY:
        return
    segment = int(row["segment_id"])
    period = str(row["period"])
    scoped = [
        item for (sid, uid, month), item in stats.items()
        if sid == segment and uid in analyst_ids and month == period
    ]
    cancelled = sum(int(item["cancelled"]) for item in scoped)
    base = sum(int(item["etit_volume"]) for item in scoped)
    unmatched = sum(
        int(item["cancelled"]) for item in scoped
        if int(item["etit_volume"]) <= 0
        or int(item["cancelled"]) > int(item["etit_volume"])
    )
    valid = base > 0 and unmatched == 0 and cancelled <= base
    team_pct = round(cancelled * 100 / base, 1) if valid else None
    is_management = "value" in row
    row.update({
        "value" if is_management else "team_avg": team_pct,
        "volume" if is_management else "team_volume": base,
        "analysts" if is_management else "analysts_with_data":
            sum(int(item["etit_volume"]) > 0 for item in scoped),
        "team_cancelled_count": cancelled,
        "team_unmatched_cancelled": unmatched,
    })


class DashboardService:
    def __init__(
        self,
        access: AccessService | None = None,
        indicators: IndicatorRepository | None = None,
    ):
        self.access = access or AccessService()
        self.indicators = indicators or IndicatorRepository()

    def _analyst_ids(self, segment_id: int) -> set[int]:
        return {user.id for user in UserRepository().list_for_segment(segment_id)}

    def management_payload(self, ctx: AccessContext, segment_ids: list[int]) -> dict:
        if not (ctx.is_admin or ctx.is_subadmin):
            raise PermissionError("Visão gerencial disponível apenas para liderança")
        normalized = sorted({int(segment_id) for segment_id in segment_ids})
        for segment_id in normalized:
            self.access.assert_segment_access(ctx, segment_id)
        result = self.indicators.management_payload(
            normalized,
            include_external=ctx.is_admin,
        )
        stats = self.indicators.cancellation_etit_stats(normalized)
        team_ids = {
            sid: self._analyst_ids(sid) for sid in normalized
        }
        for row in result.get("segment_summary") or []:
            _apply_team_cancellation(
                row, stats, team_ids.get(int(row["segment_id"]), set())
            )
        for row in result.get("analyst_summary") or []:
            if row.get("indicator_key") != CANCELLATION_KEY:
                continue
            item = stats.get((
                int(row["segment_id"]), int(row["user_id"]),
                str(row["period"]),
            ))
            row["value"] = _cancel_rate(item)
            row["cancelled_count"] = int(item["cancelled"]) if item else 0
            row["etit_volume"] = int(item["etit_volume"]) if item else 0
        for row in result.get("daily_summary") or []:
            if row.get("indicator_key") == CANCELLATION_KEY:
                row["value"] = None
        return result

    def leader_peer_averages(self, ctx: AccessContext, segment_id: int) -> list[dict]:
        """Outros três líderes para indicadores comuns; ETIT mantém o mesmo setor."""
        if not ctx.is_subadmin or ctx.is_admin:
            raise PermissionError("Comparação entre líderes exige perfil de líder")
        self.access.assert_segment_access(ctx, segment_id)

        # Descarta a taxa bruta antiga de Canceladas (denominador incorreto).
        result = [
            item for item in self.indicators.leader_peer_averages(
                segment_id, ctx.user.id
            )
            if item["indicator_key"] != CANCELLATION_KEY
        ]
        stats = self.indicators.cancellation_etit_stats()
        memberships = self.indicators.leader_performance_pairs()
        peers = {}
        for (sid, uid, month), item in stats.items():
            if uid == ctx.user.id or (uid, sid) not in memberships:
                continue
            if item["source_volume"] <= 0:
                continue
            rate = _cancel_rate(item)
            if rate is None:
                continue
            # Só a competência mais recente de cada outro líder conta.
            previous = peers.get(uid)
            if previous is None or month > previous[0]:
                peers[uid] = (month, rate)
        if peers:
            periods = [item[0] for item in peers.values()]
            avg = sum(item[1] for item in peers.values()) / len(peers)
            result.append({
                "indicator_key": CANCELLATION_KEY,
                "peer_avg": round(avg, 1),
                "peer_count": len(peers),
                "oldest_period": min(periods),
                "newest_period": max(periods),
            })
        return result

    def analyst_payload(
        self,
        ctx: AccessContext,
        segment_id: int,
        target_user_id: int | None = None,
    ) -> dict:
        target_user_id = target_user_id or ctx.user.id
        self.access.assert_can_view_user(ctx, segment_id, target_user_id)
        result = self.indicators.dashboard_payload(segment_id, target_user_id)
        stats = self.indicators.cancellation_etit_stats([segment_id])
        _apply_personal_cancellation(result, stats, segment_id, target_user_id)
        analyst_ids = self._analyst_ids(segment_id)
        for row in result.get("team_averages") or []:
            # Personal team reference uses team_avg / team_volume fields.
            if row.get("indicator_key") != CANCELLATION_KEY:
                continue
            # The adjustment must happen in-place (shared with UI).
            row["segment_id"] = segment_id
            _apply_team_cancellation(row, stats, analyst_ids)
        return result
