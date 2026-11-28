# Config

Optional. Without a config file tsesh lists live sessions, zoxide and the scan
with sensible filters. Copy [examples/config.toml](../examples/config.toml) to
`~/.config/tsesh/config.toml` (`$XDG_CONFIG_HOME/tsesh/config.toml`, or the
file `$TSESH_CONFIG` names) to pin sessions or change the filters.

## Environment variables

`TSESH_MURMUR` names the murmur to run (default `murmur` on `PATH`) and
`TSESH_MURMUR_TIMEOUT` its time limit in seconds (default 1).
`TSESH_REX` names the `rex` to run (default `rex` on `PATH`; empty turns Rex
support off, see [rex.md](rex.md)).
`TSESH_TMUX_SOCKET_PATH` / `TSESH_TMUX_SOCKET_NAME` point tsesh at another
tmux server, and `TSESH_FAST=1` selects the fast test gate; both exist for the
tests.

## Layout and columns

The picker fits its columns to the popup. The preview sits right of the list
from 120 columns, below it from 80, and starts hidden under 80 (`ctrl-/` shows
it). The name column grows from 16 to 40 cells with the list; a long name keeps
its last part whole and shortens the start (`projects/te…/demo`), and a long
path keeps its end (`…ects/team/demo`).
On a narrow list the window counts go first, then the path. Widths are counted
in terminal cells, so wide (CJK) names keep the columns aligned. Resizing the
popup lays the list out again.

## Preview

The preview of a live session lists every window (active marker, index, agent
state, name, pane count, directory) above the active pane's contents.

## Theme

Catppuccin Mocha, hardcoded in `bin/tsesh` between `THEME BEGIN` / `THEME END`
markers so a local theme generator can rewrite them.
