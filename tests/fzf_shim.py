#!/usr/bin/env python3
"""A stand-in for fzf, put first on PATH by the picker tests.

It replays the parts of fzf the picker relies on: the initial prompt, header
and rows, the ``load`` event, and ``transform`` key bindings whose output is
``change-prompt(...)``, ``reload(...)``, ``transform-header(...)``,
``transform-prompt(...)``, ``transform(...)`` and ``bg-transform(...)`` actions
(run in the foreground here). Keys to press come from FZF_SHIM_KEYS
(comma separated). After each step the visible state is appended to
FZF_SHIM_LOG as one JSON line. FZF_SHIM_PICK, a regex, selects the first
matching row (printed, exit 0); without it the shim aborts like esc (exit 130).
The "start" step also records the rows fzf was started with ("input").
With ``--listen=PATH`` the shim serves fzf's POST endpoint on that unix socket
and waits for the first posted action before it goes on. FZF_SHIM_EARLY
skips that wait: Enter pressed on the rows fzf started with, before anything
was posted.
"""

import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading

ACTION = re.compile(
    r"(change-prompt|reload|transform-header|transform-prompt|bg-transform|transform)"
    r"\((.*?)\)(?=\+|$)",
    re.S,
)


def sh(cmd: str, prompt: str) -> str:
    env = dict(os.environ, FZF_PROMPT=prompt)
    return subprocess.run(
        ["sh", "-c", cmd], env=env, capture_output=True, text=True, check=False
    ).stdout


def main() -> int:
    args = sys.argv[1:]
    text = {"prompt": "", "header": ""}  # what fzf shows above the rows
    rows = sys.stdin.read().splitlines()
    given = list(rows)
    binds: dict[str, str] = {}
    flags: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"--prompt", "--header", "--bind"} and i + 1 < len(args):
            value = args[i + 1]
            if arg == "--bind":
                key, _, action = value.partition(":")
                if action.startswith(("transform", "change-prompt")):
                    binds[key] = action
                else:  # plain "a:b,c:d" lists
                    for part in value.split(","):
                        k, _, a = part.partition(":")
                        binds[k] = a
            else:
                text[arg[2:]] = value
            i += 2
            continue
        flags.append(arg)
        i += 1

    def log(step: str) -> None:
        with open(os.environ["FZF_SHIM_LOG"], "a") as out:
            state = {"step": step, "flags": flags, "rows": rows, **text}
            if step == "start":
                state["input"] = given
            out.write(json.dumps(state) + "\n")

    def apply(actions: str) -> None:
        nonlocal rows
        for name, arg in ACTION.findall(actions.strip()):
            if name == "change-prompt":
                text["prompt"] = arg
            elif name == "reload":
                rows = sh(arg, text["prompt"]).splitlines()
                if "load" in binds:
                    apply(binds["load"])
            elif name == "transform-header":
                text["header"] = sh(arg, text["prompt"]).removesuffix("\n")
            elif name == "transform-prompt":
                text["prompt"] = sh(arg, text["prompt"]).removesuffix("\n")
            elif name in {"transform", "bg-transform"}:
                apply(sh(arg, text["prompt"]))

    early = bool(os.environ.get("FZF_SHIM_EARLY"))
    if "load" in binds:
        apply(binds["load"])
    listen = next((f for f in flags if f.startswith("--listen=")), "")
    if listen:
        posted = threading.Event()

        class Post(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                size = int(self.headers.get("Content-Length", 0))
                apply(self.rfile.read(size).decode())
                self.send_response(200)
                self.end_headers()
                posted.set()

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = socketserver.UnixStreamServer(listen.split("=", 1)[1], Post)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if not early:
            posted.wait(30)
    log("start")
    for key in filter(None, os.environ.get("FZF_SHIM_KEYS", "").split(",")):
        action = binds.get(key, "")
        if action.startswith("transform:"):
            apply(sh(action.removeprefix("transform:"), text["prompt"]))
        log(key)
    if pick := os.environ.get("FZF_SHIM_PICK"):
        for row in rows:
            if re.search(pick, row):
                print(row)
                return 0
        return 1
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
