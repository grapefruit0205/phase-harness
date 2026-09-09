"""Command line interface for phase-harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core import HarnessError, PhaseRunner, import_legacy_phase, initial_progress, validate_config, _load, atomic_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="phase-harness")
    result.add_argument("--project", default=".")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--repair", metavar="PHASE")
    mode.add_argument("--retry-role", choices=["verify"])
    mode.add_argument("--migrate-legacy", metavar="PHASE")
    result.add_argument("--phase")
    result.add_argument("--through")
    result.add_argument("--allow-deploy", action="store_true")
    result.add_argument("--target-status", choices=["ready_verify", "completed"])
    result.add_argument("--receipt")
    result.add_argument("--snapshot")
    result.add_argument("--baseline", action="append", default=[])
    result.add_argument("--authorize-path", action="append", default=[])
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    try:
        if args.phase and args.retry_role != "verify":
            raise HarnessError("--phase is only valid with --retry-role verify")
        if args.init:
            config = validate_config(_load(root / "orchestration.json"))
            progress = root / "progress.json"
            if progress.exists():
                raise HarnessError("progress.json already exists")
            atomic_json(progress, initial_progress(config))
            return 0
        if args.migrate_legacy:
            if not args.receipt or not args.target_status:
                raise HarnessError("migration requires --receipt and --target-status")
            import_legacy_phase(
                root, root / "orchestration.json", root / "progress.json",
                phase_id=args.migrate_legacy, receipt_path=Path(args.receipt),
                target_status=args.target_status,
                snapshot_path=Path(args.snapshot) if args.snapshot else None,
                baseline_roots=args.baseline, authorized_paths=args.authorize_path,
            )
            return 0
        with PhaseRunner(root, allow_deploy=args.allow_deploy) as runner:
            if args.dry_run:
                print(json.dumps(runner.plan(args.through), indent=2))
                return 0
            if args.run:
                return 0 if runner.run(args.through) else 1
            if args.repair:
                return 0 if runner.repair(args.repair) else 1
            if args.retry_role == "verify":
                if not args.phase:
                    raise HarnessError("--retry-role verify requires --phase")
                return 0 if runner.retry_verify(args.phase) else 1
    except HarnessError as exc:
        print(f"phase-harness: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
