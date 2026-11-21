# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.3] - 2026-11-21

### Fixed

- Enter on a row reached through a view key failed with "gone since the
  picker opened". This hit crew agents (mu delegates) after `ctrl-g`, and rows
  of another view after `ctrl-s` or `ctrl-f`. 1.0.2 checked every choice
  against the opening view, which lacks those rows. Only a choice from the
  cached rows is checked now. Rows from a reload are fresh already.

## [1.0.2] - 2026-11-20

### Changed

- The popup opens on the rows that the last open of the same view left
  behind, then swaps in a fresh list. The wait for murmur and tmux no longer
  delays the first paint. If you press Enter before the fresh list arrives,
  the popup closes and tsesh looks the row up again in a fresh list, so it
  never acts on stale rows. The cache is kept per view, tmux server, popup
  width and tsesh version, in `$XDG_STATE_HOME/tsesh/views/`.
- On a cached open, the picker builds the fresh list itself while fzf shows
  the cache, and hands it over through fzf's `--listen` socket (a unix socket
  in the picker's private temporary directory). The tmux call that finds the
  invoking pane now runs after fzf starts. A view key or `ctrl-x` pressed
  before the handover keeps its own list.

## [1.0.1] - 2026-11-20

### Changed

- The picker opens faster: it starts fewer processes, and murmur's snapshot
  read now overlaps the tmux calls.
  - Sessions and windows come from one tmux call instead of two.
  - The agents view no longer runs `murmur jump --help` on every open. A
    snapshot with `jump_target` already shows that `murmur jump` exists (both
    came in murmur 2.3.0).
  - The background `murmur collect` runs at a lower priority, and only when
    some peer was last fetched over 20 seconds ago or is stale.

## [1.0.0] - 2026-11-19

### Changed (breaking)

- Picker keymap reworked. Views are now `all` (`ctrl-a`), `sessions`
  (`ctrl-s`, pinned plus live) and `find` (`ctrl-f`). The pinned-only (`ctrl-c`),
  live-only (`ctrl-t`) and zoxide-only (`ctrl-x`) views are gone, so `ctrl-c`
  aborts again (`ctrl-x` now kills a session, see Added). `--mode` takes
  `all`, `sessions`, `find` or `agents`; the old values `default`, `tmux` and
  `zoxide` are rejected.
- The picker header now lists `tab`/`shift-tab` and `enter` too.

### Changed

- The preview is faster: a live session's preview takes one tmux call instead
  of five, and the built-in directory listing runs without a login shell. A
  `preview_command` set in the config still runs in `sh -l`.

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

- Live sessions sort by last activity, newest first; pinned sessions keep
  their config order.

- `tsesh --help` describes each command.

### Fixed

- A live session's preview names the session and its attached clients again
  on its first line; on recent tmux that line was blank.
- Sourcing `tsesh.tmux` again releases a key it bound before when its option
  changed or became `""`; keys the user rebound are left alone. The bindings
  work from a plugin directory with spaces, quotes, `#` or `$` in its path.

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

### Development

- ruff and ty are pinned in `pyproject.toml` and `uv.lock`; the gate runs
  `uv run --frozen` ruff, ty and the tests. `TSESH_FAST=1` skips the live tmux
  and fzf tests for a fast gate, and test runs leave no tmux servers behind.

### Documented

- A session restored by tmux at server start skips its configured `startup`
  and `split`.
- A symlink retargeted after its session was created still reaches that
  session when connected through the same symlink string.

