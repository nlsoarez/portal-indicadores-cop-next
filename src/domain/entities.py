from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RoleCode(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"


@dataclass(frozen=True)
class User:
    id: int
    login: str
    full_name: str
    display_name: str
    active: bool


@dataclass(frozen=True)
class Segment:
    id: int
    slug: str
    name: str
    active: bool


@dataclass(frozen=True)
class AccessContext:
    user: User
    roles: frozenset[RoleCode]
    segment_ids: frozenset[int]

    @property
    def is_admin(self) -> bool:
        return RoleCode.ADMIN in self.roles

    @property
    def is_analyst(self) -> bool:
        return RoleCode.ANALYST in self.roles
