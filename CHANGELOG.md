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

- `tsesh last` shows "tsesh: no previous session" in tmux when there is none.

- `ctrl-x` in the picker kills the highlighted session and redraws the view.
  It ignores agent, zoxide, find and not-running pinned rows and refuses the
  session the client is in, with a tmux message. It targets the session by its
  tmux id, so names like `$0`, `-x`, `a.b` or ones with outer spaces kill that
  session and no other. Also available as
  `tsesh kill --kind=tmux --session-id='$N'`.
- `tsesh --version`.
- murmur's `error` and `waiting` agent states, with murmur's glyphs. `error`
  counts as needing attention.

- With a current murmur: per-state agent counts on session rows, and attention
  agents as rows at the top of the all view. Enter selects the agent's pane or
  hands off to `murmur jump`. Probed by feature, falls back to
  `@murmur_session_state` without murmur. The picker row gained `host`,
  `pane`, `jump_target` and `here` fields, and the state column is wider.

- The picker key now runs through `run-shell` and passes `--client`, so a
  failure is shown on the client that opened the picker.

- Agents view: `prefix a` (`@tsesh_key_agents`), `ctrl-g` in the picker or
  `--mode agents` lists murmur's agents with state, name, workstream, host and
  age, per-state counts in the prompt, and murmur's session notice in the
  header. `ctrl-g` again toggles crew agents; the toggle survives view
  switches. Works outside tmux; Enter jumps through `murmur jump` unless the
  picker runs inside the agent's tmux server. An empty view, a missing murmur
  and a too-old murmur are said in the header.
- `◆` marks the invoking client's session and agent pane, `◇` sessions
  attached by another client. The legend lists `^g`.
- The view keys are fzf `transform` bindings (`tsesh fzf-action`); each view
  sets its own header and prompt.

- Live session rows count windows and panes (`3w 5p`, blank for a pinned
  session that is not running).
- Live session rows show the active pane's directory, with a dim `+N` for
  windows in other directories; zoxide and scan rows for a directory a live
  session already covers are dropped; the session preview lists every window.

- The picker fits its columns to the popup width: preview right, below or
  hidden (`ctrl-/` toggles it), a name column of 16 to 40 cells, paths cut at
  the start, counts and then paths dropped on narrow lists, a key legend that
  wraps, and a new layout on resize. Widths count terminal cells (CJK names
  stay aligned). Needs fzf 0.46+.

### Fixed

- Picker rows escape backslashes, tabs and line breaks in every field, so a
  pinned path or startup command holding a tab no longer shifts the fields
  after it.
- Switching sessions from the popup moves the client that opened it.
- Closing the picker with `esc` (or Enter on no match) exits 0, so tmux no
  longer prints "returned 130" over the pane.

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
