# tmux-session-picker

`tsesh` is a tmux session picker. One fzf popup lists pinned sessions, live
sessions, zoxide directories and a directory scan. Pick a row and tsesh
switches to that session, creating it in the directory first if needed.

If [murmur](https://github.com/mu-crew/murmur) runs on the machine, each
session also shows its coding agents' state: crashed, blocked, done or
working. Without murmur that column is blank and everything else works.

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

| Key | View |
| --- | --- |
| `ctrl-a` | Everything (the default) |
| `ctrl-c` | Pinned sessions |
| `ctrl-t` | Live sessions |
| `ctrl-x` | zoxide directories |
| `ctrl-f` | Directory scan under `$HOME` |

## Config

Optional. Without a config file tsesh lists live sessions, zoxide and the scan
with sensible filters. Copy [examples/config.toml](examples/config.toml) to
`~/.config/tsesh/config.toml` to pin sessions or change the filters.

## Agent state

tsesh reads one tmux option per session, `@murmur_session_state`, in a single
`list-sessions` call. murmur keeps it at the strongest state among the
session's agents. Any tool can set it; the values are `crashed`, `blocked`,
`done` and `working`.

## Theme

Catppuccin Mocha, hardcoded in `bin/tsesh` between `THEME BEGIN` / `THEME END`
markers so a local theme generator can rewrite them.

## Development

```sh
python3 -m unittest discover -s tests
ruff check . && ruff format --check .
```

tsesh started as `tms` in a personal dotfiles repo. It was renamed because
[tmux-sessionizer](https://github.com/jrmoulton/tmux-sessionizer) already
installs a `tms` binary.

---

Part of [mu-crew](https://github.com/mu-crew). Written mostly by AI coding agents, with a human reviewing what ships, and built for running them.
