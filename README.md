# tmux-session-picker

`tsesh` is a session picker for tmux and [Rex](https://www.superlogical.com/rex).
One fzf popup lists pinned sessions, live tmux and Rex sessions, zoxide
directories and a directory scan. Pick a row and tsesh switches to that
session, creating it in the directory first if needed. With
[murmur](https://github.com/mu-crew/murmur), the same popup also lists coding
agents and jumps to them.

What you get:

- one popup for pinned sessions, live sessions, zoxide and a scan under `$HOME`
- session reuse by directory (real path), with name collisions kept apart
- jump to the last session, or a session rooted at the current pane's directory
- kill a session from the picker
- with murmur: each session's agent state (`crashed`, `error`, `blocked`,
  `done`, `working`, `waiting`; `idle` is only counted), attention rows and an
  agents view
- with Rex: the same picker in a Rex pane, Rex sessions next to tmux ones,
  and Enter crossing between them (a tmux session opens in a Rex tab, a new
  project becomes a named Rex session)

What it is not:

- not a tmux session manager or restorer: it creates and switches sessions,
  and leaves saving and restoring them to your tmux setup
- not a replacement for murmur's state collection: it only reads what murmur
  publishes
- no agent control beyond jumping to an agent
- no runtime dependencies beyond tmux, fzf and Python; murmur and Rex are
  optional

On vtmux >= 3.8-rc3 (`set -s vtmux-program-status on`) the state column is
native, read from `#{session_program_state}`. On vanilla tmux 3.8, which drops
OSC 7501, the picker, zoxide, root-dir, kill and last-session all work; the
state column is blank and local agents do not appear in `prefix a`. murmur 3.0
sees no local panes there; murmur 2.x (branch `release/2.x`) is the clean out.

## Install

Needs tmux 3.2+, Python 3.11+ and [fzf](https://github.com/junegunn/fzf) 0.46+.
[zoxide](https://github.com/ajeetdsouza/zoxide), [fd](https://github.com/sharkdp/fd)
and [eza](https://github.com/eza-community/eza) are used when present.
With [TPM](https://github.com/tmux-plugins/tpm):

```tmux
set -g @plugin 'mu-crew/tmux-session-picker'
```

Without TPM, clone the repo and add
`run-shell ~/path/to/tmux-session-picker/tsesh.tmux` to `~/.tmux.conf`.
Releases are git tags; pin one with
`set -g @plugin 'mu-crew/tmux-session-picker#vX.Y.Z'`.

## Keys

| Key | Does |
| --- | --- |
| `prefix s` | Picker popup (`@tsesh_key_pick`) |
| `prefix a` | Picker popup, agents view (`@tsesh_key_agents`) |
| `prefix g` | Last session (`@tsesh_key_last`) |
| `prefix T` | Session rooted at the current pane's directory (`@tsesh_key_root`) |
| `ctrl-a` / `ctrl-s` / `ctrl-f` | All / sessions / find view |
| `ctrl-g` | Agents view; again: show or hide crew agents |
| `ctrl-x` | Kill the highlighted tmux or Rex session (not the tmux session you are in); on an agent, dismiss its crash |
| `ctrl-/` | Show or hide the preview |
| `tab` / `shift-tab` | Down / up |
| `enter` | Switch to the row (creating the session if needed) or jump to the agent |
| `esc` / `ctrl-c` | Abort |

Set an option to move a key, or to `""` to unbind it.

## Rex

Run `tsesh pick-and-connect` in a Rex pane, or bind it in a floating layer:
[mu-crew/dotfiles](https://github.com/mu-crew/dotfiles) does that with
`cmd+b s` (picker) and `cmd+b a` or `cmd+j` (agents), matching `prefix s` and
`prefix a`. Rex sessions are listed only when a Rex.app is connected to this
machine's Rex server, since nothing else can show one. Details are in
[docs/rex.md](docs/rex.md).

## More

- [docs/keys-and-views.md](docs/keys-and-views.md): keys, options, views, row
  markers and the command line
- [docs/agents.md](docs/agents.md): murmur integration, agent rows, the agents
  view, safety rules and `--client`
- [docs/config.md](docs/config.md): `config.toml`, environment variables,
  layout and columns, preview, theme
- [docs/sessions.md](docs/sessions.md): session rows, reuse by path, name
  collisions, kill, last, server lifetime
- [docs/rex.md](docs/rex.md): Rex session rows, what Enter does from tmux and
  from Rex, agents, opening tsesh in Rex
- [docs/development.md](docs/development.md): gates, uv pins, tests, releasing
- [CHANGELOG.md](CHANGELOG.md) and [RELEASING.md](RELEASING.md)

---

Part of [mu-crew](https://github.com/mu-crew). Written mostly by AI coding agents, with a human reviewing what ships, and built for running them.
