#!/usr/bin/env python3
"""A stand-in for fzf, put first on PATH by the picker tests.

It replays the parts of fzf the picker relies on: the initial prompt, header
and rows, the ``load`` event, and ``transform`` key bindings whose output is
``change-prompt(...)``, ``reload(...)``, ``transform-header(...)`` and
``transform-prompt(...)`` actions. Keys to press come from FZF_SHIM_KEYS
(comma separated). After each step the visible state is appended to
FZF_SHIM_LOG as one JSON line. FZF_SHIM_PICK, a regex, selects the first
matching row (printed, exit 0); without it the shim aborts like esc (exit 130).
"""

import json
import os
import re
import subprocess
import sys

ACTION = re.compile(
    r"(change-prompt|reload|transform-header|transform-prompt)\((.*?)\)(?=\+|$)",
    re.S,
)


def sh(cmd: str, prompt: str) -> str:
    env = dict(os.environ, FZF_PROMPT=prompt)
    return subprocess.run(
        ["sh", "-c", cmd], env=env, capture_output=True, text=True, check=False
    ).stdout


def main() -> int:
    args = sys.argv[1:]
    state = {"prompt": "", "header": "", "rows": sys.stdin.read().splitlines()}
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
                state[arg[2:]] = value
            i += 2
            continue
        flags.append(arg)
        i += 1

    def log(step: str) -> None:
        with open(os.environ["FZF_SHIM_LOG"], "a") as out:
            out.write(json.dumps({"step": step, "flags": flags, **state}) + "\n")

    def apply(actions: str) -> None:
        for name, arg in ACTION.findall(actions.strip()):
            if name == "change-prompt":
                state["prompt"] = arg
            elif name == "reload":
                state["rows"] = sh(arg, state["prompt"]).splitlines()
                if "load" in binds:
                    apply(binds["load"])
            elif name == "transform-header":
                state["header"] = sh(arg, state["prompt"]).removesuffix("\n")
            elif name == "transform-prompt":
                state["prompt"] = sh(arg, state["prompt"]).removesuffix("\n")

    if "load" in binds:
        apply(binds["load"])
    log("start")
    for key in filter(None, os.environ.get("FZF_SHIM_KEYS", "").split(",")):
        action = binds.get(key, "")
        if action.startswith("transform:"):
            apply(sh(action.removeprefix("transform:"), state["prompt"]))
        log(key)
    if pick := os.environ.get("FZF_SHIM_PICK"):
        for row in state["rows"]:
            if re.search(pick, row):
                print(row)
                return 0
        return 1
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
