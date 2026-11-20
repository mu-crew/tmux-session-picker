# Sessions

## Rows

Live sessions are listed most recently active first, after the pinned ones
(which keep their config order). A live session's row counts its windows and
panes (`3w 5p`) and shows its active pane's directory, with a dim `+N` when its
windows sit in N other directories. A zoxide or scan directory that a live
session is rooted at, or has a window in, is not listed again: that session's
row stands for it. The preview of a live session lists every window (active
marker, index, agent state, name, pane count, directory) above the active
pane's contents.

## Session reuse by path and name collisions

Picking a directory reuses the live session rooted at that directory, matched
by its real path (tsesh starts sessions with `new-session -c <realpath>`) or by
the path as given, which covers sessions an older tsesh started through a
symlink. Two directories whose names sanitize alike (`a.b`, `a_b`) get
separate sessions, the second suffixed `-2`. One limitation: if a symlink was
retargeted after its session was created, connecting through that same symlink
string reuses the old session. Connecting through the real path is exact.
Directories with a newline or carriage return in the name are not offered in
the scan, but `tsesh connect` handles them.

## Kill and last

`ctrl-x` in the picker kills the highlighted session (session rows only; it
refuses the session you are in); `tsesh kill --kind=tmux --session-id='$N'`
does the same from a shell. `prefix g` (`tsesh last`) switches to the last
session, and says "tsesh: no previous session" in tmux when there is none.

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
and `split`: those run only when tsesh creates the session. Plain tmux has no
snapshot: `start-server` exits at once and nothing changes.
