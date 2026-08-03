# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

pyLBRY reads from and archives the LBRY network by speaking JSON-RPC to a local `lbrynet`
daemon. The library is the product; the CLI is a thin shell over it. The design and its
reasoning are in `docs/superpowers/specs/2026-08-02-pylbry-design.md` — read it before
making structural changes, and update it when one lands.

## Architecture

Dependencies run one way: `cli → archive → api → client → {errors, models}`. Nothing
depends upward.

```
src/pylbry/
  __init__.py      public exports only
  errors.py        exception hierarchy
  models.py        frozen dataclasses, from_dict parsers, JSON narrowers
  client.py        Client: endpoint, pooled session, call(), retry policy
  api/claims.py    resolve, resolve_many, search, iter_channel
  api/files.py     download (enqueue only), query
  archive/store.py SQLite schema and queries
  archive/archiver.py  index, reconcile, fetch, resume
  cli.py           argparse over the public API
```

Two rules this layout exists to enforce:

- **`client.py` is the only module that touches HTTP.** Timeouts, error unwrapping and
  retries live there and nowhere else.
- **The archiver calls typed API methods only, never `client.call()` directly.** Verbs
  belong in a namespace under `Client`; publishing will slot in as `api/publish.py`
  touching nothing that exists.

Runtime dependencies are `httpx` only. Adding one is a decision to discuss with Ben, not a
convenience.

## Daemon behaviour that shapes the code

These are established from the daemon's source and are the things most easily got wrong:

- **`get` returns once the first blob hits disk, not on completion.** Transfer continues
  inside the daemon. Completion is observed by polling `file_list`. Our database is always
  a lagging view of the daemon's truth, which is why `Archiver.reconcile()` runs before
  any resume.
- **The `FileRef` returned by `get` describes the request, not the outcome.** Its
  `completed` and `download_path` can both disagree with what the daemon actually did —
  `file_list` is the authority. If the daemon already holds a stream, it returns the
  existing file and ignores the `download_directory` you asked for, so record the path
  that comes back rather than the one you requested.
- **Failures arrive by four distinct routes**, and conflating them is the main hazard:
  transport (httpx exception), a JSON-RPC `error` object, an `error` key *inside* a
  successful result, and per-URL error entries in a batch `resolve`. The first two are
  handled globally in `Client.call()`; the third is verb-scoped; the fourth is data
  (`ResolveFailure`), not an exception.
- **Retries cover idempotent reads only** — `resolve`, `claim_search`, `file_list`. `get`
  is never auto-retried: repeating it costs a `download_timeout` and whether a dead stream
  deserves another attempt is an archiving decision.
- **Paged `claim_search` can return the same claim twice and can miss others.** There is
  no unique sort key, so claims tied on the sort field shuffle between page requests.
  `iter_channel` dedupes; re-running an index is idempotent and picks up stragglers.

## Testing

Live daemon, **no mocks anywhere**, 100% branch coverage. Both halves are non-negotiable
and together they constrain how code gets written.

Error branches are provoked by misusing a real daemon: a closed port
(`http://127.0.0.1:1`) for transport failure, an unknown method name for `-32601`, a bogus
parameter for `-32602`, a nonexistent URI for an in-result failure. Daemon-free tests
(`store`, `cli`, pure helpers) use real SQLite files in `tmp_path` and real `main(argv)`
calls — no network dependency is not the same as a fake.

**When a branch cannot be provoked, extract the decision into a pure function rather than
reaching for `# pragma: no cover`.** `unseen()` in `api/claims.py` and
`should_retry()`/`backoff_delay()` in `client.py` exist for exactly this reason: real
inputs, unit-testable in both directions with no daemon, leaving only mechanism inline.
The repository currently has zero pragmas. Keep it that way; any that prove genuinely
necessary carry a justification comment.

Tests draw from one pinned channel (`PYLBRY_TEST_CHANNEL`) and reuse media the daemon
already holds before starting any transfer. Downloads are real and large — never write a
test that starts a fresh one when an existing file will do. Tests touching daemon state
carry `@pytest.mark.xdist_group("daemon_state")` to pin them to a single worker.

## Gates

Every one of these must pass before a commit:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest --cov-fail-under=100
```

`--cov-fail-under` is deliberately absent from `addopts`, so single-test runs during
development do not fail the threshold. The 100% requirement applies to full-suite runs.
CI runs the three static gates only; functional tests need a daemon and run locally.

Conventions the linters enforce, and the ones they cannot:

- **`ANN401` bans bare `Any`.** `Client.call()` returns the recursive `JSONValue` alias and
  the `as_*`/`opt_*` narrowers in `models.py` turn it into structure. Reaching for
  `dict[str, Any]` defeats the entire type story.
- **`T20` bans `print`.** The archiver emits `ArchiveEvent`s through a callback; only
  `cli.py` renders. It is the sole per-file exemption.
- **Google-style docstrings on every function**, private ones included — ruff's `D` rules
  only reach public objects, so private docstrings are convention. `DOC` checks that
  documented `Args`/`Returns`/`Raises` match the signature.
- **Two `# ABOUTME:` comment lines at the top of every file**, above the module docstring.
  Inside it they trip `D205`.
- `ty` runs with `all = "error"`. If a rule fights the daemon's untyped JSON, downgrade
  that *named* rule with a justification. Never a blanket relaxation.

## Working here

- Run `uv run ruff format` after editing; the `--check` gate will otherwise fail on
  formatting you did not intend to argue with.
- There is no released version, so there is nothing to be backward compatible with. Replace
  code rather than deprecating it.
- Publishing, channel management, wallet writes and daemon auth are out of scope. The
  namespace split under `Client` is the designed extension point for the first three.
- A daemon whose wallet will not start reports `available_servers: 0`; the fix is in
  `~/.local/share/lbry/lbrynet/daemon_settings.yml` and is documented in `README.md`.
