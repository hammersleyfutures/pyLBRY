# ABOUTME: Command line shell over the pyLBRY public API.
# ABOUTME: The only module permitted to print; rendering lives here alone.
"""Command line shell over the pyLBRY public API."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pylbry.archive.archiver import ArchiveEvent, Archiver
from pylbry.archive.store import Store
from pylbry.client import DEFAULT_ENDPOINT, Client
from pylbry.errors import PyLBRYError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
DEFAULT_WORKERS = 8


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser.

    Returns:
        A parser covering every pylbry command.
    """
    # Shared options are accepted on either side of the subcommand. The real
    # defaults live on the top-level parser; the subparser copies suppress
    # theirs, so an unused copy cannot overwrite a value given before the
    # subcommand. Giving the top level suppressed defaults instead and relying
    # on set_defaults does not work: the subcommand merge clobbers the value.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--endpoint", default=argparse.SUPPRESS, help="lbrynet daemon URL"
    )
    common.add_argument(
        "--root", type=Path, default=argparse.SUPPRESS, help="archive root directory"
    )

    parser = argparse.ArgumentParser(prog="pylbry")
    parser.add_argument(
        "--endpoint", default=DEFAULT_ENDPOINT, help="lbrynet daemon URL"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(), help="archive root directory"
    )
    commands = parser.add_subparsers(dest="command")

    archive = commands.add_parser(
        "archive", help="archive claims and media", parents=[common]
    )
    archive_commands = archive.add_subparsers(dest="subcommand", required=True)

    channel = archive_commands.add_parser(
        "channel", help="archive a whole channel", parents=[common]
    )
    channel.add_argument("url", help="channel URL or claim ID")
    channel.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    channel.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many downloads; without it the whole channel "
        "is fetched, which can be many gigabytes",
    )

    resume = archive_commands.add_parser(
        "resume", help="continue an interrupted archive", parents=[common]
    )
    resume.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    resume.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many downloads; without it every outstanding "
        "claim is fetched",
    )

    commands.add_parser("status", help="report archive state counts", parents=[common])

    resolve = commands.add_parser(
        "resolve", help="resolve a single URL", parents=[common]
    )
    resolve.add_argument("url", help="LBRY URL to resolve")

    return parser


def render(event: ArchiveEvent) -> None:
    """Print one archive event.

    Args:
        event: The event to render.
    """
    print(f"{event.kind:>12}  {event.claim_id[:8]}  {event.detail}")


def _archive(args: argparse.Namespace, client: Client) -> int:
    """Run an archive subcommand.

    Args:
        args: Parsed arguments.
        client: Connected daemon client.

    Returns:
        Process exit code.
    """
    workers = getattr(args, "workers", DEFAULT_WORKERS)
    with Archiver(client, args.root, workers=workers, on_event=render) as archiver:
        if args.subcommand == "resume":
            archiver.resume(limit=args.limit)
        else:
            channel = client.claims.resolve(args.url)
            indexed = archiver.index_channel(channel.claim_id)
            print(f"indexed {indexed} claims")
            archiver.fetch_pending(limit=args.limit)
        # A get reports a stream as incomplete even when the daemon already
        # holds it in full, and transfers continue after it returns. The
        # archive's true state therefore comes from reconciling, not from what
        # enqueueing returned.
        archiver.reconcile()
        for state, count in sorted(archiver.counts().items()):
            print(f"{state}: {count}")
        print("downloads continue in the daemon; run 'archive resume' to update")
    return EXIT_OK


def _status(args: argparse.Namespace) -> int:
    """Print archive state counts.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    with Store(args.root / "pylbry.db") as store:
        print(f"claims: {store.claim_count()}")
        for state, count in sorted(store.counts().items()):
            print(f"{state}: {count}")
    return EXIT_OK


def _resolve(args: argparse.Namespace, client: Client) -> int:
    """Resolve one URL and print its identity.

    Args:
        args: Parsed arguments.
        client: Connected daemon client.

    Returns:
        Process exit code.
    """
    claim = client.claims.resolve(args.url)
    print(f"{claim.claim_id}  {claim.claim_type}  {claim.title or claim.name}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    if args.command == "status":
        return _status(args)
    try:
        with Client(args.endpoint) as client:
            if args.command == "archive":
                return _archive(args, client)
            return _resolve(args, client)
    except PyLBRYError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
