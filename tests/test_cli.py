# ABOUTME: Tests for the pyLBRY command line interface.
# ABOUTME: Parser tests need no daemon; command tests are marked live.
"""Tests for the pyLBRY command line interface."""

from pathlib import Path

import pytest

from pylbry.archive.archiver import ArchiveEvent
from pylbry.archive.store import DownloadState, Store
from pylbry.cli import EXIT_ERROR, EXIT_OK, EXIT_USAGE, build_parser, main, render
from pylbry.models import Claim

WORKERS = 4


def test_parser_reads_archive_channel_arguments() -> None:
    """The archive channel command captures its URL and worker count."""
    args = build_parser().parse_args(
        ["archive", "channel", "lbry://@chan", "--workers", "4"]
    )
    assert args.command == "archive"
    assert args.subcommand == "channel"
    assert args.url == "lbry://@chan"
    assert args.workers == WORKERS


def test_parser_defaults_the_archive_root() -> None:
    """The archive root defaults to the current directory."""
    args = build_parser().parse_args(["status"])
    assert args.root == Path()


def test_parser_rejects_an_unknown_command() -> None:
    """An unrecognised command exits with a usage error."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nonsense"])


def test_main_without_a_command_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running with no command prints usage and exits non-zero."""
    assert main([]) == EXIT_USAGE
    assert "usage" in capsys.readouterr().out


def test_render_writes_one_line_per_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Events render as a single aligned line."""
    render(ArchiveEvent(kind="fetched", claim_id="abcdef0123", detail="ok"))
    out = capsys.readouterr().out
    assert "fetched" in out
    assert "abcdef01" in out
    assert out.endswith("ok\n")


def test_status_reports_counts_on_an_empty_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Status prints the archive's state counts without needing a daemon."""
    assert main(["--root", str(tmp_path), "status"]) == EXIT_OK
    assert "claims: 0" in capsys.readouterr().out


def test_resolve_reports_a_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """An unreachable daemon prints an error and exits non-zero."""
    assert (
        main(
            [
                "--endpoint",
                "http://127.0.0.1:1",
                "resolve",
                "lbry://anything",
            ]
        )
        == EXIT_ERROR
    )
    assert "error" in capsys.readouterr().err.lower()


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_resolve_prints_a_claim(
    channel: Claim, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resolve prints the resolved claim's identity."""
    assert main(["resolve", channel.canonical_url]) == EXIT_OK
    out = capsys.readouterr().out
    assert channel.claim_id in out
    assert "channel" in out


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_archive_channel_indexes_and_reports(
    channel: Claim, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Archiving a channel indexes it and prints a per-state tally."""
    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "archive",
            "channel",
            channel.canonical_url,
            "--limit",
            "1",
            "--workers",
            "2",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == EXIT_OK
    assert "indexed" in out
    assert (tmp_path / "pylbry.db").exists()


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_archive_resume_runs_against_an_existing_archive(
    channel: Claim, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resume reconciles and continues without re-indexing."""
    main(
        [
            "--root",
            str(tmp_path),
            "archive",
            "channel",
            channel.canonical_url,
            "--limit",
            "1",
            "--workers",
            "2",
        ]
    )
    capsys.readouterr()
    assert (
        main(["--root", str(tmp_path), "archive", "resume", "--limit", "1"]) == EXIT_OK
    )


def test_status_lists_each_state_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Status prints a line per download state once the archive holds claims."""
    claim = Claim(
        claim_id="c" * 40,
        name="n",
        canonical_url="lbry://n",
        permanent_url="lbry://n#c",
        claim_type="stream",
        title=None,
        description=None,
        channel_id=None,
        channel_name=None,
        height=1,
        timestamp=None,
        sd_hash="sd",
        media_type="video/mp4",
        size=1,
        duration=None,
        raw={},
    )
    with Store(tmp_path / "pylbry.db") as store:
        store.upsert_claim(claim)

    assert main(["--root", str(tmp_path), "status"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "claims: 1" in out
    assert f"{DownloadState.PENDING}: 1" in out
