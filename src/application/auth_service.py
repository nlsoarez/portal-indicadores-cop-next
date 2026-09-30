from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.application.security import hash_password, verify_password
from src.domain.entities import AccessContext
from src.infrastructure.repositories import AuditRepository, LoginThrottleRepository, UserRepository


@dataclass(frozen=True)
class AuthResult:
    user_id: int
    login: str
    must_change_password: bool
    auth_version: int


LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_FAILURE_THRESHOLD = 5
LOGIN_BACKOFF_BASE_SECONDS = 5
LOGIN_BACKOFF_MAX_SECONDS = 60


def _as_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class AuthService:
    def __init__(
        self,
        users: UserRepository | None = None,
        audit: AuditRepository | None = None,
        throttle: LoginThrottleRepository | None = None,
    ):
        self.users = users or UserRepository()
        self.audit = audit or AuditRepository()
        self.throttle = throttle or LoginThrottleRepository()

    def authenticate(self, login: str, password: str) -> AuthResult | None:
        normalized = login.strip().upper()
        if not normalized:
            return None

        now = datetime.now(timezone.utc)
        if self._is_blocked(normalized, now):
            return None

        row = self.users.get_credentials(normalized)
        if not row or not bool(row["active"]):
            return None
        if not verify_password(password, row["password_hash"], row["password_salt"]):
            self._record_failure(normalized, now)
            return None

        self.throttle.clear(normalized)
        user_id = int(row["id"])
        self.audit.record_access(user_id, "login")
        return AuthResult(
            user_id,
            str(row["login"]),
            bool(row["must_change_password"]),
            int(row["auth_version"]),
        )

    def _is_blocked(self, login: str, now: datetime) -> bool:
        state = self.throttle.get(login)
        if not state:
            return False
        blocked_until = _as_utc(state.get("blocked_until"))
        return bool(blocked_until and blocked_until > now)

    def _record_failure(self, login: str, now: datetime) -> None:
        state = self.throttle.get(login)
        window_started = _as_utc(state.get("window_started_at")) if state else None
        if window_started is None or now - window_started >= LOGIN_FAILURE_WINDOW:
            failure_count = 1
            window_started = now
        else:
            failure_count = int(state.get("failure_count") or 0) + 1

        blocked_until = None
        if failure_count >= LOGIN_FAILURE_THRESHOLD:
            exponent = min(failure_count - LOGIN_FAILURE_THRESHOLD, 4)
            delay_seconds = min(
                LOGIN_BACKOFF_BASE_SECONDS * (2 ** exponent),
                LOGIN_BACKOFF_MAX_SECONDS,
            )
            blocked_until = now + timedelta(seconds=delay_seconds)

        self.throttle.upsert(
            login,
            failure_count=failure_count,
            window_started_at=window_started.isoformat(),
            blocked_until=blocked_until.isoformat() if blocked_until else None,
        )

    def session_is_valid(self, user_id: int, auth_version: int) -> bool:
        current = self.users.get_auth_version(user_id)
        return current is not None and current == int(auth_version)

    def change_password(self, user_id: int, new_password: str) -> int:
        if len(new_password) < 8:
            raise ValueError("A nova senha precisa ter pelo menos 8 caracteres")
        password_hash, salt = hash_password(new_password)
        return self.users.change_password(user_id, password_hash, salt)
    def reset_password_as_admin(
        self,
        ctx: AccessContext,
        target_user_id: int,
        temporary_password: str,
    ) -> int:
        if not ctx.is_admin:
            raise PermissionError("Somente administradores podem resetar senhas")
        if len(temporary_password) < 8:
            raise ValueError("A senha temporária precisa ter pelo menos 8 caracteres")
        target = self.users.get_by_id(target_user_id)
        if not target or not target.active:
            raise ValueError("Usuário inexistente ou inativo")
        password_hash, salt = hash_password(temporary_password)
        return self.users.reset_password(target_user_id, password_hash, salt)
