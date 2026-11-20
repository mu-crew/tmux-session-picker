# Development

ruff and ty are pinned in `pyproject.toml` and `uv.lock` (needs
[uv](https://docs.astral.sh/uv/)). The tests run on uv's Python here; plain
`python3 -m unittest discover -s tests` works too. tsesh itself needs none of
this: `bin/tsesh` is a plain script with no dependencies.

## Gates

Fast, while working and before every commit (a few seconds; skips the tests
that start a real tmux server or client, or fzf):

```sh
uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen ty check && TSESH_FAST=1 uv run --frozen python -m unittest discover -s tests
```

Slow, the full suite with the live tmux and fzf tests, before a merge or a
release. Run it through `muzzle run --` where muzzle is installed, so it waits
its turn on a busy machine:

```sh
muzzle run -- uv run --frozen python -m unittest discover -s tests
```

Targeted, the live tests for one area (`-k` matches class or test names):

```sh
muzzle run -- uv run --frozen python -m unittest discover -s tests -k LiveTmux -k RealFzf
```

Every test that starts tmux kills the server and its panes' processes in
cleanup, and a run that ends early (a timeout, ctrl-c) kills the rest; a run
leaves no test servers or shells behind. Waits poll for the state they need,
for up to a minute, instead of sleeping a fixed time.

## Releasing

Releases are git tags; see [RELEASING.md](../RELEASING.md) and
[CHANGELOG.md](../CHANGELOG.md).
