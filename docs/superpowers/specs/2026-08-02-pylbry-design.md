# pyLBRY design

Date: 2026-08-02
Status: approved

## Purpose

pyLBRY is a Python library for reading from and archiving the LBRY network, with a thin
CLI over it. Scope, in priority order:

1. Read and download content — resolve claims, search, enumerate channels, fetch streams.
2. Archive at scale — bulk capture of claims and media with durable, resumable state.
3. Publish and manage — **designed for, not built.** Publishing, channel management and
   wallet operations must slot in later without reworking what exists.

## Context

The upstream reference implementation, `lbryio/lbry-sdk`, is dormant: last commit to
`master` was August 2024, last release `v0.113.0` in January 2023. It is not archived,
but it is not moving. This makes it a stable target rather than a moving one, and means
"what still works on the live network" is an empirical question rather than a
documentation question.

`belikor/lbrytools` (MIT, last touched September 2023) is prior art. Its domain knowledge
is valuable — blob accounting, peer lookup, channel enumeration, claim-search paging. Its
structure is what to avoid:

- `server="http://localhost:5279"` threaded through nearly every public function, because
  there is no client object for connection state to live in. This is the root cause of its
  ~50 flat repetitive modules.
- Retrieval and presentation fused — many functions fetch *and* print, so they do not compose.
- No error-envelope handling: `output["result"]["data_dir"]` indexed directly, so an RPC
  error surfaces as a `KeyError`.
- `check_lbry()` launches the daemon as a side effect of a function named "check".

## Decisions

| Decision | Choice |
| --- | --- |
| Transport | Requires a running local `lbrynet` daemon, over JSON-RPC |
| Concurrency | Synchronous API; concurrency confined to the archive layer |
| Persistence | Media files on disk plus a SQLite index |
| Testing | No mocks anywhere; a live daemon for every network path |
| Deliverable | Library plus a thin CLI |
| Runtime dependencies | `httpx` only |

The daemon requirement decouples runtimes: `lbry-sdk` is an old asyncio codebase that will
not run on Python 3.14, but it runs in its own environment or container and we speak to it
over HTTP.

## Architecture

Strict one-way dependency: `cli → archive → api → client → {errors, models}`. Nothing
depends upward. The archiver calls typed API methods only, never raw `call()`. That
constraint is what keeps the later publish work cheap.

```
src/pylbry/
  __init__.py      public exports only
  errors.py        exception hierarchy
  models.py        frozen dataclasses and from_dict parsers
  client.py        Client: endpoint, pooled session, call(), namespace wiring
  api/
    claims.py      resolve, search, channel enumeration
    files.py       enqueue download, query
  archive/
    store.py       SQLite schema and queries
    archiver.py    enqueue pool, poll loop, resume
  cli.py           thin shell over the public API
```

`Client` is transport only — endpoint, one pooled HTTP session, timeouts, error unwrapping.
Verbs live in namespaces reached through it: `client.claims.resolve(url)`,
`client.files.query(...)`. A `Client` carrying every verb becomes a god object; the namespace
split is where `publish.py` slots in later as a sibling, touching nothing that exists.

### Dependency choices

- **`httpx`** — explicit timeouts and real connection pooling, which matter when issuing
  thousands of short RPCs at one local daemon.
- **`dataclasses`, not pydantic** — we parse JSON from a daemon we do not control. Pydantic
  would put a heavy third-party type in our public API that every consumer inherits.
- **stdlib `sqlite3`** — no ORM.
- **stdlib `argparse`** — for a thin CLI, Typer's ergonomics do not justify a dependency.

## Transport and error model

Requests POST to `/` (also served at `/lbryapi`, `daemon.py:364-366`) as
`{"method": ..., "params": {...}}`. Responses are JSON-RPC 2.0 shaped —
`{"jsonrpc":"2.0","result":...}` or `{"jsonrpc":"2.0","error":{...}}` (`daemon.py:286-290`).

