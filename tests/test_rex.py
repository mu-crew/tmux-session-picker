"""Tests for tsesh's Rex session listing, switching, creation, preview, and kill."""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from test_tsesh import ANSI, TSESH, tsesh


def make_fake_rex(directory: Path, log_path: Path) -> Path:
    script = directory / "fake-rex"
    script.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open({str(log_path)!r}, "a") as fh:
    fh.write(json.dumps(args) + "\\n")
if "client" in args and "ls" in args:
    kind = os.environ.get("FAKE_REX_CLIENT_KIND", "app")
    print(json.dumps({{"clients": [
        {{"client_id": "client:cli", "info": {{"kind": "cli"}}}},
        {{"client_id": "client:01ab", "info": {{"kind": kind, "label": "mac"}}}},
    ]}}))
elif "ls" in args:
    print(json.dumps({{"sessions": [
        {{"session_id": "session:r1", "label": "dotfiles"}},
        {{"session_id": "session:r2", "label": "murmur"}},
    ]}}))
elif "new" in args and "window" in args:
    print(json.dumps({{"window_id": "window:newtab", "block_ids": ["block:newb"]}}))
elif "new" in args and "window" not in args:
    print(json.dumps({{
        "session_id": "session:created",
        "initial_windows": [{{"window_id": "window:w0", "block_ids": ["block:b0"]}}],
    }}))
elif "inspect" in args:
    print(json.dumps({{
        "session_id": "session:r1",
        "label": "dotfiles",
        "active_window_id": "window:w1",
        "windows": [
            {{"window_id": "window:w1", "label": "editor", "focused_block_id": "block:b1"}}
        ],
    }}))
elif "capture" in args:
    print("captured rex pane output")
