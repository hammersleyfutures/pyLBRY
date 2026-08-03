# pyLBRY

A Python library for reading from and archiving the LBRY network.

Requires a running `lbrynet` daemon. See
`docs/superpowers/specs/2026-08-02-pylbry-design.md` for the design.

## Development

    uv venv && uv sync
    uv run pytest --cov-fail-under=100
    uv run ruff check && uv run ty check

The test suite requires a reachable `lbrynet` daemon with its wallet component
started. Set `PYLBRY_TEST_DAEMON` if it is not at `http://localhost:5279`.
