"""Tests for bin/tsesh. Run with: python3 -m unittest discover -s tests"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
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


def setUpModule():
    # Never read the real murmur's state: tests that want one install a fake.
    os.environ["TSESH_MURMUR"] = "/nonexistent/murmur-for-tests"


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
        self.assertIn(fg_seq("maroon"), row(State.error))
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

    def test_murmur_states_parse_and_order(self):
        for raw in ("crashed", "error", "blocked", "done", "working", "waiting"):
            self.assertIsNotNone(State.parse(raw), raw)
        self.assertGreater(State.crashed, State.error)
        self.assertGreater(State.error, State.blocked)
        self.assertGreater(State.working, State.waiting)
        self.assertIn(State.error, tsesh.ATTENTION_STATES)
        self.assertNotIn(State.waiting, tsesh.ATTENTION_STATES)


class Header(unittest.TestCase):
    def test_legend_shows_every_picker_key(self):
        legend = ANSI.sub("", tsesh.header_text().splitlines()[0])
        for key in ("^a", "^s", "^f", "tab", "s-tab", "enter"):
            self.assertIn(key, legend)


class Version(unittest.TestCase):
    def test_version_flag_prints_the_constant(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            tsesh.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"tsesh {tsesh.VERSION}")

    def test_changelog_has_the_current_version_or_unreleased(self):
        log = (TSESH.parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]", log)


class Docs(unittest.TestCase):
    def test_readme_documents_every_state(self):
        readme = (TSESH.parent.parent / "README.md").read_text(encoding="utf-8")
        for state in State:
            self.assertIn(f"`{state.name}`", readme)


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


@contextlib.contextmanager
def mock_env(env, remove=()):
    saved = dict(os.environ)
    os.environ.update(env)
    for key in remove:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


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

    def test_bad_second_session_names_the_file(self):
        tsesh.CONFIG_PATH = Path(self.tmp.name) / "config.toml"
        tsesh.CONFIG_PATH.write_text(
            '[[sessions]]\nname = "a"\npath = "/tmp"\n'
            '[[sessions]]\nname = ""\npath = "/tmp"\n'
        )
        with self.assertRaisesRegex(tsesh.ConfigError, "config.toml"):
            tsesh.load_config()


class PreviewEmptyPath(unittest.TestCase):
    def test_pathless_row_does_not_run_preview_command(self):
        calls = []
        old = tsesh.os.execvp
        tsesh.os.execvp = lambda *a: calls.append(a)
        self.addCleanup(setattr, tsesh.os, "execvp", old)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            tsesh.preview("", "gone", "")
        self.assertEqual(calls, [])
        self.assertIn("session: gone", out.getvalue())


class AttachUsesSocket(unittest.TestCase):
    def test_attach_targets_the_isolated_server(self):
        argvs = []
        old_run, old_last = tsesh.subprocess.run, tsesh.update_last
        tsesh.subprocess.run = lambda argv, **kw: argvs.append(argv)
        tsesh.update_last = lambda name: None
        self.addCleanup(setattr, tsesh.subprocess, "run", old_run)
        self.addCleanup(setattr, tsesh, "update_last", old_last)
        env = {"TSESH_TMUX_SOCKET_PATH": "/tmp/x.sock"}
        with mock_env(env, remove=("TMUX",)):
            tsesh.TmuxBackend().switch("work")
        self.assertEqual(argvs[0][:3], ["tmux", "-S", "/tmp/x.sock"])
        self.assertIn("attach-session", argvs[0])


class Tildify(unittest.TestCase):
    def test_only_a_leading_home_component(self):
        home = str(Path.home())
        self.assertEqual(tsesh.tildify(home), "~")
        self.assertEqual(tsesh.tildify(home + "/x"), "~/x")
        self.assertEqual(tsesh.tildify(home + "2/x"), home + "2/x")
        self.assertEqual(tsesh.tildify("/srv" + home + "/x"), "/srv" + home + "/x")


class TmuxErrorsAreReported(unittest.TestCase):
    def test_failed_tmux_is_a_message_not_a_traceback(self):
        def boom(*a, **kw):
            raise subprocess.CalledProcessError(1, ["tmux"], stderr="no such thing\n")

        old, old_pause = tsesh.connect, tsesh.pause_for_error
        tsesh.connect = boom
        tsesh.pause_for_error = lambda: None
        self.addCleanup(setattr, tsesh, "connect", old)
        self.addCleanup(setattr, tsesh, "pause_for_error", old_pause)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = tsesh.main(["connect", "x"])
        self.assertEqual(code, 1)
        self.assertIn("no such thing", err.getvalue())


class FindPrunesBlacklist(unittest.TestCase):
    def test_find_fallback_skips_blacklisted_dirs(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        (home / "Library" / "deep").mkdir(parents=True)
        (home / "proj").mkdir()
        with (
            mock_env({"HOME": str(home)}),
            unittest.mock.patch.object(tsesh.shutil, "which", return_value=None),
        ):
            cfg = config(blacklist=frozenset({"Library"}))
            found = tsesh.find_paths(cfg)
        self.assertEqual(found, [str(home / "proj")])

    def test_blacklist_entry_is_literal_not_a_glob(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        for name in ("dev1", "dev[0-9]", "normal"):
            (home / name).mkdir()
        with (
            mock_env({"HOME": str(home)}),
            unittest.mock.patch.object(tsesh.shutil, "which", return_value=None),
        ):
            found = tsesh.find_paths(config(blacklist=frozenset({"dev[0-9]"})))
        self.assertEqual(sorted(found), [str(home / "dev1"), str(home / "normal")])


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
            tsesh.TmuxBackend.live_sessions,
            tsesh.zoxide_paths,
        )

        def restore():
            (
                tsesh.load_config,
                tsesh.TmuxBackend.live_sessions,
                tsesh.zoxide_paths,
            ) = originals

        self.addCleanup(restore)
        tsesh.load_config = lambda: cfg
        tsesh.TmuxBackend.live_sessions = lambda self: {
            "zed": State.crashed,
            "notes": State.blocked,
            "alpha": None,
        }
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

    def test_sessions_mode_is_pinned_then_live(self):
        self.assertEqual(
            [e.name for e in tsesh.build_entries("sessions")],
            ["dotfiles", "notes", "alpha", "zed"],
        )

    def test_modes_are_all_sessions_find(self):
        self.assertEqual(tsesh.MODES, ["all", "sessions", "find"])


class PickerKeys(unittest.TestCase):
    def test_binds_follow_the_keymap(self):
        cmd = tsesh._fzf_command("all")
        spec = " ".join(a for i, a in enumerate(cmd) if cmd[i - 1] == "--bind")
        binds = set(re.findall(r"(?:^|[\s,])([a-z-]+):", spec))
        self.assertTrue({"ctrl-a", "ctrl-s", "ctrl-f", "tab", "btab"} <= binds)
        for gone in ("ctrl-c", "ctrl-t", "ctrl-x"):
            self.assertNotIn(gone, binds)


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class LiveTmux(unittest.TestCase):
    """live_sessions against a real, isolated tmux server."""

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
        self.assertEqual(tsesh.TmuxBackend().live_sessions()["busy"], State.blocked)

    def test_no_server_is_no_state(self):
        os.environ["TSESH_TMUX_SOCKET_NAME"] = f"{self.socket}-absent"
        self.assertEqual(tsesh.TmuxBackend().live_sessions(), {})


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class CreateWithDefaultBaseIndex(unittest.TestCase):
    """create() on a real isolated server whose indexes start at 0."""

    def setUp(self):
        self.sock = Path(tempfile.mkdtemp()) / "s"
        os.environ["TSESH_TMUX_SOCKET_PATH"] = str(self.sock)
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_PATH", None)
        self.addCleanup(shutil.rmtree, self.sock.parent, True)
        self.addCleanup(self.tmux, "kill-server")
        # Start the server here with no config so base-index stays 0.
        self.tmux("new-session", "-d", "-s", "keep")
        old = tsesh.start_server_in_own_scope
        tsesh.start_server_in_own_scope = lambda args: False
        self.addCleanup(setattr, tsesh, "start_server_in_own_scope", old)

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", "-f", "/dev/null", "-S", str(self.sock), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_startup_and_split_reach_the_new_pane(self):
        tsesh.TmuxBackend().create("work", "/tmp", "echo hi", "vertical")
        panes = self.tmux("list-panes", "-t", "=work", "-F", "#{pane_index}")
        self.assertEqual(len(panes.stdout.split()), 2)


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class NameCollision(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.sock = self.tmp / "s"
        os.environ["TSESH_TMUX_SOCKET_PATH"] = str(self.sock)
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_PATH", None)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self._kill)
        self.run_tmux("new-session", "-d", "-s", "keep")
        for owner, attr, value in (
            (tsesh, "start_server_in_own_scope", lambda args: False),
            (tsesh.TmuxBackend, "switch", lambda self, name, target=None: None),
        ):
            self.addCleanup(setattr, owner, attr, getattr(owner, attr))
            setattr(owner, attr, value)

    def run_tmux(self, *args):
        return subprocess.run(
            ["tmux", "-f", "/dev/null", "-S", str(self.sock), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def _kill(self):
        self.run_tmux("kill-server")

    def test_distinct_dirs_with_one_sanitized_name_get_distinct_sessions(self):
        a, b = self.tmp / "a.b", self.tmp / "a_b"
        a.mkdir()
        b.mkdir()
        tsesh.connect(str(a))
        tsesh.connect(str(b))
        paths = self.run_tmux("list-sessions", "-F", "#{session_path}").stdout.split()
        self.assertIn(str(a), paths)
        self.assertIn(str(b), paths)
        tsesh.connect(str(a))  # same dir again reuses its session
        names = self.run_tmux("list-sessions", "-F", "#{session_name}").stdout.split()
        self.assertEqual(len(names), 3, names)

    def sessions(self):
        out = self.run_tmux("list-sessions", "-F", "#{session_name}").stdout
        return out.split()

    def tmux_bytes(self, *args):
        return subprocess.run(
            ["tmux", "-f", "/dev/null", "-S", str(self.sock), *args],
            check=False,
            capture_output=True,
        ).stdout

    def session_paths(self):
        """Every session's raw #{session_path}, one display-message each.

        Bytes in, one trailing newline out: a path may hold any other byte.
        """
        ids = self.tmux_bytes("list-sessions", "-F", "#{session_id}").split()
        return [
            os.fsdecode(
                self.tmux_bytes("display-message", "-p", "-t", i, "#{session_path}")
            ).removesuffix("\n")
            for i in ids
        ]

    def test_recreated_session_does_not_duplicate_a_surviving_suffixed_one(self):
        a, b = self.tmp / "a.b", self.tmp / "a_b"
        a.mkdir()
        b.mkdir()
        tsesh.connect(str(a))
        tsesh.connect(str(b))
        base = tsesh.session_name_for_path(str(a))
        self.run_tmux("kill-session", "-t", f"={base}")
        tsesh.connect(str(b))
        self.assertEqual(self.session_paths().count(str(b)), 1, self.sessions())

    def test_path_with_newline_reuses_its_session(self):
        d = self.tmp / "double\nline"
        d.mkdir()
        tsesh.connect(str(d))
        tsesh.connect(str(d))
        self.assertEqual(self.session_paths().count(str(d)), 1, self.sessions())

    def pick_find_row(self, home, target):
        """pick_and_connect("find") over real rows, fzf shim picks TARGET."""
        shim_dir = self.tmp / "bin"
        shim_dir.mkdir(exist_ok=True)
        shim = shim_dir / "fzf"
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "for row in sys.stdin.read().split('\\n'):\n"
            "    if row.split('\\t')[3] == os.environ['SHIM_PICK']:\n"
            "        print(row)\n"
            "        sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        shim.chmod(0o755)
        old_load = tsesh.load_config
        tsesh.load_config = lambda: config(blacklist=frozenset())
        self.addCleanup(setattr, tsesh, "load_config", old_load)
        env = {
            "HOME": str(home),
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "SHIM_PICK": str(target),
        }
        with mock_env(env):
            self.assertEqual(tsesh.pick_and_connect("find"), 0)

    def test_picker_rows_for_colliding_dirs_get_distinct_sessions(self):
        home = self.tmp / "home"
        a, b = home / "a.b", home / "a_b"
        a.mkdir(parents=True)
        b.mkdir()
        for d in (a, b):
            self.pick_find_row(home, d)
        self.assertEqual(
            sorted(self.session_paths()), sorted([str(a), str(b), str(Path.cwd())])
        )

    def test_cr_and_lf_directories_are_distinct(self):
        cr, lf = self.tmp / "double\rline", self.tmp / "double\nline"
        cr.mkdir()
        lf.mkdir()
        self.run_tmux("new-session", "-d", "-s", "double-line", "-c", str(cr))
        tsesh.connect(str(lf))
        self.assertIn(str(lf), self.session_paths())
        tsesh.connect(str(cr))
        tsesh.connect(str(cr))
        self.assertEqual(self.session_paths().count(str(cr)), 1)

    def test_retargeted_symlink_does_not_alias_the_old_session(self):
        home = self.tmp / "home"
        old, new = home / "old-dir", home / "new-dir"
        old.mkdir(parents=True)
        new.mkdir()
        link = home / "current"
        link.symlink_to(old)
        tsesh.connect(str(link))
        link.unlink()
        link.symlink_to(new)
        tsesh.connect(str(new))
        self.assertIn(str(new), self.session_paths())
        self.pick_find_row(home, old)  # via the picker: old gets its session
        self.assertEqual(self.session_paths().count(str(old)), 1)
        self.pick_find_row(home, new)
        self.assertEqual(self.session_paths().count(str(new)), 1)

    PATH_NAMES = (
        "with space",
        "dot.ted",
        "dollar$HOME",
        "token-#{version}",
        "com,ma",
        "brace}",
        "hash##",
        "cr\rname",
        "lf\nname",
        "plain",
        "plain\x1etail",
        "unit\x1fsep",
        "caf\u00e9",
    )

    def test_every_supported_path_routes_to_its_own_session(self):
        home = self.tmp / "home"
        home.mkdir()
        dirs = []
        for name in self.PATH_NAMES:
            d = home / name
            d.mkdir()
            dirs.append(str(d))
        for _ in range(2):  # the second pass must reuse, not create
            for d in dirs:
                tsesh.connect(d)
        paths = self.session_paths()
        for d in dirs:
            self.assertEqual(paths.count(d), 1, (d, paths))
        self.assertEqual(len(paths), len(dirs) + 1, paths)  # + keep

    def test_every_pickable_path_routes_to_its_own_session(self):
        home = self.tmp / "home"
        home.mkdir()
        dirs = []
        for name in self.PATH_NAMES:
            if "\r" in name or "\n" in name:  # fzf cannot show these rows
                continue
            d = home / name
            d.mkdir()
            dirs.append(str(d))
        for _ in range(2):
            for d in dirs:
                self.pick_find_row(home, d)
        paths = self.session_paths()
        for d in dirs:
            self.assertEqual(paths.count(d), 1, (d, paths))
        self.assertEqual(len(paths), len(dirs) + 1, paths)

    def test_session_made_through_a_symlink_by_older_tsesh_is_reused(self):
        home = self.tmp / "home"
        work, link = home / "workspace", home / "current"
        work.mkdir(parents=True)
        link.symlink_to(work)
        self.run_tmux("new-session", "-d", "-s", "workspace", "-c", str(link))
        tsesh.connect(str(link))
        tsesh.connect(str(link))
        self.assertEqual(len(self.session_paths()), 2, self.session_paths())

    def test_symlink_to_a_directory_named_like_a_format_stays_literal(self):
        home = self.tmp / "home"
        literal = home / "proj-#{version}"
        literal.mkdir(parents=True)
        (home / "proj-3.8").mkdir()
        link = home / "current"
        link.symlink_to(literal)
        tsesh.connect(str(link))
        self.assertIn(str(literal), self.session_paths())
        ids = self.tmux_bytes("list-sessions", "-F", "#{session_id}").split()
        cwds = [
            os.fsdecode(
                self.tmux_bytes(
                    "display-message", "-p", "-t", i, "#{pane_current_path}"
                )
            ).removesuffix("\n")
            for i in ids
        ]
        self.assertIn(str(literal), cwds)

    def test_session_named_like_an_id_does_not_alias_the_matched_id(self):
        home = self.tmp / "home"
        d = home / "dollar$HOME"
        d.mkdir(parents=True)
        # Session "$0" at d gets id $N (N>0); id $0 is the "keep" session.
        self.run_tmux("new-session", "-d", "-s", "$0", "-c", str(d))
        switched = []
        old = tsesh.TmuxBackend.switch
        tsesh.TmuxBackend.switch = lambda self, name, target=None: switched.append(
            (name, target)
        )
        self.addCleanup(setattr, tsesh.TmuxBackend, "switch", old)
        tsesh.connect(str(d))
        self.assertEqual(len(switched), 1)
        name, target = switched[0]
        resolved = self.tmux_bytes(
            "display-message", "-p", "-t", target or f"={name}", "#{session_path}"
        )
        self.assertEqual(os.fsdecode(resolved).removesuffix("\n"), str(d))


class FakeServer:
    """A tmux server that may "restore" sessions when started.

    Patches the module-level helpers TmuxBackend uses and records the order
    of server starts and session creations.
    """

    def __init__(self, restores=(), scoped=True):
        self.restores = set(restores)
        self.scoped = scoped
        self.running = False
        self.sessions: set[str] = set()
        self.calls: list[tuple[str, ...]] = []

    def start(self, args):
        if args[0] == "start-server":
            self.sessions |= self.restores
            self.running = bool(self.sessions)  # exit-empty
        else:
            self.sessions |= self.restores | {args[args.index("-s") + 1]}
            self.running = True

    def server_running(self):
        return self.running

    def scope(self, args):
        self.calls.append(("scope", *args))
        if self.scoped:
            self.start(args)
        return self.scoped

    def tmux_cmd(self, *args, check=True, capture=True):
        self.calls.append(("tmux", *args))
        if args[0] == "has-session":
            name = args[2].lstrip("=").removesuffix(":")
            rc = 0 if self.running and name in self.sessions else 1
        elif args[0] in ("start-server", "new-session"):
            if args[0] == "new-session" and self.running:
                assert args[3] not in self.sessions, "duplicate session"
            self.start(args)
            rc = 0
        else:
            rc = 0
        return subprocess.CompletedProcess(args, rc, "", "")

    def patched(self, testcase):
        for name, fake in (
            ("server_running", self.server_running),
            ("start_server_in_own_scope", self.scope),
            ("tmux_cmd", self.tmux_cmd),
        ):
            old = getattr(tsesh, name)
            setattr(tsesh, name, fake)
            testcase.addCleanup(setattr, tsesh, name, old)
        return self

    def verbs(self):
        return [c[1] for c in self.calls]


class ServerStartRestore(unittest.TestCase):
    """A restoring tmux brings sessions back when the server starts."""

    def test_restored_session_is_not_created(self):
        fake = FakeServer(restores={"work"}).patched(self)
        tsesh.TmuxBackend().create("work", "/", "make")
        self.assertEqual(fake.sessions, {"work"})
        self.assertNotIn("new-session", fake.verbs())
        self.assertNotIn("send-keys", fake.verbs())

    def test_connect_switches_to_restored_session(self):
        fake = FakeServer(restores={"work"}).patched(self)
        switched = []
        old = tsesh.TmuxBackend.switch
        tsesh.TmuxBackend.switch = lambda self, name: switched.append(name)
        self.addCleanup(setattr, tsesh.TmuxBackend, "switch", old)
        self.assertEqual(tsesh.connect_resolved("work", "/", None), 0)
        self.assertEqual(switched, ["work"])
        self.assertNotIn("new-session", fake.verbs())

    def test_other_session_is_created_after_restore(self):
        fake = FakeServer(restores={"work"}).patched(self)
        tsesh.TmuxBackend().create("fresh", "/", None)
        self.assertEqual(fake.sessions, {"work", "fresh"})
        self.assertEqual(fake.verbs().count("new-session"), 1)

    def test_nothing_to_restore_still_creates_in_scope(self):
        fake = FakeServer().patched(self)
        tsesh.TmuxBackend().create("fresh", "/", None)
        self.assertEqual(fake.sessions, {"fresh"})
        self.assertEqual(
            [c[:2] for c in fake.calls if c[0] == "scope"],
            [("scope", "start-server"), ("scope", "new-session")],
        )

    def test_without_scope_falls_back_to_plain_tmux(self):
        fake = FakeServer(scoped=False).patched(self)
        tsesh.TmuxBackend().create("fresh", "/", None)
        self.assertEqual(fake.sessions, {"fresh"})

    def test_running_server_is_not_restarted(self):
        fake = FakeServer().patched(self)
        fake.running, fake.sessions = True, {"a"}
        tsesh.TmuxBackend().create("b", "/", None)
        self.assertEqual(fake.sessions, {"a", "b"})
        self.assertFalse([c for c in fake.calls if c[0] == "scope"])


class PickerStartsServer(unittest.TestCase):
    def test_server_started_in_scope_before_listing(self):
        fake = FakeServer(restores={"work"}).patched(self)
        listed = []

        def snapshot(self):
            if not fake.running:
                return None
            listed.append(sorted(fake.sessions))
            return dict.fromkeys(listed[-1])

        old = tsesh.TmuxBackend.snapshot
        tsesh.TmuxBackend.snapshot = snapshot
        self.addCleanup(setattr, tsesh.TmuxBackend, "snapshot", old)
        old_load = tsesh.load_config
        tsesh.load_config = lambda: config()
        self.addCleanup(setattr, tsesh, "load_config", old_load)
        old_run = tsesh.subprocess.run
        tsesh.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 1)
        self.addCleanup(setattr, tsesh.subprocess, "run", old_run)

        tsesh.pick_and_connect("sessions")
        self.assertEqual(fake.calls[0], ("scope", "start-server"))
        self.assertEqual(listed, [["work"]])

    def test_running_server_is_left_alone(self):
        fake = FakeServer().patched(self)
        fake.running = True
        tsesh.TmuxBackend().ensure_server()
        self.assertEqual(fake.calls, [])


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class PickerListsOnce(unittest.TestCase):
    def test_running_server_is_listed_once_before_fzf(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        sock = tmp / "s"
        os.environ["TSESH_TMUX_SOCKET_PATH"] = str(sock)
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_PATH", None)
        tmux = ["tmux", "-f", "/dev/null", "-S", str(sock)]
        subprocess.run([*tmux, "new-session", "-d", "-s", "x"], check=True)
        self.addCleanup(subprocess.run, [*tmux, "kill-server"], capture_output=True)
        calls = []
        real = tsesh.tmux_cmd

        def spy(*args, **kw):
            calls.append(args)
            return real(*args, **kw)

        for owner, attr, value in (
            (tsesh, "tmux_cmd", spy),
            (tsesh, "load_config", lambda: config()),
            (tsesh, "_fzf_command", lambda mode, query="": ["true"]),
        ):
            self.addCleanup(setattr, owner, attr, getattr(owner, attr))
            setattr(owner, attr, value)
        tsesh.fzf("sessions")
        listings = [c for c in calls if c[0] == "list-sessions"]
        self.assertEqual(len(listings), 1, calls)


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class PlainTmuxNoRestore(unittest.TestCase):
    """Real tmux has no snapshot: start-server exits, create still works."""

    def setUp(self):
        self.socket = f"tsesh-plain-{os.getpid()}"
        saved_path = os.environ.pop("TSESH_TMUX_SOCKET_PATH", None)
        if saved_path is not None:
            self.addCleanup(
                os.environ.__setitem__, "TSESH_TMUX_SOCKET_PATH", saved_path
            )
        os.environ["TSESH_TMUX_SOCKET_NAME"] = self.socket
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_NAME", None)
        self.addCleanup(
            subprocess.run,
            ["tmux", "-L", self.socket, "kill-server"],
            check=False,
            capture_output=True,
        )

    def test_ensure_server_leaves_no_sessions(self):
        tsesh.TmuxBackend().ensure_server()
        self.assertEqual(tsesh.TmuxBackend().live_sessions(), {})

    def test_create_makes_the_session(self):
        tsesh.TmuxBackend().create("first", "/", None)
        self.assertEqual(list(tsesh.TmuxBackend().live_sessions()), ["first"])


class UserManagerCgroup(unittest.TestCase):
    """Only a server started under a user@ unit moves to its own scope.

    A login shell's session-N.scope outlives logout; user@UID.service does
    not, so moving an ssh-started server there would kill it at logout.
    """

    def test_unit_of_user_manager(self):
        cgroup = (
            "0::/user.slice/user-1000.slice/user@1000.service"
            "/app.slice/sway-foot-server.service\n"
        )
        self.assertTrue(tsesh.in_user_manager(cgroup))

    def test_login_session_scope(self):
        cgroup = "0::/user.slice/user-1000.slice/session-3.scope\n"
        self.assertFalse(tsesh.in_user_manager(cgroup))

    def test_hybrid_host_reads_systemd_hierarchy(self):
        cgroup = (
            "12:memory:/user.slice\n"
            "1:name=systemd:/user.slice/user-1000.slice/session-3.scope\n"
            "0::/user.slice/user-1000.slice/user@1000.service\n"
        )
        self.assertEqual(
            tsesh.systemd_cgroup(cgroup), "/user.slice/user-1000.slice/session-3.scope"
        )
        self.assertFalse(tsesh.in_user_manager(cgroup))


def own_cgroup() -> str:
    try:
        return tsesh.systemd_cgroup(Path("/proc/self/cgroup").read_text())
    except OSError:
        return ""


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
@unittest.skipUnless(shutil.which("systemd-run"), "needs systemd-run")
@unittest.skipUnless("/user@" in own_cgroup(), "needs to run under a user@ unit")
class ServerScope(unittest.TestCase):
    """A server tsesh starts must not share its parent unit's cgroup.

    Otherwise stopping the unit tsesh ran under (foot --server) kills it.
    """

    def setUp(self):
        self.socket = f"tsesh-scope-{os.getpid()}"
        saved_path = os.environ.pop("TSESH_TMUX_SOCKET_PATH", None)
        if saved_path is not None:
            self.addCleanup(
                os.environ.__setitem__, "TSESH_TMUX_SOCKET_PATH", saved_path
            )
        os.environ["TSESH_TMUX_SOCKET_NAME"] = self.socket
        self.addCleanup(os.environ.pop, "TSESH_TMUX_SOCKET_NAME", None)
        self.addCleanup(
            subprocess.run,
            ["tmux", "-L", self.socket, "kill-server"],
            check=False,
            capture_output=True,
        )

    def server_cgroup(self) -> str:
        pid = tsesh.tmux_cmd("display-message", "-p", "#{pid}").stdout.strip()
        return tsesh.systemd_cgroup(Path(f"/proc/{pid}/cgroup").read_text())

    def test_new_server_gets_its_own_scope(self):
        tsesh.TmuxBackend().create("first", "/", None)
        cgroup = self.server_cgroup()
        self.assertNotEqual(cgroup, own_cgroup())
        self.assertRegex(cgroup, r"/run-[^/]+\.scope$")

    def test_second_session_joins_running_server(self):
        tsesh.TmuxBackend().create("first", "/", None)
        tsesh.TmuxBackend().create("second", "/", None)
        self.assertEqual(list(tsesh.TmuxBackend().live_sessions()), ["first", "second"])

    def test_dollar_in_name_reaches_tmux_verbatim(self):
        tsesh.TmuxBackend().create("literal-${USER}", "/", None)
        self.assertEqual(list(tsesh.TmuxBackend().live_sessions()), ["literal-${USER}"])


FAKE_MURMUR = """#!/usr/bin/env python3
import os, sys, time
with open(os.environ["FAKE_MURMUR_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[:3] == ["status", "--json", "--cached"]:
    mode = os.environ.get("FAKE_MURMUR_MODE", "ok")
    if mode == "old":
        sys.stderr.write("error: unknown option '--cached'\\n")
        sys.exit(1)
    if mode == "slow":
        time.sleep(5)
    sys.stdout.write(open(os.environ["FAKE_MURMUR_JSON"]).read())
    sys.exit(0)
if args[:1] == ["jump"]:
    if os.environ.get("FAKE_MURMUR_NOJUMP"):
        sys.stderr.write("error: unknown command 'jump'\\n")
        sys.exit(1)
    if args[1:] == ["--help"]:
        sys.exit(0)
    sys.exit(int(os.environ.get("FAKE_MURMUR_JUMP_RC", "0")))
"""


def agent_pane(**over):
    pane = {
        "pane": "%1",
        "local": True,
        "host": "box",
        "host_id": "h1",
        "server": {"kind": "default"},
        "session_name": "notes",
        "window": "@1",
        "window_name": "editor",
        "agent_name": "a",
        "label": "agent-a",
        "render_state": "blocked",
        "visible": True,
        "jump_target": "j1:abc",
        "updated_at": None,
    }
    pane.update(over)
    return pane


class FakeMurmur(unittest.TestCase):
    """A murmur on PATH-equivalent (TSESH_MURMUR) that records its calls."""

    def install(self, panes, mode="ok"):
        import json

        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.log = self.dir / "log"
        self.log.write_text("")
        script = self.dir / "murmur"
        script.write_text(FAKE_MURMUR)
        script.chmod(0o755)
        (self.dir / "status.json").write_text(
            json.dumps({"counts": {}, "panes": panes, "peers": []})
        )
        env = {
            "TSESH_MURMUR": str(script),
            "FAKE_MURMUR_LOG": str(self.log),
            "FAKE_MURMUR_JSON": str(self.dir / "status.json"),
            "FAKE_MURMUR_MODE": mode,
        }
        patch = unittest.mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        for var in ("TMUX", "TSESH_TMUX_SOCKET_PATH", "TSESH_TMUX_SOCKET_NAME"):
            hide = unittest.mock.patch.dict(os.environ)
            hide.start()
            self.addCleanup(hide.stop)
            os.environ.pop(var, None)

    def calls(self):
        return self.log.read_text().splitlines()

    def wait_for_call(self, prefix):
        import time

        for _ in range(40):
            if any(c.startswith(prefix) for c in self.calls()):
                return True
            time.sleep(0.05)
        return False


class MurmurProbe(FakeMurmur):
    def test_no_murmur_means_no_snapshot(self):
        self.assertIsNone(tsesh.murmur_panes())  # TSESH_MURMUR is nonexistent

    def test_capable_murmur_gives_panes_and_warms_the_cache(self):
        self.install([agent_pane()])
        panes = tsesh.murmur_panes()
        self.assertEqual([p["label"] for p in panes], ["agent-a"])
        self.assertIn("status --json --cached", self.calls())
        self.assertTrue(self.wait_for_call("collect --quiet --floored"))

    def test_old_murmur_without_cached_is_ignored(self):
        self.install([agent_pane()], mode="old")
        self.assertIsNone(tsesh.murmur_panes())
        self.assertFalse(any(c.startswith("collect") for c in self.calls()))

    def test_panes_without_derived_fields_are_ignored(self):
        pane = agent_pane()
        del pane["render_state"]
        self.install([pane])
        self.assertIsNone(tsesh.murmur_panes())

    def test_slow_murmur_times_out(self):
        self.install([agent_pane()], mode="slow")
        with unittest.mock.patch.dict(os.environ, {"TSESH_MURMUR_TIMEOUT": "0.2"}):
            self.assertIsNone(tsesh.murmur_panes())


class MurmurSnapshotValidation(FakeMurmur):
    """A malformed snapshot is rejected as a whole, never half-used."""

    def setUp(self):
        cfg = config()
        for owner, attr, value in (
            (tsesh, "load_config", lambda: cfg),
            (tsesh, "zoxide_paths", list),
            (tsesh.TmuxBackend, "snapshot", lambda self: {"notes": State.blocked}),
        ):
            self.addCleanup(setattr, owner, attr, getattr(owner, attr))
            setattr(owner, attr, value)

    def assert_legacy(self, pane):
        self.install([pane])
        self.assertIsNone(tsesh.murmur_panes())
        entries = tsesh.build_entries("all")
        self.assertFalse([e for e in entries if e.kind == "agent"])
        notes = next(e for e in entries if e.name == "notes")
        self.assertEqual(notes.agent_counts, ())
        self.assertEqual(notes.worst_state, State.blocked)
        self.assertFalse(any(c.startswith("collect") for c in self.calls()))

    def test_missing_fields_fall_back(self):
        for field in ("label", "visible", "server", "local", "pane", "host"):
            with self.subTest(missing=field):
                pane = agent_pane()
                del pane[field]
                self.assert_legacy(pane)

    def test_ill_typed_fields_fall_back(self):
        bad = {
            "label": 3,
            "visible": "yes",
            "local": 1,
            "server": {"kind": "bogus"},
            "render_state": "sleeping",
            "session_name": 7,
            "updated_at": "now",
            "jump_target": "",
        }
        for field, value in bad.items():
            with self.subTest(field=field):
                self.assert_legacy(agent_pane(**{field: value}))

    def test_nan_is_not_a_traceback(self):
        self.install([agent_pane()])
        raw = (
            (self.dir / "status.json")
            .read_text()
            .replace('"updated_at": null', '"updated_at": NaN')
        )
        (self.dir / "status.json").write_text(raw)
        self.assertIsNone(tsesh.murmur_panes())
        entries = tsesh.build_entries("sessions")
        self.assertEqual(entries[0].worst_state, State.blocked)

    def test_non_object_snapshot_falls_back(self):
        self.install([])
        (self.dir / "status.json").write_text("[]")
        self.assertIsNone(tsesh.murmur_panes())


class MurmurRows(FakeMurmur):
    def setUp(self):
        cfg = config(sessions=(tsesh.SessionConfig(name="pinned", path="/tmp/pinned"),))
        for owner, attr, value in (
            (tsesh, "load_config", lambda: cfg),
            (tsesh, "zoxide_paths", list),
            (
                tsesh.TmuxBackend,
                "snapshot",
                lambda self: {"notes": None, "other": State.working},
            ),
        ):
            self.addCleanup(setattr, owner, attr, getattr(owner, attr))
            setattr(owner, attr, value)

    def rows(self, mode="all"):
        return tsesh.build_entries(mode)

    def test_attention_agents_lead_the_all_view(self):
        self.install(
            [
                agent_pane(label="first", render_state="crashed"),
                agent_pane(pane="%2", label="busy", render_state="working"),
                agent_pane(pane="%3", label="second", render_state="done"),
            ]
        )
        entries = self.rows()
        agents = [e for e in entries if e.kind == "agent"]
        self.assertEqual([e.name for e in agents], ["first", "second"])
        self.assertEqual([e.kind for e in entries[:2]], ["agent", "agent"])
        self.assertEqual(agents[0].worst_state, State.crashed)

    def test_agent_rows_are_not_in_the_sessions_view(self):
        self.install([agent_pane()])
        self.assertFalse([e for e in self.rows("sessions") if e.kind == "agent"])

    def test_murmur_without_jump_offers_no_agent_rows(self):
        self.install(
            [agent_pane(pane="%1", render_state="blocked"), agent_pane(pane="%2")]
        )
        with unittest.mock.patch.dict(os.environ, {"FAKE_MURMUR_NOJUMP": "1"}):
            entries = self.rows()
        self.assertFalse([e for e in entries if e.kind == "agent"])
        notes = next(e for e in entries if e.name == "notes")
        self.assertEqual(sum(n for _, n in notes.agent_counts), 2)
        self.assertFalse([c for c in self.calls() if c.startswith("jump j1:")])

    def test_invisible_agents_get_no_row(self):
        self.install([agent_pane(visible=False)])
        self.assertFalse([e for e in self.rows() if e.kind == "agent"])

    def test_session_row_shows_a_state_breakdown(self):
        self.install(
            [
                agent_pane(pane="%1", render_state="working"),
                agent_pane(pane="%2", render_state="working"),
                agent_pane(pane="%3", render_state="done"),
                agent_pane(pane="%4", render_state="idle"),
            ]
        )
        notes = next(e for e in self.rows() if e.name == "notes")
        text = ANSI.sub("", notes.visible_text())
        self.assertIn(f"{tsesh.STATE_GLYPH[State.working]}2", text)
        self.assertIn(f"{tsesh.STATE_GLYPH[State.done]}1", text)
        self.assertNotIn("idle", text)

    def test_other_servers_do_not_count_toward_sessions(self):
        self.install([agent_pane(server={"kind": "label", "value": "private"})])
        notes = next(e for e in self.rows() if e.name == "notes")
        self.assertEqual(notes.agent_counts, ())
        agent = next(e for e in self.rows() if e.kind == "agent")
        self.assertEqual(agent.here, "")

    def test_no_murmur_is_todays_behaviour(self):
        entries = self.rows()
        self.assertFalse([e for e in entries if e.kind == "agent"])
        self.assertEqual([e.name for e in entries][:1], ["pinned"])

    def test_agent_row_survives_the_fzf_round_trip(self):
        self.install([agent_pane()])
        row = next(e for e in self.rows() if e.kind == "agent").to_fzf_row()
        payload = tsesh.EntryPayload.from_fzf_row(row)
        self.assertEqual(
            (payload.kind, payload.pane, payload.jump_target, payload.here),
            ("agent", "%1", "j1:abc", "1"),
        )


@unittest.skipUnless(shutil.which("tmux"), "needs tmux")
class AmbientServer(FakeMurmur):
    """tsesh with no socket override talks to the server $TMUX names."""

    def test_here_follows_the_socket_in_tmux_env(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        sock = tmp / "s"
        tmux = ["tmux", "-f", "/dev/null", "-S", str(sock)]
        subprocess.run([*tmux, "new-session", "-d", "-s", "origin"], check=True)
        subprocess.run([*tmux, "new-session", "-d", "-s", "notes"], check=True)
        self.addCleanup(subprocess.run, [*tmux, "kill-server"], capture_output=True)
        pane = subprocess.run(
            [*tmux, "list-panes", "-t", "notes", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]
        ambient = {"kind": "path", "value": str(sock)}
        self.install(
            [
                agent_pane(pane=pane, label="elsewhere", server={"kind": "default"}),
                agent_pane(pane=pane, label="ambient", server=ambient),
            ]
        )
        os.environ["TMUX"] = f"{sock},1,0"
        cfg = config()
        with (
            unittest.mock.patch.object(tsesh, "load_config", lambda: cfg),
            unittest.mock.patch.object(tsesh, "zoxide_paths", list),
        ):
            rows = {e.name: e for e in tsesh.build_entries("all")}
        self.assertEqual(rows["ambient"].here, "1")
        self.assertEqual(rows["elsewhere"].here, "")
        payload = tsesh.EntryPayload.from_fzf_row(rows["ambient"].to_fzf_row())
        old = tsesh.TmuxBackend.switch
        tsesh.TmuxBackend.switch = lambda self, name, target=None: None
        self.addCleanup(setattr, tsesh.TmuxBackend, "switch", old)
        self.assertEqual(tsesh.connect_agent(payload), 0)
        active = subprocess.run(
            [*tmux, "display-message", "-p", "-t", "notes", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(active, pane)
        # The default-server row must go through murmur, not touch this pane.
        other = tsesh.EntryPayload.from_fzf_row(rows["elsewhere"].to_fzf_row())
        tsesh.connect_agent(other)
        self.assertIn("jump j1:abc", self.calls())

    def test_unknown_identity_is_not_local(self):
        self.install([agent_pane(server={"kind": "bogus"})])
        cfg = config()
        with (
            unittest.mock.patch.object(tsesh, "load_config", lambda: cfg),
            unittest.mock.patch.object(tsesh, "zoxide_paths", list),
        ):
            rows = [e for e in tsesh.build_entries("all") if e.kind == "agent"]
        self.assertTrue(all(e.here == "" for e in rows))


class AgentEnter(FakeMurmur):
    def pick(self, entry):
        old = tsesh.run_fzf
        tsesh.run_fzf = lambda mode, query, *, capture: subprocess.CompletedProcess(
            [], 0, stdout=entry.to_fzf_row() + "\n"
        )
        self.addCleanup(setattr, tsesh, "run_fzf", old)
        return tsesh.pick_and_connect()

    def agent_entry(self, socket=None, **over):
        self.install([agent_pane(**over)])
        if socket:
            override = {"TSESH_TMUX_SOCKET_PATH": str(socket)}
            patch = unittest.mock.patch.dict(os.environ, override)
            patch.start()
            self.addCleanup(patch.stop)
        with unittest.mock.patch.object(
            tsesh.TmuxBackend, "snapshot", lambda self: {"notes": None}
        ):
            cfg = config()
            with unittest.mock.patch.object(tsesh, "load_config", lambda: cfg):
                return next(e for e in tsesh.build_entries("all") if e.kind == "agent")

    def test_other_server_goes_through_murmur_jump(self):
        entry = self.agent_entry(server={"kind": "label", "value": "private"})
        self.assertEqual(self.pick(entry), 0)
        self.assertIn("jump j1:abc", self.calls())

    def test_failed_jump_is_reported(self):
        entry = self.agent_entry(server={"kind": "label", "value": "private"})
        with unittest.mock.patch.dict(os.environ, {"FAKE_MURMUR_JUMP_RC": "1"}):
            self.assertEqual(self.pick(entry), 1)

    def test_failed_jump_stays_visible_in_a_popup(self):
        entry = self.agent_entry(server={"kind": "label", "value": "private"})
        paused, tmux_calls = [], []
        real = tsesh.tmux_cmd

        def spy(*args, **kw):
            tmux_calls.append(args)
            return real(*args, **kw) if args[0] != "display-message" else None

        env = {"FAKE_MURMUR_JUMP_RC": "1", "TMUX": "/nowhere/sock,1,0"}
        with (
            unittest.mock.patch.dict(os.environ, env),
            unittest.mock.patch.object(tsesh, "tmux_cmd", spy),
            unittest.mock.patch.object(
                tsesh, "pause_for_error", lambda: paused.append(1)
            ),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            self.assertEqual(self.pick(entry), 1)
        shown = [c for c in tmux_calls if c[0] == "display-message"]
        self.assertEqual(len(shown), 1, tmux_calls)
        self.assertIn("j1:abc", " ".join(shown[0]))
        self.assertIn("jump", err.getvalue())
        self.assertEqual(paused, [1])

    @unittest.skipUnless(shutil.which("tmux"), "needs tmux")
    def test_local_agent_selects_its_pane_then_switches(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        sock = tmp / "s"
        tmux = ["tmux", "-f", "/dev/null", "-S", str(sock)]
        subprocess.run([*tmux, "new-session", "-d", "-s", "notes"], check=True)
        subprocess.run([*tmux, "new-window", "-t", "notes:", "-n", "two"], check=True)
        subprocess.run([*tmux, "split-window", "-t", "notes:two"], check=True)
        self.addCleanup(subprocess.run, [*tmux, "kill-server"], capture_output=True)
        panes = subprocess.run(
            [*tmux, "list-panes", "-t", "notes:two", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        target = panes[0]
        subprocess.run([*tmux, "select-window", "-t", "notes:0"], check=True)
        server = {"kind": "path", "value": str(sock)}
        entry = self.agent_entry(socket=sock, pane=target, server=server)
        switched = []
        with unittest.mock.patch.object(
            tsesh.TmuxBackend,
            "switch",
            lambda self, name, target=None: switched.append((name, target)),
        ):
            self.assertEqual(self.pick(entry), 0)
        active = subprocess.run(
            [*tmux, "display-message", "-p", "-t", "notes", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(switched, [("notes", target)])
        self.assertEqual(active, target)
        self.assertFalse(any(c.startswith("jump j1:") for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
