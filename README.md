# pyLBRY

A Python library for reading from and archiving the LBRY network.

Requires a running `lbrynet` daemon. See
`docs/superpowers/specs/2026-08-02-pylbry-design.md` for the design.

## Usage

```python
from pathlib import Path

from pylbry import Archiver, Client

with Client() as client:
    channel = client.claims.resolve("lbry://@example")
    with Archiver(client, Path("archive")) as archiver:
        archiver.index_channel(channel.claim_id)
        archiver.fetch_pending(limit=10)
```

Or from the command line:

    pylbry resolve lbry://@example
    pylbry --root archive archive channel lbry://@example --limit 10
    pylbry --root archive archive resume --limit 10
    pylbry --root archive status

Archiving happens in two phases. Indexing records every claim in the channel
into a SQLite database without downloading media, so the metadata survives even
if the media never does. Fetching then downloads the queued claims.

**Media downloads are large.** Without `--limit`, `archive channel` fetches the
entire channel, which is routinely tens of gigabytes.

## Daemon setup

The default `lbryum_servers` list is mostly dead: LBRY Inc's `spv*.lbry.com`
hosts refuse connections. If the daemon reports `available_servers: 0` and its
wallet never starts, pin it to a server that still runs, in
`~/.local/share/lbry/lbrynet/daemon_settings.yml`:

```yaml
lbryum_servers:
  - hub.lbry.grin.io:50001
```

Entries must be `host:port` strings. The nested-list form that `settings_get`
returns is silently discarded on load, yielding no servers at all.

## Development

    uv venv && uv sync
    uv run pytest --cov-fail-under=100
    uv run ruff check && uv run ty check

The suite has no mocks: every network path runs against a real daemon with its
wallet started. Set `PYLBRY_TEST_DAEMON` if the daemon is not at
`http://localhost:5279`, and `PYLBRY_TEST_CHANNEL` to draw test content from a
channel other than the default. Tests reuse media the daemon already holds
before starting any new download.
