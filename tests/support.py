"""Shared test plumbing: bounded waits, and no tmux left behind.

Imported first by every test module. It gives the run one short directory
under /tmp that holds every temporary directory and tmux socket the tests
make (``tempfile.tempdir`` and ``TMUX_TMPDIR`` both point there), so when the
run ends, however it ends, every tmux server still listening there is killed.
Clients and pane processes die with their server.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# Upper bound for any wait on state. Generous: a loaded machine (load average
# far above the core count) can take seconds to start a shell or a Python.
WAIT = 60.0

# Short: a socket path must fit in sun_path (104 bytes on macOS).
RUN_DIR = tempfile.mkdtemp(prefix="ts", dir="/tmp")
tempfile.tempdir = RUN_DIR
os.environ["TMUX_TMPDIR"] = RUN_DIR
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


def kill_test_servers() -> None:
    for socket in test_sockets():
        subprocess.run(
            ["tmux", "-S", socket, "kill-server"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    shutil.rmtree(RUN_DIR, ignore_errors=True)


def _interrupt(_signum: int, _frame: object) -> None:
    # Like ctrl-c: unittest stops (it would record a SystemExit as one failed
    # test and carry on) and the atexit hook runs; a default SIGTERM would
    # skip it.
    raise KeyboardInterrupt


atexit.register(kill_test_servers)
for _sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(_sig, _interrupt)
