from __future__ import annotations

import hashlib
import hmac
import time

from dataclasses import dataclass

from src.application.security import hash_password, verify_password, is_retired_bootstrap_password
from src.domain.entities import AccessContext
from src.infrastructure.repositories import AuditRepository, UserRepository


@dataclass(frozen=True)
class AuthResult:
    user_id: int
    login: str
    must_change_password: bool
    credential_version: str


class AuthService:
    def __init__(self, users: UserRepository | None = None, audit: AuditRepository | None = None):
        self.users = users or UserRepository()
        self.audit = audit or AuditRepository()

    def authenticate(self, login: str, password: str) -> AuthResult | None:
        if len(login) > 128 or len(password) > 1024:
            return None
        normalized = login.strip().upper()
        # Hash identifiers so the limiter table does not store attempted logins.
        key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        window_start = int(time.time()) // 60 * 60
        if not self.users.reserve_login_attempt(key, window_start):
            return None
        if is_retired_bootstrap_password(password):
            return None
        row = self.users.get_credentials(normalized)
        if not row or not bool(row["active"]):
            return None
        if not verify_password(password, row["password_hash"], row["password_salt"]):
            return None
        user_id = int(row["id"])
        self.audit.record_access(user_id, "login")
        return AuthResult(user_id, str(row["login"]), bool(row["must_change_password"]), str(row["password_salt"]))

    def validate_session(self, user_id: int, credential_version: str):
        row = self.users.session_credentials(user_id)
        if not row or not bool(row["active"]) or not credential_version:
            raise PermissionError("Sessão expirada. Entre novamente.")
        if not hmac.compare_digest(str(row["password_salt"]), credential_version):
            raise PermissionError("Sessão revogada. Entre novamente.")
        return bool(row["must_change_password"])

    def change_password(self, user_id: int, new_password: str) -> None:
        if len(new_password) < 8 or len(new_password) > 1024 or is_retired_bootstrap_password(new_password):
            raise ValueError("A nova senha precisa ter entre 8 e 1024 caracteres e não pode ser a credencial inicial antiga")
        password_hash, salt = hash_password(new_password)
        self.users.change_password(user_id, password_hash, salt)

    def reset_password_as_admin(
        self,
        ctx: AccessContext,
        target_user_id: int,
        temporary_password: str,
    ) -> None:
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem resetar senhas")
        if len(temporary_password) < 8 or len(temporary_password) > 1024 or is_retired_bootstrap_password(temporary_password):
            raise ValueError("A senha temporária precisa ter entre 8 e 1024 caracteres e não pode ser a credencial inicial antiga")
        target = self.users.get_by_id(target_user_id)
        if not target or not target.active:
            raise ValueError("Usuário inexistente ou inativo")
        password_hash, salt = hash_password(temporary_password)
        self.users.reset_password(target_user_id, password_hash, salt)