Failures arrive by **four** distinct routes. Conflating them is the main thing to get right.

1. **Transport** — daemon unreachable. Surfaces as an `httpx` exception.
2. **JSON-RPC error object**, codes at `daemon.py:213-219`: `-32601` method not found,
   `-32602` invalid params, `-32603` internal, `-32500` application, `-32501` auth. These
   also map to HTTP 400/404/500 (`daemon.py:231-236`).
3. **`{"error": "..."}` inside a successful result.** `jsonrpc_get` does this at
   `daemon.py:1147`. A failed download and a successful one are indistinguishable at the
   HTTP layer.
4. **Per-item errors in a batch.** `resolve` accepts a list and returns a map keyed by URL
   whose individual entries may be error objects (`file_manager.py:104-110`).

### Exception hierarchy

```
PyLBRYError
├── DaemonUnavailableError     channel 1
├── RPCError                   channel 2; carries .code and .message
│   ├── MethodNotFoundError    -32601
│   ├── InvalidParamsError     -32602
│   └── DaemonInternalError    -32603 / -32500
└── OperationFailedError       channel 3; carries the raw daemon message
```

Channel 4 is not an exception — see `ResolveFailure` under Models.

We deliberately do **not** define an exception for `-32501` (auth) or `-32700` (parse).
An unauthenticated localhost daemon never emits the former, and the latter is not sent to a
well-formed client. Unmapped codes fall through to a generic `RPCError` carrying the raw
code. This is required by the 100% coverage target: we map only what we can provoke.

`Client.call()` handles channels 1 and 2 globally. **Channel 3 is verb-scoped**, applied by
a shared helper in the verbs that need it — a blanket "is there an `error` key?" check risks
false positives against result shapes we do not control.

`OperationFailedError` carries the raw message and we do **not** pattern-match it into
subclasses. Upstream produces these via `str(e)` on arbitrary exceptions, so the strings are
unstable; parsing them would be a fragile guess dressed as typing.

### Retries and timeouts

Connection errors and 5xx get bounded retry with backoff, **for idempotent reads only**
(`resolve`, `claim_search`, `file_list`). `get` is never auto-retried; the archiver owns
that decision, because retry policy for a dead stream is an archiving question.

**Timeout inversion is the subtlest hazard here.** `get` blocks server-side for up to the
daemon's `download_timeout` (default 30s). If our HTTP read timeout is lower, we abandon the
request while the daemon continues downloading, recording a failure for content that
actually arrives. The client read timeout must exceed the daemon's download timeout, and
`get` takes a per-call override rather than sharing the default used by fast reads.

Auth exists in the protocol but localhost daemons are unauthenticated by default. Not built;
the endpoint stays configurable so fronting the daemon later is not a rewrite.

## Models and read API

JSON is recursive and Python 3.14 can say so, which is what makes banning `Any` satisfiable:

```python
type JSONValue = (
    str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None
)
```

`Client.call()` returns `JSONValue`; `from_dict` classmethods narrow it. Without this, a
JSON-RPC client is a machine for turning `Any` into structure and the `ANN401` ban would be
`# noqa`'d everywhere.

Models are frozen with `slots=True`:

- `Claim` — `claim_id`, `name`, `canonical_url`, `permanent_url`, `claim_type`, `title`,
  `description`, `channel_id`, `channel_name`, `height`, `timestamp`, `sd_hash`,
  `media_type`, `size`, `duration`, and `raw: Mapping[str, JSONValue]`.
- `FileRef` — `claim_id`, `sd_hash`, `file_name`, `download_path`, `status`, `completed`,
  `written_bytes`, `total_bytes`, `blobs_completed`, `blobs_in_stream`.
- `Page[T]` — `items`, `page`, `page_size`, `total_pages | None`.
- `ResolveFailure` — `url`, `message`.