""",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


CLIENT_LS = ["--autostart=false", "--timeout", "1s", "client", "ls", "--json"]


class RexIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tsesh-rex-"))
        self.log = self.tmp / "rex.log"
        self.fake_rex = make_fake_rex(self.tmp, self.log)
        self.cfg = self.tmp / "config.toml"
        self.cfg.write_text("")
        self.saved = {
            k: os.environ.get(k)
            for k in ("TSESH_REX", "TSESH_CONFIG", "TERM_PROGRAM", "REX_BLOCK", "TMUX")
        }
        os.environ["TSESH_REX"] = str(self.fake_rex)
        os.environ["TSESH_CONFIG"] = str(self.cfg)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def rex_calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_sessions_view_lists_rex_sessions(self):
        entries = tsesh.build_entries("sessions", live={})
        rex_rows = [e for e in entries if e.kind == "rex"]
        self.assertEqual([e.name for e in rex_rows], ["dotfiles", "murmur"])
        self.assertEqual([e.session_id for e in rex_rows], ["session:r1", "session:r2"])
        self.assertEqual(rex_rows[0].counts, "rex")
        # Not the current-row marker, which sits one column to the left.
        self.assertEqual(rex_rows[0].icon, "■")
        self.assertNotEqual(rex_rows[0].icon, tsesh.CURRENT_MARK)
        self.assertIn("dotfiles", ANSI.sub("", rex_rows[0].visible_text()))

    def test_sessions_hidden_without_a_rex_app(self):
        # A headless Rex server (Linux, no app): nothing could show them.
        os.environ["FAKE_REX_CLIENT_KIND"] = "cli"
        try:
            entries = tsesh.build_entries("sessions", live={})
        finally:
            os.environ.pop("FAKE_REX_CLIENT_KIND", None)
        self.assertEqual([e for e in entries if e.kind == "rex"], [])

    def test_rex_client_must_match_when_named(self):
        os.environ["REX_CLIENT"] = "ipad"
        try:
            self.assertFalse(tsesh.rex_has_app())
            os.environ["REX_CLIENT"] = "mac"
            self.assertTrue(tsesh.rex_has_app())
        finally:
            os.environ.pop("REX_CLIENT", None)

    def test_in_rex_detection_from_rex_block(self):
        self.assertTrue(tsesh.in_rex({"TERM_PROGRAM": "rex", "REX_BLOCK": "block:1"}))
        self.assertTrue(tsesh.in_rex({"TERM_PROGRAM": "rex", "REX_SESSION": "session:1"}))
        self.assertFalse(tsesh.in_rex({"TERM_PROGRAM": "rex"}))
        self.assertFalse(
            tsesh.in_rex({"TMUX": "/tmp/s,1,0", "TERM_PROGRAM": "rex", "REX_BLOCK": "block:1"})
        )

    def test_murmur_jump_env_backfills_rex_session_from_rex_block(self):
        env = tsesh.murmur_jump_env({"TERM_PROGRAM": "rex", "REX_BLOCK": "block:1"})
        self.assertEqual(env["REX_SESSION"], "block:1")
        kept = tsesh.murmur_jump_env(
            {"TERM_PROGRAM": "rex", "REX_BLOCK": "block:1", "REX_SESSION": "session:s"}
        )
        self.assertEqual(kept["REX_SESSION"], "session:s")
        self.assertNotIn("REX_SESSION", tsesh.murmur_jump_env({"REX_BLOCK": "block:1"}))
        self.assertNotIn(
            "REX_SESSION",
            tsesh.murmur_jump_env(
                {"TMUX": "/tmp/s,1,0", "TERM_PROGRAM": "rex", "REX_BLOCK": "block:1"}
            ),
        )

    def _agent_jump(self, before, after):
        os.environ["TERM_PROGRAM"] = "rex"
        os.environ["REX_BLOCK"] = "block:float"
        os.environ.pop("TMUX", None)
        os.environ["TSESH_MURMUR"] = "/usr/bin/true"
        selected = []
        payload = tsesh.EntryPayload(session_name="s", kind="agent", jump_target="j1:abc")
        with (
            mock.patch.object(tsesh, "rex_session_windows", side_effect=[before, after]),
            mock.patch.object(
                tsesh, "rex_select_session", side_effect=lambda s, w="": selected.append((s, w)) or 0
            ),
        ):
            rc = tsesh.connect_agent(payload)
        os.environ.pop("TSESH_MURMUR", None)
        return rc, selected

    def test_agent_jump_in_rex_selects_the_tab_it_opened(self):
        rc, selected = self._agent_jump(
            ("session:s", ["window:a"]), ("session:s", ["window:a", "window:new"])
        )
        self.assertEqual(rc, 0)
        self.assertEqual(selected, [("session:s", "window:new")])

    def test_agent_jump_in_rex_without_a_new_tab_selects_nothing(self):
        # A Rex agent: murmur focuses and selects it itself; no window is added.
        rc, selected = self._agent_jump(("session:s", ["window:a"]), ("session:s", ["window:a"]))
        self.assertEqual(rc, 0)
        self.assertEqual(selected, [])

    def test_select_rex_session(self):
        rc = tsesh.rex_select_session("session:r1")
        self.assertEqual(rc, 0)
        self.assertEqual(
            self.rex_calls(),
            [["--autostart=false", "do", "session.select", "session_id=session:r1"]],
        )

    def test_open_tmux_session_from_rex_opens_new_tab(self):
        os.environ["TERM_PROGRAM"] = "rex"
        os.environ["REX_BLOCK"] = "block:here"
        os.environ.pop("TMUX", None)
        rc = tsesh.rex_open_tmux_tab("work", "=work")
        self.assertEqual(rc, 0)
        self.assertEqual(
            self.rex_calls(),
            [
                [
                    "--autostart=false",
                    "window",
                    "new",
                    "-s",
                    "block:here",
                    "--json",
                    "work",
                    "--",
                    "tmux",
                    "attach-session",
                    "-t",
                    "=work",
                ],
                ["--autostart=false", "--timeout", "1s", "session", "inspect", "block:here", "--json"],
                [
                    "--autostart=false",
                    "do",
                    "session.select",
                    "session_id=session:r1",
                    "window_id=window:newtab",
                ],
            ],
        )

    def test_connect_resolved_in_rex_creates_named_rex_session(self):
        os.environ["TERM_PROGRAM"] = "rex"
        os.environ["REX_BLOCK"] = "block:here"
        os.environ.pop("TMUX", None)
        project = self.tmp / "newproj"
        project.mkdir()
        rc = tsesh.connect_resolved("newproj", str(project), None, "")
        self.assertEqual(rc, 0)
        calls = self.rex_calls()
        self.assertEqual(calls[1], CLIENT_LS)
        self.assertEqual(calls[0], ["--autostart=false", "--timeout", "1s", "ls", "--json"])
        self.assertEqual(
            calls[2],
            ["--autostart=false", "new", "newproj", "-c", os.path.realpath(project), "--json"],
        )
        self.assertEqual(
            calls[3],
            [
                "--autostart=false",
                "do",
                "session.select",
                "session_id=session:created",
                "window_id=window:w0",
            ],
        )

    def test_connect_resolved_in_rex_honors_startup_and_split(self):
        os.environ["TERM_PROGRAM"] = "rex"
        os.environ["REX_BLOCK"] = "block:here"
        os.environ.pop("TMUX", None)
        project = self.tmp / "splitproj"
        project.mkdir()
        rc = tsesh.connect_resolved("splitproj", str(project), "nvim", "vertical")
        self.assertEqual(rc, 0)
        calls = self.rex_calls()
        self.assertEqual(calls[1], CLIENT_LS)
        self.assertEqual(
            calls[3],
            ["--autostart=false", "send", "-b", "block:b0", "--", "nvim\r"],
        )
        self.assertEqual(
            calls[4],
            [
                "--autostart=false",
                "split",
                "-b",
                "block:b0",
                "--split=right",
                "-c",
                os.path.realpath(project),
            ],
        )
        self.assertEqual(
            calls[5],
            [
                "--autostart=false",
                "do",
                "session.select",
                "session_id=session:created",
                "window_id=window:w0",
            ],
        )

    def test_connect_resolved_in_rex_reuses_existing_rex_session(self):
        os.environ["TERM_PROGRAM"] = "rex"
        os.environ["REX_BLOCK"] = "block:here"
        os.environ.pop("TMUX", None)
        project = self.tmp / "dotfiles"
        project.mkdir()
        rc = tsesh.connect_resolved("dotfiles", str(project), None, "")
        self.assertEqual(rc, 0)
        calls = self.rex_calls()
        self.assertEqual(calls[1], CLIENT_LS)
        self.assertEqual(
            calls[2],
            ["--autostart=false", "do", "session.select", "session_id=session:r1"],
        )

    def test_kill_rex_session(self):
        rc = tsesh.kill("rex", "session:r2")
        self.assertEqual(rc, 0)
        self.assertEqual(self.rex_calls(), [["--autostart=false", "kill", "session:r2"]])

    def test_preview_rex_session(self):
        out = subprocess.run(
            [str(TSESH), "preview", "--kind", "rex", "--session-id", "session:r1"],
            env={**os.environ, "TSESH_REX": str(self.fake_rex)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("rex session: dotfiles", out.stdout)
        self.assertIn("* editor", out.stdout)
        self.assertIn("captured rex pane output", out.stdout)
