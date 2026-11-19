# tmux-session-picker

`tsesh` is a tmux session picker. One fzf popup lists pinned sessions, live
sessions, zoxide directories and a directory scan. Pick a row and tsesh
switches to that session, creating it in the directory first if needed. With
murmur, the same popup also lists coding agents and jumps to them.

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
| `a` | Picker popup, agents view | `@tsesh_key_agents` |
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
| `ctrl-a` | All view: pinned, live, agents needing attention, zoxide (the default) |
| `ctrl-s` | Sessions view: pinned and live sessions |
| `ctrl-g` | Agents view; again in the agents view: show or hide crew agents |
| `ctrl-f` | Find view: directory scan under `$HOME` |
| `ctrl-x` | Kill the highlighted session (session rows only; refuses the session you are in) |
| `tab` / `shift-tab` | Down / up |
| `enter` | Switch to the row, creating the session first if needed, or jump to the agent |
| `esc` / `ctrl-c` | Abort |

`tsesh list|picker|pick-and-connect --mode` takes `all`, `sessions`, `find` or
`agents`; `tsesh list --mode agents --crew` includes crew agents.

The first column marks where you are: `◆` is the session (and, in the agents
view, the agent pane) of the client that opened the picker, and `◇` is a
session another client has attached.

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
`blocked`, `done`, `working` and `waiting`. murmur also reports `idle` (a
stopped agent with nothing pending); tsesh only counts those in the breakdown
of a session row, and an idle session shows no state.

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

Agent rows need murmur's `jump` command too. A remote agent counts under the
local session that holds its ssh attachment. tsesh acts on a pane itself only
when it has proven the agent's tmux server is the one it talks to (the
`TSESH_TMUX_SOCKET_*` variables, else the socket in `$TMUX`, else the default);
everything else goes through `murmur jump`. A failed jump stays on screen for a
moment and shows as a tmux message.

tsesh probes for this (`status --json --cached` succeeds with well-formed
panes, and `jump --help` exits 0); it never compares versions. A malformed
snapshot is ignored as a whole. With no murmur, or an older one,
everything works from `@murmur_session_state` as before.

### Agents view

`prefix a`, `ctrl-g` in the picker, or `tsesh pick-and-connect --mode agents`
lists every agent murmur shows by default (human agents, plus crew agents that
need a human), in murmur's order. `ctrl-g` again shows or hides the other crew
(orchestrated) agents; the prompt starts with `crew` while they are shown, and
the setting holds when you switch views and come back (in the all view it
adds crew agents to the attention rows). Each row has the state,
the agent's name, its workstream (or tmux session) when that differs from the
name, a host column (`here` or `→ host`) when any agent is remote, and the age
of its last update. The prompt counts the shown agents per state.

When a peer needs a new ssh session, murmur's notice is the first header line,
with the `ssh` command that lets murmur reach it again.
An empty view says so ("No agents", or how many crew agents are hidden) and
stays open until `esc`. Without murmur, or with one too old for the view, the
header says that instead.

The agents view starts no tmux server and works outside tmux. Enter moves the
client itself only when the picker runs inside the agent's tmux server;
otherwise it runs `murmur jump`, which handles other hosts and servers and
any confirmation it needs on the terminal.

Open it through the `prefix a` binding (it passes `--client`), or pass
`--client` yourself; otherwise errors may show on another client.

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

A live session's row counts its windows and panes (`3w 5p`) and shows its
active pane's directory, with a dim `+N` when its windows sit in N other
directories. A zoxide or scan directory that a live
session is rooted at, or has a window in, is not listed again: that session's
row stands for it. The preview of a live session lists every window (active
marker, index, agent state, name, pane count, directory) above the active
pane's contents.

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

---

Part of [mu-crew](https://github.com/mu-crew). Written mostly by AI coding agents, with a human reviewing what ships, and built for running them.
