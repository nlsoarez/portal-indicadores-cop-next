from __future__ import annotations

from src.domain.entities import AccessContext, User
from src.infrastructure.repositories import UserRepository


class AccessService:
    """Autorização server-side. A UI nunca decide quais registros o usuário pode receber."""

    def __init__(self, users: UserRepository | None = None):
        self.users = users or UserRepository()

    def context(self, user_id: int) -> AccessContext:
        return self.users.access_context(user_id)

    def assert_segment_access(self, ctx: AccessContext, segment_id: int) -> None:
        if segment_id not in ctx.segment_ids:
            raise PermissionError("Usuário não pertence ao segmento solicitado")

    def visible_users(self, ctx: AccessContext, segment_id: int) -> list[User]:
        self.assert_segment_access(ctx, segment_id)
        if ctx.is_admin:
            return self.users.list_for_segment(segment_id)
        # Fail-closed: analista recebe apenas a própria entidade.
        return [ctx.user]

    def assert_can_view_user(self, ctx: AccessContext, segment_id: int, target_user_id: int) -> None:
        self.assert_segment_access(ctx, segment_id)
        if ctx.is_admin:
            segment_users = {user.id for user in self.users.list_for_segment(segment_id)}
            if target_user_id not in segment_users:
                raise PermissionError("Usuário-alvo não pertence ao segmento")
            return
        if target_user_id != ctx.user.id:
            raise PermissionError("Analista não pode consultar dados individuais de outro analista")
