#!/usr/bin/env bash
# TPM entry point. Binds under the prefix; override a key before TPM runs:
#   set -g @tsesh_key_pick s     # picker popup
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

pick=$(opt @tsesh_key_pick s)
last=$(opt @tsesh_key_last g)
root=$(opt @tsesh_key_root T)

[[ -n $pick ]] && tmux bind-key -N "session picker (tsesh)" "$pick" \
	display-popup -E -w 90% -h 85% "'$tsesh' pick-and-connect"
[[ -n $last ]] && tmux bind-key -N "last session (tsesh)" "$last" \
	run-shell -b "'$tsesh' last"
# #{pane_id} only: run-shell hands the expanded line to sh -c, and a path
# can carry a newline. tsesh reads the cwd for the pane id itself.
[[ -n $root ]] && tmux bind-key -N "session at pane cwd (tsesh)" "$root" \
	run-shell -b "'$tsesh' connect --pane '#{pane_id}'"
true