`raw` is kept deliberately. For an archive, fidelity beats tidiness: a field we did not think
to model is not lost if the network goes dark. Typed attributes are the ergonomic surface,
not the archival record.

### Verbs

```python
client.claims.resolve(url)        -> Claim                         # raises on failure
client.claims.resolve_many(urls)  -> dict[str, Claim | ResolveFailure]
client.claims.search(**filters)   -> Page[Claim]
client.claims.iter_channel(channel_id, *, has_source=True) -> Iterator[Claim]
client.files.download(uri, *, timeout=None) -> FileRef             # enqueue only
client.files.query(**filters)     -> Page[FileRef]
```

Single-URL `resolve` raises; batch `resolve_many` never does. Archiving uses the batch form
and records failures as data, so one dead URL cannot fail a batch of 200.

`iter_channel` is the archiver's workhorse: a generator paging via `claim_search` with
`--no_totals` (`daemon.py:2597-2598`) and `--has_source` (`daemon.py:2517`). Requesting
totals on every page makes bulk enumeration quadratic work for the daemon; an archiver only
needs to know when a page comes back short.

## Download semantics

Established from source, and it drives the archiver design:

1. `get <uri>` (`daemon.py:1113`) resolves the claim with a 3s resolve timeout, starts the
   stream, then calls `save_file()`.
2. `save_file` (`managed_stream.py:302`) spawns `_save_file` as a **background task** and
   awaits only `started_writing` (`managed_stream.py:322-324`).
3. **`get` therefore returns once the first bytes hit disk, not on completion.** Transfer
   continues inside the daemon after the call returns.
4. Completion is observed by polling `file_list` (`daemon.py:2102`), which filters on
   `--completed`, `--claim_id`, `--channel_name`, `--status` and pages via
   `--page`/`--page_size`.

Consequences: bulk transfer is not held on our connection, so the heavy concurrency lives in
the daemon's event loop. Firing hundreds of concurrent `get` calls does not download faster.
But `get` blocks up to `download_timeout` when a stream will not start — common on a dormant
network — so sequential enqueueing stalls badly. A bounded pool of 8–16 is the requirement:
enough to hide dead-stream stalls, not so much that we queue pointlessly inside the daemon.

## Archiver

Two phases per channel, and the order is the point.

1. **Index** — `iter_channel` upserts claims and inserts `download` rows as `pending`.
   Fast, small, no media.
2. **Fetch** — pull `pending`, enqueue through the pool, poll to completion.

Metadata is captured even if media fetching never finishes. On a dormant network a completed
index is worth more than an incomplete media archive.

### Schema

`archive/store.py`, stdlib `sqlite3`, WAL mode.

```sql
claim(claim_id PK, canonical_url, channel_id, channel_name, name, title,
      sd_hash, media_type, size, height, timestamp,
      raw TEXT NOT NULL,              -- complete claim JSON
      first_seen, last_seen)

download(claim_id PK REFERENCES claim, state, path, bytes_total, bytes_written,
         attempts INTEGER NOT NULL DEFAULT 0, last_error, updated_at)

channel_sync(channel_id PK, last_run_at, last_height)
```

Indexed on `download(state)` and `claim(channel_id)`.

### State machine

`pending → running → complete | failed | unavailable`

`unavailable` means the stream would not start — nothing is seeding it. That is not a
transient error, and retrying it every run burns 30 seconds of `download_timeout` per claim
forever. `failed` means something worth retrying, bounded by `attempts`.

### Resume

Resume is a query, not a journal:
`state IN ('pending','failed') AND attempts < max`.

**Reconcile before resuming.** A crashed run may have left downloads the daemon went on to
finish, so we query `file_list` first and mark those `complete`; stale `running` rows then
reset to `pending`. Our database is always a lagging view of the daemon's truth, because
`get` returns before completion. Resume logic that trusts our own state without re-checking
the daemon will duplicate work or lose files.

### Concurrency and output

