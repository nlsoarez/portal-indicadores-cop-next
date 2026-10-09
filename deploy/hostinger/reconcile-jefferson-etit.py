"""Preview/reconcile Jefferson ETIT historical alias after a fresh backup.

Dry-run by default. Changes need explicit --apply (used by safe VPS wrapper).
"""
from __future__ import annotations

import argparse
import json

from src.application.etit_alias_recovery import recover_jefferson_etit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = recover_jefferson_etit(apply=args.apply)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.apply and result["status"] not in (
        "recovered", "already_recovered_or_reimported",
    ):
        raise RuntimeError("Reconciliação não confirmada")


if __name__ == "__main__":
    main()
