# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This repository is a fresh `uv init --lib` skeleton. Apart from a placeholder `hello()` in
`src/pylbry/__init__.py`, no library code, tests, or CI exist yet. There is no architecture to
describe — when you add the first real modules, replace this section with one that documents them.

The intent, from `pyproject.toml`: a modern Python library for interacting with the LBRY network.
Nothing in the repo yet commits to a transport, API surface, or dependency set, so treat those as
open design questions to settle with Ben rather than assumptions to infer.

## Layout and packaging

- `src/` layout with `uv_build` as the build backend. The package directory name (`src/pylbry/`)
  must keep matching the `project.name` in `pyproject.toml` — `uv_build` derives the module path
  from it, so renaming one without the other breaks the build.
- `py.typed` is present, so the package ships inline type information. Public functions need
  annotations for that marker to mean anything to consumers.
- `.python-version` pins 3.14; `requires-python = ">=3.14"` matches it.
- `lib/` is empty and unreferenced by the build. Delete it or explain it before it accumulates
  meaning by accident.

## Commands

Dependencies are empty and no dev tooling is declared yet, so the linter, type checker, and test
runner must be invoked through `uvx` (or added as a dev group first).

```bash
uv sync                       # create .venv and resolve dependencies
uv run python -c "import pylbry; print(pylbry.hello())"

uvx ruff check                # lint
uvx ruff format               # format
uvx ty check                  # static types
uvx --with pytest pytest -q   # tests (no tests/ directory exists yet)
uvx --with pytest pytest -q tests/test_module.py::test_name   # single test
```

Before the first real feature lands, add `pytest`, `ruff`, and `ty` to a `[dependency-groups] dev`
list in `pyproject.toml` so these become plain `uv run` commands and the versions get locked.