One `ThreadPoolExecutor` (default 8 workers) for enqueue calls, plus a single poll thread
updating progress from `files.query`. All DB writes go through the store behind one lock on a
single connection — SQLite serialises writes regardless, so the lock states that honestly.
WAL lets the poll loop read while the pool writes.

Progress is **emitted, never printed**: the archiver takes a callback and yields events; the
CLI renders them. `T20` enforces this mechanically, with `cli.py` the only module exempted.

Disk layout, controlled via `get`'s `download_directory` and `file_name` parameters
(`daemon.py:1114`):

```
<root>/pylbry.db
<root>/media/<channel_name>/<claim_id>__<name>.<ext>
```

The `claim_id` prefix guarantees uniqueness and lets a file be re-associated with its row if
the database is rebuilt.

## CLI

Thin argparse over the public API. The library is the product.

```
pylbry archive channel <url> [--root PATH] [--workers N] [--limit N]
pylbry archive resume [--root PATH]
pylbry status [--root PATH]
pylbry resolve <url>
```

## Standards and guardrails

These land in the first commit, before any library code. Configuring gates after writing
code means negotiating with existing violations, and "run linters before committing" is
unenforceable if the linter config arrives with the code it judges.

```toml
[project]
dependencies = ["httpx>=0.28.1,<0.29.0"]

[dependency-groups]
dev = [
  "ruff>=0.16.1,<0.17.0",
  "ty>=0.0.65,<0.1.0",
  "pytest>=9.1.1,<10.0.0",
  "pytest-cov>=7.1.0,<8.0.0",
  "pytest-xdist>=3.8.0,<4.0.0",
]

[tool.ty.environment]
python-version = "3.14"

[tool.ty.rules]
all = "error"

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
preview = true
select = ["E","W","F","I","N","D","UP","B","A","C4","SIM","RUF",
          "ANN","PYI","PTH","TID","ERA","PL","T20","DOC"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers --strict-config -n auto --dist loadgroup --cov --cov-report=term-missing"
markers = ["live: requires a running lbrynet daemon"]

[tool.coverage.run]
branch = true
source = ["src/pylbry"]

[tool.coverage.report]
exclude_also = ["if TYPE_CHECKING:", "@overload"]
```

Environment is `uv venv` plus `uv sync`; commands are `uv run pytest`, `uv run ruff check`,
`uv run ruff format`, `uv run ty check`.

Rationale for the less obvious selections:

- **`ANN` + `PYI`** — recommended by ty's own migration guide to approximate strict mode.
  Annotation enforcement is linting; type correctness is ty's job.
- **`ANN401`** bans bare `Any`. Load-bearing here: without it the easy path is returning
  `dict[str, Any]` from `call()`, which passes every other check while providing none of the
  intended safety. The recursive `JSONValue` alias makes the ban satisfiable honestly.
- **`T20`** bans `print`, mechanically enforcing the retrieval/presentation split.
- **`PTH`** forces `pathlib`, which matters for the archiver's file layout.
- **`DOC`** (pydoclint, preview) checks that documented `Args`/`Returns`/`Raises` match the
  signature, catching stale docstrings. Exact codes to be verified at configuration time
  rather than assumed.

All functions carry Google-style docstrings. **Known limitation:** ruff's `D` rules only
cover public objects — `D103` is "missing docstring in *public* function" — so private
helpers cannot be mechanically enforced. Public enforcement is automatic; private is
convention, with `DOC` catching drift in both.

If a specific ty rule fights the daemon's untyped JSON, we downgrade **that named rule**
with a justification comment. Never a blanket relaxation.

**Supply-chain note:** `ty` at 0.0.65 with `all = "error"` means a routine upgrade can add
rules and break a green build with no code change. The `<0.1.0` ceiling plus `uv.lock`
contains it, but upgrades are deliberate work, not routine bumps.

## Testing

Live daemon, no mocks, 100% branch coverage. `tests/` mirrors the package.

