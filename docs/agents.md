# Agents (murmur integration)

If [murmur](https://github.com/mu-crew/murmur) runs on the machine, each
session also shows its coding agents' state: crashed, error, blocked, done,
working or waiting. Without murmur that column is blank and everything else works.

## Agent state

tsesh reads one tmux option per session, `@murmur_session_state`, in a single
`list-sessions` call. murmur keeps it at the strongest state among the
session's agents. Any tool can set it; the values are `crashed`, `error`,
`blocked`, `done`, `working` and `waiting`. murmur also reports `idle` (a
stopped agent with nothing pending); tsesh only counts those in the breakdown
of a session row, and an idle session shows no state.

## Richer view with a current murmur

When the installed murmur supports it, tsesh also reads `murmur status --json
--cached` once per open (cache-only, one second timeout; a detached
`murmur collect --quiet --floored` warms the cache for the next open). Then:

- a session row shows how many agents are in each state (`2 working, 1 done`
  as glyph and count) instead of only the strongest state;
- agents that need attention (crashed, error, blocked, done) get their own rows
  at the top of the all view, in murmur's order. Enter on one selects its pane
  and switches to it when the picker runs inside that agent's tmux server;
  any other agent (another host or server, or a picker outside tmux) goes
  through `murmur jump`.

Agent rows need murmur's `jump` command too. A remote agent counts under the
local session that holds its ssh attachment.

### Safety rules

tsesh acts on a pane itself only when it has proven the agent's tmux server is
the one it talks to (the `TSESH_TMUX_SOCKET_*` variables, else the socket in
`$TMUX`, else the default, resolved once when tsesh starts); everything else
goes through `murmur jump`. A failed jump stays on screen for a moment and
shows as a tmux message.

tsesh probes for this (`status --json --cached` succeeds with well-formed
panes, and `jump --help` exits 0); it never compares versions. A malformed
snapshot is ignored as a whole. With no murmur, or an older one,
everything works from `@murmur_session_state` as before.

## Agents view

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

### Markers

In the agents view the first column's `◆` also marks the agent pane of the
client that opened the picker (see [keys-and-views.md](keys-and-views.md)).

### `--client`

Open it through the `prefix a` binding (it passes `--client`), or pass
`--client` yourself; otherwise errors may show on another client.

## Environment

`TSESH_MURMUR` names the murmur to run (default `murmur` on `PATH`) and
`TSESH_MURMUR_TIMEOUT` its time limit in seconds (default 1).
