from __future__ import annotations

import argparse
import json
import sys

from src.integrations.m365_etit import EtitM365Pilot, M365TokenProvider


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Piloto Microsoft 365 para ETIT Residencial e Empresarial."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "login",
        help="Autentica via device code e persiste o cache de token no servidor.",
    )
    sub.add_parser(
        "status",
        help="Mostra configuração e último estado local sem acessar o Graph.",
    )
    sub.add_parser(
        "probe",
        help="Valida autenticação, pastas e identifica os arquivos ETIT mais recentes.",
    )
    sync_parser = sub.add_parser(
        "sync",
        help="Sincroniza arquivos alterados e processa no portal.",
    )
    sync_parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa mesmo quando o arquivo remoto não mudou.",
    )

    args = parser.parse_args(argv)
    pilot = EtitM365Pilot()

    try:
        if args.command == "login":
            result = M365TokenProvider().device_login()
            _print({"status": "authenticated", **result})
            return 0

        if args.command == "status":
            _print(pilot.status())
            return 0

        if args.command == "probe":
            result = pilot.probe()
            _print(result)
            return 0 if all(
                row.get("status") == "ok"
                for row in result.get("sources", {}).values()
            ) else 2

        if args.command == "sync":
            result = pilot.sync(force=bool(args.force))
            _print(result)
            return 0 if all(
                row.get("status") in {"updated", "unchanged"}
                for row in result.get("sources", {}).values()
            ) else 2
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
