# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Changed (breaking)

- Picker keymap reworked. Views are now `all` (`ctrl-a`), `sessions`
  (`ctrl-s`, pinned plus live) and `find` (`ctrl-f`). The pinned-only (`ctrl-c`),
  live-only (`ctrl-t`) and zoxide-only (`ctrl-x`) views are gone, so `ctrl-c`
  aborts again. `--mode` takes `all`, `sessions` or `find`; the old values
  `default`, `tmux` and `zoxide` are rejected.
- The picker header now lists `tab`/`shift-tab` and `enter` too.

### Added

- `tsesh --version`.
- murmur's `error` and `waiting` agent states, with murmur's glyphs. `error`
  counts as needing attention.

### Fixed

- A new session for a directory no longer lands in another directory's session
  when their names sanitize alike (`a.b` and `a_b`); the second is suffixed
  `-2`. A directory reuses the live session rooted at it, found by real path or
  by the path as given, including paths with spaces, `#`, `,`, `}`, newlines
  and other odd bytes.
- Startup keys and splits no longer fail on tmux's default `base-index 0`.
- tmux failures print a message instead of a Python traceback.
- Attaching outside tmux honors the isolated socket variables.
- A pathless row no longer runs the preview command in the picker's cwd.
- `~` abbreviates only the real home prefix (`/home/me2/x` stays as is).
- Errors in a `[[sessions]]` entry name `config.toml`, not the session's path.
- The picker lists sessions once when the server is up; the `find` fallback
  prunes blacklisted directories and treats blacklist entries literally.
- `ruff check .` and `ruff format --check .` now cover `bin/tsesh`.

### Documented

- A session restored by tmux at server start skips its configured `startup`
  and `split`.
- A symlink retargeted after its session was created still reaches that
  session when connected through the same symlink string.
