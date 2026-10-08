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

        # Segurança no backend: mesmo que a base ainda tenha grants legados
        # para os três segmentos, um líder só acessa seu segmento operacional.
        if ctx.is_subadmin and not ctx.is_admin:
            performance_ids = {
                segment.id
                for segment in self.users.performance_segments_for_user(ctx.user.id)
            }
            if segment_id not in performance_ids:
                raise PermissionError(
                    "Líder não pode acessar indicadores de outro segmento"
                )

    def visible_users(self, ctx: AccessContext, segment_id: int) -> list[User]:
        self.assert_segment_access(ctx, segment_id)
        if ctx.is_admin or ctx.is_subadmin:
            return self.users.list_for_segment(segment_id)
        return [ctx.user]

    def visible_subadmins(self, ctx: AccessContext) -> list[User]:
        if not ctx.is_admin:
            raise PermissionError("Somente o administrador pode consultar a lista de líderes")
        return self.users.list_subadmins()

    def assert_can_view_user(self, ctx: AccessContext, segment_id: int, target_user_id: int) -> None:
        self.assert_segment_access(ctx, segment_id)

        # O líder possui indicadores próprios em seu segmento, embora tenha
        # apenas a role subadmin. Outros líderes continuam fora do alcance.
        if ctx.is_subadmin and not ctx.is_admin and target_user_id == ctx.user.id:
            return

        if not ctx.is_admin and not ctx.is_subadmin:
            if target_user_id != ctx.user.id:
                raise PermissionError("Analista não pode consultar dados individuais de outro analista")
            return

        allowed = self.users.can_view_user_in_segment(
            target_user_id,
            segment_id,
            include_subadmins=ctx.is_admin,
        )
        if allowed:
            return

        if ctx.is_subadmin:
            raise PermissionError("Subadmin pode consultar somente dados individuais de analistas")
        raise PermissionError("Usuário-alvo não pertence ao escopo gerencial do segmento")
