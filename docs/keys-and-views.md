# Keys and views

## tmux keys

| Prefix + | Does | Option |
| --- | --- | --- |
| `s` | Picker popup | `@tsesh_key_pick` |
| `a` | Picker popup, agents view | `@tsesh_key_agents` |
| `g` | Last session | `@tsesh_key_last` |
| `T` | Session rooted at the current pane's directory | `@tsesh_key_root` |

Set an option before TPM runs to move a key, or to `""` to leave it unbound.
Sourcing `tsesh.tmux` again after a change releases the key it bound before
(unless you have rebound that key yourself).
[mu-crew/dotfiles](https://github.com/mu-crew/dotfiles) sets these for you from
its own `@mu_crew_key_session_*` options, so configure them there if you use it.

```tmux
set -g @tsesh_key_pick 'f'
set -g @tsesh_key_last ''
```

## Inside the picker

| Key | Does |
| --- | --- |
| `ctrl-a` | All view: pinned, live, agents needing attention, zoxide (the default) |
| `ctrl-s` | Sessions view: pinned and live sessions |
| `ctrl-g` | Agents view; again in the agents view: show or hide crew agents |
| `ctrl-f` | Find view: directory scan under `$HOME` |
| `ctrl-x` | Kill the highlighted session (session rows only; refuses the session you are in) |
| `ctrl-/` | Show or hide the preview |
| `tab` / `shift-tab` | Down / up |
| `enter` | Switch to the row, creating the session first if needed, or jump to the agent |
| `esc` / `ctrl-c` | Abort |

The first column marks where you are: `◆` is the session (and, in the agents
view, the agent pane) of the client that opened the picker, and `◇` is a
session another client has attached.

## Command line

`bin/tsesh` also works on its own, outside a popup: `tsesh pick-and-connect`.

`tsesh list|picker|pick-and-connect --mode` takes `all`, `sessions`, `find` or
`agents`; `tsesh list --mode agents --crew` includes crew agents. `tsesh last`
says "tsesh: no previous session" in tmux when there is none, and
`tsesh kill --kind=tmux --session-id='$N'` is `ctrl-x` from a shell.
`tsesh --help` lists the commands. `tsesh --version` prints the version.

See [sessions.md](sessions.md) for what each session row shows and how
picking a directory finds its session, and [agents.md](agents.md) for the
agents view.
