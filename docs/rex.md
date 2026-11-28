# Rex

tsesh works the same from a tmux client and from a [Rex](https://www.superlogical.com/rex)
pane: one picker lists tmux sessions, Rex sessions, directories and agents,
and Enter takes you to the row in whichever multiplexer holds it.

## When tsesh is in Rex

tsesh counts as running in Rex when `TERM_PROGRAM=rex` and Rex has set
`$REX_BLOCK` (older Rex builds set `$REX_SESSION` instead), and `$TMUX` is
unset. A tmux client running in a Rex tab counts as tmux, because that is
where its keys go.

## Rex session rows

Live Rex sessions on this machine are listed in the all and sessions views,
after the tmux sessions, with a `■` icon and `rex` where a tmux row shows its
window and pane counts.

They are listed only when this machine's Rex server has a Rex.app connected
(`rex client ls`; with `$REX_CLIENT` set, that client). Rex has no terminal
attach, so on a machine with no Rex.app, such as a Linux box running a
headless Rex server, nothing could show a Rex session and none are listed.

With murmur, a Rex row takes the strongest non-idle state of the agents in its
panes, as a tmux row does. The preview lists the session's windows (`*` marks
the active one) above the contents of the active window's focused pane.
`ctrl-x` on a Rex row runs `rex kill` on that session.

## Enter

| Row | From tmux | From Rex |
| --- | --- | --- |
| Rex session | Shows it in Rex.app and, on macOS, brings Rex.app to the front | Shows it |
| Live tmux session | Switches the client | Opens it in a new Rex tab (`tmux attach-session`) and shows that tab |
| Pinned, zoxide or find row | Switches to its tmux session, creating it first if needed | Shows the live Rex or tmux session of that name (tmux in a new tab); otherwise creates a Rex session |
| Agent | See [agents.md](agents.md) | `murmur jump`; a tmux agent opens in a new Rex tab, which tsesh shows |

A Rex session created from a directory row gets the row's name and starts in
its directory, so it never carries one of Rex's generated names. A pinned
session's `startup` is typed into the new session's shell, as tmux's
`send-keys` would, so quitting the program leaves the shell. Its `split`
becomes a Rex split of that first pane: `vertical` to the right, `horizontal`
below.

## Agents

The agents view has a `mux` column (`tmux` or `rex`), and the all view's
attention rows name the multiplexer too. A Rex agent is reached through
`murmur jump`, which needs a Rex.app on this machine; without one, murmur
releases after 3.1.2 say so instead of jumping.

murmur 3.1.1 and older do not handle a jump from a Rex pane completely: 3.1.0
misses current Rex panes, and neither shows the tab it opens. tsesh covers both,
passing `$REX_BLOCK` as `$REX_SESSION` to `murmur jump` and showing the new tab
afterwards. With murmur 3.1.2 or later both steps are redundant and harmless.

## Opening tsesh in Rex

Run `tsesh pick-and-connect` in any Rex pane, or `tsesh pick-and-connect
--mode agents` for the agents view. [mu-crew/dotfiles](https://github.com/mu-crew/dotfiles)
binds both in a floating Rex layer, the way `prefix s` and `prefix a` open a
tmux popup: `cmd+b s` for the picker, and `cmd+b a` or `cmd+j` for the agents
view (see its `docs/rex.md`).

## Environment

| Variable | Effect |
| --- | --- |
| `TSESH_REX` | The `rex` to run (default `rex` on `PATH`). Set it empty to turn Rex support off. |
| `REX_CLIENT` | The Rex.app client to show sessions in, by label or ID. Rex rows are listed only when it is connected. |
| `REX_SERVER` | Ignored: tsesh always talks to this machine's Rex server. |