**Fixture discovery, not hard-coded URLs.** A session fixture finds currently-resolvable
content via `claim_search` (recent, `has_source=True`); tests assert on **shape, not
values**. A pinned claim ID can be supplied by environment variable to reproduce a specific
failure. Hard-coded URLs would give a suite that passes today and rots silently as content
goes unseeded. Shape-based assertion is what makes discovery safe, so it is a requirement,
not a habit.

**Error branches are provoked by misusing a real daemon** — not mocking:

| Branch | Provocation |
| --- | --- |
| `DaemonUnavailableError` | point the client at a closed port |
| `MethodNotFoundError` (`-32601`) | call a method name that does not exist |
| `InvalidParamsError` (`-32602`) | call `resolve` with malformed params |
| `OperationFailedError` (channel 3) | `get` a nonexistent or malformed URI |
| `ResolveFailure` (channel 4) | batch-resolve valid and junk URLs together |
| download timeout → `unavailable` | `get` with a 1-second timeout |

All deterministic against a real daemon, which is what makes `--cov-fail-under=100`
achievable without exclusions. Target is zero `# pragma: no cover`; any that prove necessary
carry a justification comment.

**Daemon-free is not mock-based.** `archive/store.py` tests use a real SQLite database in
`tmp_path`; CLI argument tests call `main(argv)` directly. Real code, real files, no fakes —
they simply have no network dependency. Daemon-dependent tests carry the `live` marker and
fail loudly with an actionable message when no daemon is reachable, rather than skipping.

**Affordability.** Archiver tests run against a real temp root with a small `--limit` and
select `stream_types=["image"]` or documents, so real downloads are kilobytes. We exercise
the state machine and resume logic, not throughput.

**xdist.** Downloads and `file_list` assertions carry
`@pytest.mark.xdist_group("daemon_state")`, pinning that group to one worker; read-only and
store tests fan out. A single stateful daemon shared by parallel workers otherwise flakes on
shared downloads and file state.

CI runs `ruff check`, `ruff format --check` and `ty check`, none of which need a daemon.
Functional tests run locally against a live daemon.

## Out of scope

- Publishing, channel management and wallet write operations. The `client.<namespace>`
  split and shared transport are the designed extension point.
- Daemon authentication.
- Any reimplementation of protocol internals — blobs, DHT and wallet stay the daemon's job.
- Backward-compatibility shims. There is no released version to be compatible with.

## Corrections from planning

Writing the implementation plan surfaced four errors in the original draft of this
spec. They are corrected above; recorded here so the reasoning is not lost.

1. **`files.list()` renamed to `files.query()`.** Inside a class body, a method named
   `list` shadows the builtin, so a `list[str]` return annotation on any method of that
   class resolves to the method. Verified: `ty` rejects it with
   `invalid-type-form: Invalid subscript of object of type 'def list(...)'`.
2. **`None` moved to the end of the `JSONValue` union, and the alias wrapped.** Ruff
   `RUF036` (`none-not-at-end-of-union`) rejects `None` mid-union, and the single-line
   form exceeds 88 characters.
3. **`--cov-fail-under=100` removed from `addopts`.** With it there, every single-test
   TDD run fails the threshold, making incremental development impossible. The gate
   moves to full-suite invocations: `uv run pytest --cov-fail-under=100`. The 100%
   requirement is unchanged — only where it is enforced.
4. **ABOUTME lines must be `#` comments above the module docstring**, not inside it.
   Inside the docstring they trip ruff `D205` (`missing-blank-line-after-summary`).

**One requirement is deferred rather than corrected.** The retry-with-backoff policy for
idempotent reads (see Retries and timeouts) has no task in the implementation plan.
Implementing it now would add a branch that cannot be provoked against a healthy local
daemon, conflicting with the 100% coverage rule. It should be added when a real failure
motivates it, at which point that failure becomes the test.
