#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Wordpress.scripts.admin import (
    backfill_published_report_cards,
    provision,
    seed_homepages,
    sync_profiles,
)

CommandHandler = Callable[[], None]
COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "provision": provision.main,
    "seed-homepages": seed_homepages.main,
    "sync-profiles": sync_profiles.main,
    "backfill-published-report-cards": backfill_published_report_cards.main,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Canonical Market Lense WordPress REST administration CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMAND_HANDLERS:
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate command selection without external mutations.",
        )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    handlers: dict[str, CommandHandler] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.dry_run:
        print(f"Dry run: WordPress admin command '{args.command}' is available.")
        return 0
    selected_handlers = handlers or COMMAND_HANDLERS
    selected_handlers[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
