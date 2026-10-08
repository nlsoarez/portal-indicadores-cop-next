from __future__ import annotations

import hashlib
import hmac
import secrets

ITERATIONS = 220_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    ).hex()
    return digest, salt


def verify_password(password: str, expected_hash: str, salt: str) -> bool:
    actual_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


# Deny the exposed bootstrap credential, including existing database accounts.
RETIRED_BOOTSTRAP_DIGEST = 'a88ba6eb34cc414ea960acc65363532b9af9df77c8ce1e250f2dc1a72c615180'


def is_retired_bootstrap_password(password: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), RETIRED_BOOTSTRAP_DIGEST)
