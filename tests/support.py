"""Shared test plumbing: bounded waits, and no tmux left behind.

Imported first by every test module. It gives the run one short directory
under /tmp that holds every temporary directory and tmux socket the tests
make (``tempfile.tempdir`` and ``TMUX_TMPDIR`` both point there), so when the
run ends, however it ends, every tmux server still listening there is killed.
Clients and pane processes die with their server.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

# TSESH_FAST=1: the fast gate. Skips every test that starts a real tmux
# server or client, or fzf.
FAST = os.environ.get("TSESH_FAST") == "1"


def live(*tools: str) -> Callable[[T], T]:
    """Mark a test (class) that starts real TOOLS (tmux, fzf)."""
    if FAST:
        return unittest.skip("TSESH_FAST=1 skips tests that start tmux or fzf")
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        return unittest.skip(f"needs {' and '.join(missing)}")
    return lambda test: test


# Upper bound for any wait on state. Generous: a loaded machine (load average
# far above the core count) can take seconds to start a shell or a Python.
WAIT = 60.0

# Short: a socket path must fit in sun_path (104 bytes on macOS).
RUN_DIR = tempfile.mkdtemp(prefix="ts", dir="/tmp")
tempfile.tempdir = RUN_DIR
os.environ["TMUX_TMPDIR"] = RUN_DIR
# Never the tmux or Rex server the suite happens to run in: a test that wants
# $TMUX or Rex sets it to its own isolated server/stub.
for _var in ("TMUX", "TMUX_PANE", "REX_BLOCK", "REX_SESSION", "REX_SERVER", "REX_CLIENT", "TERM_PROGRAM"):
    os.environ.pop(_var, None)
os.environ.setdefault("TSESH_REX", "")
# The picker gives murmur 1 s by default; a fake murmur under load needs more.
os.environ["TSESH_MURMUR_TIMEOUT"] = "30"


def wait_until(probe: Callable[[], T], timeout: float = WAIT) -> T | None:
    """PROBE's first truthy result, polled until TIMEOUT seconds pass."""
    deadline = time.monotonic() + timeout
    while True:
        if value := probe():
            return value
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def test_sockets() -> list[str]:
    found = []
    for parent, _, names in os.walk(RUN_DIR):
        for name in names:
            path = os.path.join(parent, name)
            try:
                if stat.S_ISSOCK(os.lstat(path).st_mode):
                    found.append(path)
            except OSError:
                pass
    return found


def kill_server(tmux: Sequence[str]) -> None:
    """Kill the tmux server TMUX (an argv prefix such as ``tmux -S path``)
    and everything its panes run.

    kill-server hangs up the panes, but a shell can outlive that; each pane's
    process group is killed outright as well.
    """
    panes = subprocess.run(
        [*tmux, "list-panes", "-a", "-F", "#{pane_pid}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    ).stdout.split()
    subprocess.run([*tmux, "kill-server"], capture_output=True, timeout=30, check=False)
    for pid in panes:
        with contextlib.suppress(OSError, ValueError):
            os.killpg(int(pid), signal.SIGKILL)


def kill_test_servers() -> None:
    for socket in test_sockets():
        kill_server(["tmux", "-S", socket])
    shutil.rmtree(RUN_DIR, ignore_errors=True)


def _interrupt(_signum: int, _frame: object) -> None:
    # Like ctrl-c: unittest stops (it would record a SystemExit as one failed
    # test and carry on) and the atexit hook runs; a default SIGTERM would
    # skip it.
    raise KeyboardInterrupt


atexit.register(kill_test_servers)
for _sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(_sig, _interrupt)


def program_state_tmux(bindir: str) -> None:
    """Put a ``tmux`` wrapper in BINDIR that maps vtmux's native
    ``#{session_program_state}`` to the user option ``@test_program_state``
    and ``#{window_program_state}`` to ``@test_window_program_state``, which a
    plain tmux can set. Prepend BINDIR to PATH to use it."""
    real = shutil.which("tmux")
    path = os.path.join(bindir, "tmux")
    with open(path, "w") as f:
        f.write(
            f'#!/bin/bash\nargs=()\nfor a in "$@"; do\n'
            f'  a="${{a//session_program_state/@test_program_state}}"\n'
            f'  args+=("${{a//window_program_state/@test_window_program_state}}")\n'
            f'done\nexec {real} "${{args[@]}}"\n'
        )
    os.chmod(path, 0o755)
