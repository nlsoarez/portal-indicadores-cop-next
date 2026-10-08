"""Credential maintenance through a trusted server terminal, never a public route."""
from __future__ import annotations

import argparse
from getpass import getpass

from src.application.security import hash_password, is_retired_bootstrap_password, verify_password
from src.infrastructure.database import transaction
from src.infrastructure.repositories import UserRepository
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Manutenção local de credenciais do portal")
    sub = parser.add_subparsers(dest="command", required=True)
    provision = sub.add_parser("set-password")
    provision.add_argument("login")
    sub.add_parser("retire-password")
    args = parser.parse_args()
    if args.command == "set-password":
        user = UserRepository().get_by_login(args.login)
        if not user or not user.active:
            parser.error("Conta inexistente ou inativa; este comando não reativa contas")
        password = getpass("Senha temporária individual: ")
        confirmation = getpass("Confirme: ")
        if password != confirmation or not 12 <= len(password) <= 1024 or is_retired_bootstrap_password(password):
            parser.error("Use uma senha individual de pelo menos 12 caracteres e confirme corretamente")
        digest, salt = hash_password(password)
        UserRepository().reset_password(user.id, digest, salt)
        print("Credencial definida; sessões anteriores revogadas. Troca obrigatória no próximo acesso.")
    else:
        old_password = getpass("Senha antiga compartilhada a invalidar: ")
        if not old_password:
            parser.error("Informe a credencial antiga")
        count = 0
        with transaction() as conn:
            rows = conn.execute("SELECT id,password_hash,password_salt FROM users").fetchall()
            for row in rows:
                if verify_password(old_password, row["password_hash"], row["password_salt"]):
                    digest, salt = hash_password(secrets.token_urlsafe(32))
                    conn.execute(
                        "UPDATE users SET password_hash=?,password_salt=?,must_change_password=1 "
                        "WHERE id=? AND password_hash=? AND password_salt=?",
                        (digest, salt, row["id"], row["password_hash"], row["password_salt"]),
                    )
                    count += 1
        print(f"Credencial antiga invalidada em {count} contas. Provisione senhas individuais antes do acesso.")


if __name__ == "__main__":
    main()
