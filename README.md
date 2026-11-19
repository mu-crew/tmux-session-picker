# tmux-session-picker

`tsesh` is a tmux session picker. One fzf popup lists pinned sessions, live
sessions, zoxide directories and a directory scan. Pick a row and tsesh
switches to that session, creating it in the directory first if needed.

If [murmur](https://github.com/mu-crew/murmur) runs on the machine, each
session also shows its coding agents' state: crashed, error, blocked, done,
working or waiting. Without murmur that column is blank and everything else works.

## Install

Needs tmux 3.2+, Python 3.11+ and [fzf](https://github.com/junegunn/fzf).
[zoxide](https://github.com/ajeetdsouza/zoxide), [fd](https://github.com/sharkdp/fd)
and [eza](https://github.com/eza-community/eza) are used when present.

With [TPM](https://github.com/tmux-plugins/tpm):

```tmux
set -g @plugin 'mu-crew/tmux-session-picker'
```

Without TPM, clone the repo and add to `~/.tmux.conf`:

```tmux
run-shell ~/path/to/tmux-session-picker/tsesh.tmux
```

`bin/tsesh` also works on its own, outside a popup: `tsesh pick-and-connect`.

## Keys

| Prefix + | Does | Option |
| --- | --- | --- |
| `s` | Picker popup | `@tsesh_key_pick` |
| `g` | Last session | `@tsesh_key_last` |
| `T` | Session rooted at the current pane's directory | `@tsesh_key_root` |

Set an option before TPM runs to move a key, or to `""` to leave it unbound.
[mu-crew/dotfiles](https://github.com/mu-crew/dotfiles) sets these for you from
its own `@mu_crew_key_session_*` options, so configure them there if you use it.

```tmux
set -g @tsesh_key_pick 'f'
set -g @tsesh_key_last ''
```

Inside the picker:

| Key | Does |
| --- | --- |
| `ctrl-a` | All view: pinned, live, zoxide (the default) |
| `ctrl-s` | Sessions view: pinned and live sessions |
| `ctrl-f` | Find view: directory scan under `$HOME` |
| `tab` / `shift-tab` | Down / up |
| `enter` | Switch to the row, creating the session first if needed |
| `esc` / `ctrl-c` | Abort |

`tsesh list|picker|pick-and-connect --mode` takes `all`, `sessions` or `find`.

## Versions

`tsesh --version` prints the version. Releases are git tags; pin one with
`set -g @plugin 'mu-crew/tmux-session-picker#vX.Y.Z'`. See
[CHANGELOG.md](CHANGELOG.md) and [RELEASING.md](RELEASING.md).

## Config

Optional. Without a config file tsesh lists live sessions, zoxide and the scan
with sensible filters. Copy [examples/config.toml](examples/config.toml) to
`~/.config/tsesh/config.toml` to pin sessions or change the filters.

## Agent state

tsesh reads one tmux option per session, `@murmur_session_state`, in a single
`list-sessions` call. murmur keeps it at the strongest state among the
session's agents. Any tool can set it; the values are `crashed`, `error`,
`blocked`, `done`, `working` and `waiting`.

### Richer view with a current murmur

When the installed murmur supports it, tsesh also reads `murmur status --json
--cached` once per open (cache-only, one second timeout; a detached
`murmur collect --quiet --floored` warms the cache for the next open). Then:

- a session row shows how many agents are in each state (`2 working, 1 done`
  as glyph and count) instead of only the strongest state;
- agents that need attention (crashed, error, blocked, done) get their own rows
  at the top of the all view, in murmur's order. Enter on one selects its pane
  and switches to it; agents on another host or tmux server go through
  `murmur jump`.

tsesh probes for this (the call succeeds and panes carry `render_state` and
`jump_target`); it never compares versions. With no murmur, or an older one,
everything works from `@murmur_session_state` as before.

## Server lifetime

When tsesh starts the tmux server from inside a unit of the systemd user
manager, it runs the server under `systemd-run --user --scope`. A shell in a
`foot --server` window is the usual case. The server would otherwise stay in
that unit's cgroup, and a stop or restart of the unit would kill every session.
A login shell (ssh, a tty) sits in logind's own session scope, which tmux
already outlives at logout, so tsesh starts plain `tmux` there. Moving that
server under `user@.service` would end it about 10 s after the last logout
unless lingering is on. macOS, containers and hosts without `systemd-run` also
get plain `tmux`.

With no server running, the picker starts one the same way (`start-server`)
before it lists live sessions, so a tmux that restores saved sessions at server
start shows them. When creating a session, tsesh checks again after starting
the server and switches to the session if it came back, instead of running
`new-session`. A restored session therefore skips its configured `startup`
and `split`: those run only when tsesh creates the session. Plain tmux has no snapshot: `start-server` exits at once and
nothing changes.

## Session names and directories

Picking a directory reuses the live session rooted at that directory, matched
by its real path (tsesh starts sessions with `new-session -c <realpath>`) or by
the path as given, which covers sessions an older tsesh started through a
symlink. Two directories whose names sanitize alike (`a.b`, `a_b`) get
separate sessions, the second suffixed `-2`. One limitation: if a symlink was
retargeted after its session was created, connecting through that same symlink
string reuses the old session. Connecting through the real path is exact.
Directories with a newline or carriage return in the name are not offered in
the scan, but `tsesh connect` handles them.

## Theme

Catppuccin Mocha, hardcoded in `bin/tsesh` between `THEME BEGIN` / `THEME END`
markers so a local theme generator can rewrite them.

## Development

```sh
python3 -m unittest discover -s tests
ruff check . && ruff format --check .
```

---

Part of [mu-crew](https://github.com/mu-crew). Written mostly by AI coding agents, with a human reviewing what ships, and built for running them.
