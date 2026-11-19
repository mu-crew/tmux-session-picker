# Releasing

tsesh has no package registry. TPM installs from git, so a release is a tag.

1. Make sure `main` has everything and is clean.
2. Bump `VERSION` in `bin/tsesh` (SemVer).
3. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and
   add a fresh empty `## [Unreleased]` above it.
4. Run the gate:

   ```sh
   uv run --frozen python -m unittest discover -s tests && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen ty check
   ```

5. Commit: `tsesh: release X.Y.Z`.
6. Tag it, annotated: `git tag -a vX.Y.Z -m "tsesh X.Y.Z"`.
7. Push the commit and the tag: `git push && git push origin vX.Y.Z`.

Users pin a release with TPM:

```tmux
set -g @plugin 'mu-crew/tmux-session-picker#vX.Y.Z'
```

## Compatibility with murmur

tsesh detects murmur's abilities by probing them (a command that succeeds, a
field that is present), never by comparing version numbers. A release note only
needs to say which murmur features it can use.
