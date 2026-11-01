# Development

Run development commands in the locked Nix shell. Prefix each command with
`nix develop -c`, or enter `nix develop` for an interactive session.

- Install dependencies: `nix develop -c uv sync --locked --extra test --extra dev`
- Run tests: `nix develop -c uv run --locked pytest tests/`
- Lint: `nix develop -c uv run --locked ruff check .`
- Check formatting: `nix develop -c uv run --locked ruff format --check .`

Work on a feature or fix branch. Keep Python dependencies in `pyproject.toml`
and `uv.lock`, and development tools in `flake.nix`.
