"""Tests for bin/tsesh. Run with: python3 -m unittest discover -s tests"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSESH = ROOT / "bin" / "tsesh"


def load_tsesh():
    loader = importlib.machinery.SourceFileLoader("tsesh", str(TSESH))
    spec = importlib.util.spec_from_loader("tsesh", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tsesh"] = module
    loader.exec_module(module)
    return module


tsesh = load_tsesh()
State = tsesh.AgentState
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def fg_seq(key: str) -> str:
    hexcolor = tsesh.CATPPUCCIN[key]
    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))
    return f"38;2;{r};{g};{b}"


def config(**over):
    base = {
        "sessions": (),
        "blacklist": frozenset({".cache"}),
        "noisy_basenames": frozenset({"node_modules"}),
        "find_max_depth": 2,
        "preview_command": "true",
    }
    base.update(over)
    return tsesh.Config(**base)


class RowRendering(unittest.TestCase):
    def test_every_state_renders(self):
        # Regression carried over from tms: a palette key missing for one state
        # killed the whole picker exactly when a crashed agent existed.
        for state in State:
            entry = tsesh.Entry(
                kind="tmux", name="w", session_name="s", worst_state=state
            )
            self.assertIn(tsesh.STATE_GLYPH[state], entry.visible_text())

    def test_colour_by_state(self):
        def row(state):
            return tsesh.Entry(
                kind="tmux", name="w", session_name="s", worst_state=state
            ).visible_text()

        self.assertIn(fg_seq("red"), row(State.crashed))
        self.assertIn(fg_seq("peach"), row(State.blocked))
        self.assertIn(fg_seq("teal"), row(State.done))
        self.assertIn(fg_seq("sky"), row(State.working))
        self.assertIn(fg_seq("sky"), row(None))

    def test_columns_align_with_the_header(self):
        with_state = ANSI.sub(
            "",
            tsesh.Entry(
                kind="tmux",
                name="docs",
                session_name="docs",
                path="/tmp/docs",
                worst_state=State.done,
            ).visible_text(),
        )
        without_state = ANSI.sub(
            "",
            tsesh.Entry(
                kind="tmux", name="shell", session_name="shell", path="/tmp/shell"
            ).visible_text(),
        )
        header = ANSI.sub("", tsesh.header_text().splitlines()[-1])
        self.assertEqual(header.index("session"), with_state.index("docs"))
        self.assertEqual(
            header.index("state"), with_state.index(tsesh.STATE_GLYPH[State.done])
        )
        self.assertEqual(header.index("path"), with_state.index("/tmp/docs"))
        self.assertEqual(header.index("path"), without_state.index("/tmp/shell"))

    def test_fzf_border_inside_popup(self):
        self.assertEqual(tsesh.fzf_border({"TMUX": "/tmp/t,1,0"}), "none")
        self.assertEqual(
            tsesh.fzf_border({"TMUX": "/tmp/t,1,0", "TMUX_PANE": "%1"}), "rounded"
        )

    def test_every_palette_key_is_used(self):
        source = TSESH.read_text(encoding="utf-8")
        for key in tsesh.CATPPUCCIN:
            uses = source.count(f'CATPPUCCIN["{key}"]') + source.count(
                f"CATPPUCCIN['{key}']"
            )
            self.assertGreater(uses, 0, key)


class RowRoundTrip(unittest.TestCase):
    def test_payload_survives(self):
        entry = tsesh.Entry(
            kind="default",
            name="proj",
            session_name="proj",
            path="/tmp/proj",
            startup="nvim",
            split="vertical",
        )
        payload = tsesh.EntryPayload.from_fzf_row(entry.to_fzf_row())
        self.assertEqual(
            (payload.session_name, payload.path, payload.startup, payload.split),
            ("proj", "/tmp/proj", "nvim", "vertical"),
        )

    def test_trailing_empty_fields(self):
        row = tsesh.Entry(
            kind="tmux", name="s", session_name="s", path="/tmp/s"
        ).to_fzf_row()
        self.assertEqual(len(row.split("\t")), len(tsesh.FZF_ROW_FIELDS))
        payload = tsesh.EntryPayload.from_fzf_row(row)
        self.assertIsNone(payload.startup)
        self.assertEqual(payload.split, tsesh.DEFAULT_SPLIT)

    def test_short_row_fails_loudly(self):
        with self.assertRaises(tsesh.ConfigError):
            tsesh.Entry.from_fzf_row("a\tb")


class Paths(unittest.TestCase):
    def test_session_names(self):
        self.assertEqual(tsesh.sanitize_session_part("a.b"), "a_b")
        self.assertEqual(tsesh.sanitize_session_part("a  b//c"), "a-b-c")
        self.assertEqual(tsesh.sanitize_session_part("--x--"), "x")
        home = Path.home()
        self.assertEqual(tsesh.session_name_for_path(str(home / "a.b" / "c")), "a_b/c")
        self.assertEqual(tsesh.session_name_for_path("/"), "session")

    def test_useful_paths(self):
        home = Path.home()
        cfg = config()
        cases = (
            (home / "code", "find", True),
            (home / ".cache", "find", False),
            (home / "code" / "node_modules", "find", False),
            (home / "code" / "node_modules" / "pkg", "find", False),
            (home / ".ssh", "find", False),
            (home / "a" / "b" / "c", "zoxide", False),
            (home / "a" / "b", "zoxide", True),
        )
        for path, mode, want in cases:
            with self.subTest(path=path, mode=mode):
                self.assertEqual(
                    tsesh.is_useful_path(str(path), mode=mode, config=cfg), want
                )

    def test_path_aliases_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            alias = Path(tmp) / "alias"
            real.mkdir()
            alias.symlink_to(real, target_is_directory=True)
            cfg = config()
            self.assertEqual(
                tsesh.build_path_entries(
                    kind="zoxide",
                    paths=[str(alias)],
                    configured_paths={str(real)},
                    mode="zoxide",
                    config=cfg,
                ),
                [],
            )
            listed = tsesh.build_path_entries(
                kind="zoxide",
                paths=[str(real), str(alias)],
                configured_paths=set(),
                mode="zoxide",
                config=cfg,
            )
            self.assertEqual(len(listed), 1)


class Config(unittest.TestCase):
    def setUp(self):
        tsesh.load_config.cache_clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(tsesh.load_config.cache_clear)
        self._paths = (tsesh.CONFIG_PATH, tsesh.LEGACY_CONFIG_PATH)
        self.addCleanup(self._restore)

    def _restore(self):
        tsesh.CONFIG_PATH, tsesh.LEGACY_CONFIG_PATH = self._paths

    def test_no_config_still_works(self):
        tsesh.CONFIG_PATH = Path(self.tmp.name) / "missing.toml"
        tsesh.LEGACY_CONFIG_PATH = Path(self.tmp.name) / "also-missing.toml"
        cfg = tsesh.load_config()
        self.assertEqual(cfg.sessions, ())
        self.assertIn("{path}", cfg.preview_command)

    def test_minimal_config(self):
        tsesh.CONFIG_PATH = Path(self.tmp.name) / "config.toml"
        tsesh.CONFIG_PATH.write_text(
            '[[sessions]]\nname = "notes"\npath = "~/notes"\nsplit = "vertical"\n'
        )
        cfg = tsesh.load_config()
        self.assertEqual([s.name for s in cfg.sessions], ["notes"])
        self.assertEqual(cfg.find_max_depth, 2)

    def test_bad_value_names_the_file(self):
        tsesh.CONFIG_PATH = Path(self.tmp.name) / "config.toml"
        tsesh.CONFIG_PATH.write_text("find_max_depth = -1\n")
        with self.assertRaisesRegex(tsesh.ConfigError, "config.toml"):
            tsesh.load_config()


class BuildEntries(unittest.TestCase):
    """The merge the picker is: which sessions appear, in what order."""

    def setUp(self):
        configured = (
            tsesh.SessionConfig(name="dotfiles", path="/tmp/dotfiles", startup="yazi"),
            tsesh.SessionConfig(name="notes", path="/tmp/notes"),
        )
        cfg = config(sessions=configured, find_max_depth=1)
        originals = (
            tsesh.load_config,
            tsesh.TmuxBackend.list_sessions,
            tsesh.session_states,
            tsesh.zoxide_paths,
        )

        def restore():
            (
                tsesh.load_config,
                tsesh.TmuxBackend.list_sessions,
                tsesh.session_states,
                tsesh.zoxide_paths,
            ) = originals

        self.addCleanup(restore)
        tsesh.load_config = lambda: cfg
        tsesh.TmuxBackend.list_sessions = lambda self: ["zed", "notes", "alpha"]
        tsesh.session_states = lambda: {"notes": State.blocked, "zed": State.crashed}
        tsesh.zoxide_paths = list

    def test_all_mode(self):
        entries = tsesh.build_entries("all")
        names = [e.name for e in entries]
        self.assertEqual(names, ["dotfiles", "notes", "alpha", "zed"])
        by_name = {e.name: e for e in entries}
        self.assertTrue(by_name["notes"].is_running)
        self.assertFalse(by_name["dotfiles"].is_running)
        self.assertEqual(by_name["notes"].worst_state, State.blocked)
        self.assertEqual(by_name["zed"].worst_state, State.crashed)
        self.assertIsNone(by_name["alpha"].worst_state)
        self.assertEqual(
            (by_name["dotfiles"].startup, by_name["dotfiles"].path),
            ("yazi", "/tmp/dotfiles"),
        )

    def test_live_and_pinned_modes(self):
        self.assertEqual(
            [e.name for e in tsesh.build_entries("tmux")], ["alpha", "notes", "zed"]
        )
        self.assertEqual(
            [e.name for e in tsesh.build_entries("default")], ["dotfiles", "notes"]
        )


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class LiveTmux(unittest.TestCase):
    """session_states against a real, isolated tmux server."""

    def setUp(self):
        self.socket = f"tsesh-test-{os.getpid()}"
        os.environ["TSESH_TMUX_SOCKET_NAME"] = self.socket
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_NAME", None)
        self.addCleanup(self.tmux, "kill-server")
        self.tmux("new-session", "-d", "-s", "busy")
        self.tmux("new-session", "-d", "-s", "quiet")
        self.tmux("new-session", "-d", "-s", "odd")

    def tmux(self, *args):
        subprocess.run(
            ["tmux", "-L", self.socket, *args], check=False, capture_output=True
        )

    def test_reads_murmur_session_state(self):
        self.tmux("set-option", "-t", "busy", "@murmur_session_state", "blocked")
        self.tmux("set-option", "-t", "odd", "@murmur_session_state", "bogus")
        self.assertEqual(tsesh.session_states(), {"busy": State.blocked})

    def test_no_server_is_no_state(self):
        os.environ["TSESH_TMUX_SOCKET_NAME"] = f"{self.socket}-absent"
        self.assertEqual(tsesh.session_states(), {})


if __name__ == "__main__":
    unittest.main()
