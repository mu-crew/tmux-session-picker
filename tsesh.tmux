#!/usr/bin/env bash
# TPM entry point. Binds under the prefix; override a key before TPM runs:
#   set -g @tsesh_key_pick s     # picker popup
#   set -g @tsesh_key_agents a   # picker popup, agents view
#   set -g @tsesh_key_last g     # last session
#   set -g @tsesh_key_root T     # session rooted at the pane's cwd
# Set a key to "" to leave it unbound.
set -euo pipefail

dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tsesh="$dir/bin/tsesh"

opt() {
	local value
	value=$(tmux show-option -gqv "$1")
	# Unset means the default; an explicit empty string means "do not bind".
	if tmux show-options -g | grep -q "^$1 "; then
		printf '%s' "$value"
	else
		printf '%s' "$2"
	fi
}

# tsesh_bind NAME KEY NOTE COMMAND...: bind KEY, or with KEY "" bind nothing.
# Either way a key this script bound for NAME on an earlier source is released
# first, so re-sourcing after changing an option takes effect. The key is
# recorded in @tsesh_bound_NAME; it is unbound only while it still carries our
# note, so a key the user rebound since is left alone.
tsesh_bind() {
	local name=$1 key=$2 note=$3 prev
	shift 3
	prev=$(tmux show-option -gqv "@tsesh_bound_$name")
	if [[ -n $prev && $prev != "$key" ]] &&
		tmux list-keys -N -T prefix "$prev" 2>/dev/null | grep -qF "$note"; then
		tmux unbind-key -T prefix "$prev"
	fi
	if [[ -n $key ]]; then
		tmux bind-key -N "$note" "$key" "$@"
		tmux set-option -g "@tsesh_bound_$name" "$key"
	else
		tmux set-option -gu "@tsesh_bound_$name"
	fi
}

# run-shell expands #{client_name} (display-popup's own command is not
# expanded), so the picker learns which client opened it and failures show
# there, not on whichever client tmux calls current. A client name is a tty
# path or "client-N": nothing a shell would split.
tsesh_bind pick "$(opt @tsesh_key_pick s)" "session picker (tsesh)" \
	run-shell -b "tmux display-popup -E -c '#{client_name}' -w 90% -h 85% \"'$tsesh' pick-and-connect --client '#{client_name}'\""
tsesh_bind agents "$(opt @tsesh_key_agents a)" "agent picker (tsesh)" \
	run-shell -b "tmux display-popup -E -c '#{client_name}' -w 90% -h 85% \"'$tsesh' pick-and-connect --mode agents --client '#{client_name}'\""
tsesh_bind last "$(opt @tsesh_key_last g)" "last session (tsesh)" \
	run-shell -b "'$tsesh' last"
# #{pane_id} only: run-shell hands the expanded line to sh -c, and a path
# can carry a newline. tsesh reads the cwd for the pane id itself.
tsesh_bind root "$(opt @tsesh_key_root T)" "session at pane cwd (tsesh)" \
	run-shell -b "'$tsesh' connect --pane '#{pane_id}'"
