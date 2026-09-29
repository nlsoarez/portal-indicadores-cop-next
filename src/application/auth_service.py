from __future__ import annotations

from dataclasses import dataclass

from src.application.security import hash_password, verify_password
from src.infrastructure.repositories import AuditRepository, UserRepository


@dataclass(frozen=True)
class AuthResult:
    user_id: int
    login: str
    must_change_password: bool


class AuthService:
    def __init__(self, users: UserRepository | None = None, audit: AuditRepository | None = None):
        self.users = users or UserRepository()
        self.audit = audit or AuditRepository()

    def authenticate(self, login: str, password: str) -> AuthResult | None:
        row = self.users.get_credentials(login)
        if not row or not bool(row["active"]):
            return None
        if not verify_password(password, row["password_hash"], row["password_salt"]):
            return None
        user_id = int(row["id"])
        self.audit.record_access(user_id, "login")
        return AuthResult(user_id, str(row["login"]), bool(row["must_change_password"]))

    def change_password(self, user_id: int, new_password: str) -> None:
        if len(new_password) < 8:
            raise ValueError("A nova senha precisa ter pelo menos 8 caracteres")
        password_hash, salt = hash_password(new_password)
        self.users.change_password(user_id, password_hash, salt)
