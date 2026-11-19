"""The agents view, driven through bin/tsesh with a fake murmur, a PATH fzf
shim and isolated tmux servers. Never the user's tmux server or murmur."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import support
from test_tsesh import FAKE_MURMUR, TSESH, agent_pane, tsesh

ROOT = TSESH.parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")
G = tsesh.STATE_GLYPH
S = tsesh.AgentState


def plain(text: str) -> str:
    return ANSI.sub("", text)


@support.live("tmux")
class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        shim = bindir / "fzf"
        shim.write_text(
            f'#!/bin/sh\nexec {sys.executable} {ROOT / "tests" / "fzf_shim.py"} "$@"\n'
        )
        shim.chmod(0o755)
        self.murmur = self.tmp / "murmur"
        self.murmur.write_text(FAKE_MURMUR)
        self.murmur.chmod(0o755)
        self.sock = self.tmp / "s"
        self.tmux("new-session", "-d", "-s", "notes")
        self.addCleanup(self.kill)
        self.pane = self.tmux("list-panes", "-t", "notes", "-F", "#{pane_id}").split()[
            0
        ]
        base = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("TMUX", "TSESH_", "FZF_", "FAKE_MURMUR"))
        }
        self.env = {
            **base,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "TSESH_CONFIG": str(self.tmp / "no-config.toml"),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "_ZO_DATA_DIR": str(self.tmp / "zoxide"),
            "TSESH_MURMUR": str(self.murmur),
            "FAKE_MURMUR_LOG": str(self.tmp / "murmur.log"),
            "FAKE_MURMUR_JSON": str(self.tmp / "status.json"),
            "FZF_SHIM_LOG": str(self.tmp / "fzf.log"),
            "TSESH_MURMUR_TIMEOUT": os.environ["TSESH_MURMUR_TIMEOUT"],
        }
        self.snapshot([])

    def tmux(self, *args, sock=None):
        return subprocess.run(
            ["tmux", "-f", "/dev/null", "-S", str(sock or self.sock), *args],
            capture_output=True,
            text=True,
            check=False,
        ).stdout

    def snapshot(self, panes, peers=(), **extra):
        doc = {"counts": {}, "panes": panes, "peers": list(peers), **extra}
        Path(self.env["FAKE_MURMUR_JSON"]).write_text(json.dumps(doc))

    def own(self, **over):
        """An agent pane on the isolated server under test."""
        server = {"kind": "path", "value": str(self.sock)}
        return agent_pane(pane=self.pane, server=server, **over)

    def tsesh(self, *args, keys="", pick="", **env):
        for path in ("FZF_SHIM_LOG", "FAKE_MURMUR_LOG"):
            Path(self.env[path]).write_text("")
        full = {**self.env, "FZF_SHIM_KEYS": keys, "FZF_SHIM_PICK": pick}
        full.update({k: v for k, v in env.items() if v is not None})
        for k, v in env.items():
            if v is None:
                full.pop(k, None)
        return subprocess.run(
            [str(TSESH), *args],
            env=full,
            capture_output=True,
            text=True,
            timeout=300,  # a bound for a hung run, not a pass condition
            check=False,
        )

    def attach(self, session):
        """A real client on the server under test, from a pane of another."""
        host = self.tmp / f"host-{session}"
        self.tmux(
            "new-session",
            "-d",
            "-s",
            "h",
            f"env -u TMUX tmux -S {self.sock} attach -t {session}",
            sock=host,
        )
        self.addCleanup(self.kill, host)
        tty = self.tmux("list-panes", "-F", "#{pane_tty}", sock=host).strip()
        if support.wait_until(
            lambda: tty in self.tmux("list-clients", "-F", "#{client_name}")
        ):
            return tty
        self.fail("client did not attach")

    def kill(self, sock=None):
        support.kill_server(["tmux", "-S", str(sock or self.sock)])

    def in_tmux(self):
        return {"TMUX": f"{self.sock},1,0"}

    def steps(self):
        lines = Path(self.env["FZF_SHIM_LOG"]).read_text().splitlines()
        return [json.loads(line) for line in lines]

    def murmur_calls(self):
        return Path(self.env["FAKE_MURMUR_LOG"]).read_text().splitlines()

    @staticmethod
    def texts(rows):
        return [plain(r.split("\t")[0]) for r in rows]

    @staticmethod
    def kinds(rows):
        return [r.split("\t")[1] for r in rows]


class AgentRows(Harness):
    def test_visible_agents_in_murmur_order_and_crew_on_request(self):
        self.snapshot(
            [
                self.own(label="first", render_state="crashed"),
                self.own(label="crewmate", render_state="working", visible=False),
                self.own(label="last", render_state="done"),
            ]
        )
        out = self.tsesh("list", "--mode", "agents", **self.in_tmux())
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = out.stdout.splitlines()
        self.assertEqual(self.kinds(rows), ["agent", "agent"])
        texts = self.texts(rows)
        self.assertIn("first", texts[0])
        self.assertIn("last", texts[1])
        crew = self.tsesh("list", "--mode", "agents", "--crew", **self.in_tmux())
        texts = self.texts(crew.stdout.splitlines())
        self.assertEqual(
            [next(n for n in ("first", "crewmate", "last") if n in t) for t in texts],
            ["first", "crewmate", "last"],
        )

    def test_columns_glyph_label_stream_age_and_no_host_when_all_local(self):
        now = int(time.time() * 1000)
        self.snapshot(
            [
                self.own(
                    label="lab",
                    workstream="demo-work",
                    render_state="blocked",
                    updated_at=now - 125_000,
                ),
                self.own(label="same", workstream="same", render_state="working"),
                self.own(
                    label="plain", workstream=None, session_name="plain", visible=True
                ),
            ]
        )
        texts = self.texts(
            self.tsesh("list", "--mode", "agents", **self.in_tmux()).stdout.splitlines()
        )
        self.assertEqual(texts[0][1], G[S.blocked])
        self.assertIn("lab", texts[0])
        self.assertIn("demo-work", texts[0])
        self.assertIn("2m", texts[0])
        self.assertEqual(texts[1].count("same"), 1)  # stream equal to label: blank
        self.assertEqual(texts[2].count("plain"), 1)
        for text in texts:
            self.assertNotIn("here", text)
            self.assertNotIn("→", text)

    def test_host_column_when_any_row_is_remote(self):
        self.snapshot(
            [
                self.own(label="mine"),
                agent_pane(label="theirs", local=False, host="peer-a", pane="%7"),
            ]
        )
        texts = self.texts(
            self.tsesh("list", "--mode", "agents", **self.in_tmux()).stdout.splitlines()
        )
        self.assertIn("here", texts[0])
        self.assertIn("→ peer-a", texts[1])

    def test_header_columns_line_up_with_rows(self):
        self.snapshot([self.own(label="lab", workstream="ws", local=False)])
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        start = self.steps()[0]
        columns = plain(start["header"].splitlines()[-1])
        text = self.texts(start["rows"])[0]
        self.assertEqual(columns.index("agent"), text.index("lab"))
        self.assertEqual(columns.index("stream"), text.index("ws"))
        self.assertEqual(columns.index("host"), text.index("→"))


class AgentPicker(Harness):
    def test_prompt_counts_and_legend(self):
        self.snapshot(
            [
                self.own(render_state="crashed"),
                self.own(render_state="done"),
                self.own(render_state="done"),
            ]
        )
        out = self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        self.assertEqual(out.stderr, "")
        start = self.steps()[0]
        prompt = plain(start["prompt"])
        self.assertIn(f"{G[S.crashed]}1", prompt)
        self.assertIn(f"{G[S.done]}2", prompt)
        legend = plain(start["header"])
        for key in ("^a", "^s", "^g", "^f", "enter"):
            self.assertIn(key, legend)

    def test_ctrl_g_toggles_crew_and_the_toggle_survives_view_switches(self):
        self.snapshot(
            [
                self.own(label="human"),
                self.own(label="crewmate", visible=False, render_state="working"),
            ]
        )
        keys = "ctrl-g,ctrl-s,ctrl-a,ctrl-g,ctrl-g"
        out = self.tsesh(
            "pick-and-connect", "--mode", "agents", keys=keys, **self.in_tmux()
        )
        self.assertEqual(out.stderr, "")
        log = self.steps()
        self.assertEqual(len(log[0]["rows"]), 1)
        self.assertFalse(log[0]["prompt"].startswith("crew "))
        self.assertEqual(len(log[1]["rows"]), 2)  # ctrl-g in agents: crew on
        self.assertTrue(log[1]["prompt"].startswith("crew "))
        self.assertEqual(set(self.kinds(log[2]["rows"])), {"tmux"})  # ctrl-s
        self.assertIn("agent", self.kinds(log[3]["rows"]))  # ctrl-a: all view
        self.assertEqual(len(log[4]["rows"]), 2)  # back to agents: still crew
        self.assertEqual(self.kinds(log[4]["rows"]), ["agent", "agent"])
        self.assertEqual(len(log[5]["rows"]), 1)  # ctrl-g again: crew off
        self.assertFalse(log[5]["prompt"].startswith("crew "))

    def test_ctrl_g_from_the_all_view_opens_the_agents_view(self):
        self.snapshot([self.own(label="human", render_state="working")])
        self.tsesh("pick-and-connect", keys="ctrl-g", **self.in_tmux())
        start, after = self.steps()
        self.assertNotIn("agent", self.kinds(start["rows"]))  # working: no row
        self.assertEqual(self.kinds(after["rows"]), ["agent"])
        self.assertIn("agent", plain(after["header"].splitlines()[-1]))

    def test_enter_on_a_remote_agent_runs_murmur_jump(self):
        self.snapshot([agent_pane(local=False, host="peer-a", jump_target="j9:x")])
        out = self.tsesh(
            "pick-and-connect", "--mode", "agents", pick="agent-a", **self.in_tmux()
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("jump j9:x", self.murmur_calls())

    def test_murmur_read_once_per_view_and_cache_warmed(self):
        self.snapshot([self.own()])
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        calls = self.murmur_calls()
        self.assertEqual(calls.count("status --json --cached"), 1, calls)
        self.assertEqual(calls.count("jump --help"), 1, calls)


class CurrentMarker(Harness):
    def test_current_pane_and_session_get_the_marker(self):
        self.tmux("new-session", "-d", "-s", "other")
        self.tmux("new-session", "-d", "-s", "elsewhere")
        other_pane = self.tmux("list-panes", "-t", "other", "-F", "#{pane_id}").strip()
        client = self.attach("notes")
        self.attach("elsewhere")
        server = {"kind": "path", "value": str(self.sock)}
        self.snapshot(
            [
                self.own(label="mine"),
                agent_pane(label="theirs", pane=other_pane, server=server),
            ]
        )
        args = ("pick-and-connect", "--client", client)
        self.tsesh(*args, "--mode", "agents", **self.in_tmux())
        texts = self.texts(self.steps()[0]["rows"])
        self.assertEqual([t[0] for t in texts], ["◆", " "])
        self.tsesh(*args, "--mode", "sessions", **self.in_tmux())
        rows = {
            r.split("\t")[2]: plain(r.split("\t")[0]) for r in self.steps()[0]["rows"]
        }
        self.assertEqual(rows["notes"][0], "◆")
        self.assertEqual(rows["elsewhere"][0], tsesh.ATTACHED_MARK)
        self.assertEqual(rows["other"][0], " ")


class EmptyState(Harness):
    def test_no_agents_says_so_and_stays_open(self):
        out = self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        self.assertEqual(out.stderr, "")
        self.assertEqual(out.returncode, 0)  # esc is a clean exit
        start = self.steps()[0]
        self.assertEqual(start["rows"], [])
        self.assertIn("No agents", plain(start["header"]))
        for flag in ("--exit-0", "-0", "--select-1", "-1"):
            self.assertNotIn(flag, start["flags"])

    def test_only_crew_points_at_the_toggle(self):
        self.snapshot([self.own(visible=False), self.own(visible=False)])
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        header = plain(self.steps()[0]["header"])
        self.assertIn("No human agents (+2 crew: ctrl-g)", header)


class OutsideTmux(Harness):
    def test_no_server_is_started_and_enter_uses_murmur_jump(self):
        absent = self.tmp / "absent"
        self.snapshot([agent_pane(server={"kind": "path", "value": str(absent)})])
        out = self.tsesh(
            "pick-and-connect",
            "--mode",
            "agents",
            pick="agent-a",
            TSESH_TMUX_SOCKET_PATH=str(absent),
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(absent.exists())
        self.assertIn("jump j1:abc", self.murmur_calls())

    def test_an_agent_on_tsesh_server_still_goes_through_jump_outside_tmux(self):
        self.tmux("new-window", "-t", "notes:", "-n", "two")
        before = self.tmux("display-message", "-p", "-t", "notes", "#{pane_id}")
        self.snapshot([self.own()])
        out = self.tsesh(
            "pick-and-connect",
            "--mode",
            "agents",
            pick="agent-a",
            TSESH_TMUX_SOCKET_PATH=str(self.sock),
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("jump j1:abc", self.murmur_calls())
        after = self.tmux("display-message", "-p", "-t", "notes", "#{pane_id}")
        self.assertEqual(before, after)

    def test_inside_the_agent_server_enter_selects_the_pane(self):
        self.tmux("new-session", "-d", "-s", "other")
        client = self.attach("other")
        self.tmux("new-window", "-t", "notes:", "-n", "two")
        self.snapshot([self.own()])
        out = self.tsesh(
            "pick-and-connect",
            "--mode",
            "agents",
            "--client",
            client,
            pick="agent-a",
            **self.in_tmux(),
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse([c for c in self.murmur_calls() if c.startswith("jump j1")])
        active = self.tmux("display-message", "-p", "-t", "notes", "#{pane_id}")
        self.assertEqual(active.strip(), self.pane)
        on = self.tmux("display-message", "-p", "-t", client, "#{session_name}")
        self.assertEqual(on.strip(), "notes")


class MurmurUnavailable(Harness):
    def header(self, **env):
        out = self.tsesh(
            "pick-and-connect", "--mode", "agents", **self.in_tmux(), **env
        )
        self.assertEqual((out.returncode, out.stderr), (0, ""))  # clean exit
        start = self.steps()[0]
        self.assertEqual(start["rows"], [])
        return plain(start["header"])

    def test_missing_murmur(self):
        self.assertIn(
            "murmur not installed", self.header(TSESH_MURMUR="/nonexistent/murmur")
        )

    def test_old_murmur(self):
        self.snapshot([self.own()])
        too_old = "murmur too old for the agent view"
        self.assertIn(too_old, self.header(FAKE_MURMUR_MODE="old"))
        self.assertIn(too_old, self.header(FAKE_MURMUR_NOJUMP="1"))

    def test_malformed_snapshot(self):
        for doc in (
            {"panes": [self.own(workstream=3)]},
            {"panes": [self.own()], "peers": [{"name": 1}]},
            {"panes": [self.own()], "peers": "peer-a"},
        ):
            with self.subTest(doc=doc):
                Path(self.env["FAKE_MURMUR_JSON"]).write_text(json.dumps(doc))
                self.assertIn("murmur too old", self.header())

    def test_unencodable_strings_reject_the_whole_snapshot(self):
        self.tmux("set-option", "-t", "notes", "@murmur_session_state", "blocked")
        lone = "bad\ud800"  # a lone surrogate: valid JSON, not valid UTF-8
        cases = (
            [self.own(render_state="done"), self.own(label=lone)],
            [self.own(workstream=lone)],
            [self.own(window_name=lone)],
            [self.own(), {**self.own(), "extra": lone}],
        )
        for panes in cases:
            with self.subTest(panes=panes[-1]):
                self.snapshot(panes)
                out = self.tsesh("list", "--mode", "all", **self.in_tmux())
                self.assertEqual((out.returncode, out.stderr), (0, ""))
                rows = out.stdout.splitlines()
                self.assertNotIn("agent", self.kinds(rows))
                notes = next(r for r in rows if r.split("\t")[2] == "notes")
                self.assertIn(G[S.blocked], plain(notes))  # legacy option
                self.assertIn("murmur too old", self.header())
        self.snapshot([self.own()], peers=[{"name": lone, "needs_session": True}])
        self.assertIn("murmur too old", self.header())


class SessionNotice(Harness):
    def test_a_peer_needing_a_session_leads_the_header(self):
        peers = [
            {"name": "peer-a", "needs_session": True, "fetched_at": None},
            {"name": "peer-b", "needs_session": False, "fetched_at": None},
        ]
        self.snapshot([self.own()], peers=peers)
        for mode in ("agents", "all"):
            with self.subTest(mode=mode):
                self.tsesh("pick-and-connect", "--mode", mode, **self.in_tmux())
                first = plain(self.steps()[0]["header"].splitlines()[0])
                self.assertIn("peer-a", first)
                self.assertNotIn("peer-b", first)

    def test_notice_names_the_oldest_peer_target_and_the_command(self):
        now = int(time.time() * 1000)
        peers = [
            {
                "name": "newer",
                "target": "me@newer.invalid",
                "needs_session": True,
                "fetched_at": now - 7_200_000,
            },
            {
                "name": "build-alias",
                "target": "builder@peer.invalid",
                "needs_session": True,
                "fetched_at": None,
            },
        ]
        self.snapshot([self.own()], peers=peers)
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        first = plain(self.steps()[0]["header"].splitlines()[0])
        self.assertEqual(
            first,
            f"{G[S.blocked]} build-alias, newer: re-auth needed (last seen never)"
            " \u2014 ssh -MNf -S ~/.ssh/control/%r@%h:%p builder@peer.invalid",
        )

    def test_notice_age_and_target_fallback(self):
        now = int(time.time() * 1000)
        for fetched, seen in ((now - 5_000, "just now"), (now - 180_000, "3m")):
            with self.subTest(seen=seen):
                peer = {"name": "peer-a", "needs_session": True, "fetched_at": fetched}
                self.snapshot([self.own()], peers=[peer])
                self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
                first = plain(self.steps()[0]["header"].splitlines()[0])
                self.assertIn(f"(last seen {seen})", first)
                self.assertTrue(first.endswith(" peer-a"), first)

    def test_ill_typed_target_rejects_the_snapshot(self):
        peer = {"name": "p", "target": 7, "needs_session": True, "fetched_at": None}
        self.snapshot([self.own()], peers=[peer])
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        self.assertIn("murmur too old", plain(self.steps()[0]["header"]))

    def test_no_notice_without_a_gated_peer(self):
        self.snapshot([self.own()], peers=[{"name": "peer-a", "needs_session": False}])
        self.tsesh("pick-and-connect", "--mode", "agents", **self.in_tmux())
        self.assertNotIn("peer-a", plain(self.steps()[0]["header"]))


@support.live("tmux")
class AgentsKey(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        sock = tmp / "s"
        self.tmux = ["tmux", "-f", "/dev/null", "-S", str(sock)]
        subprocess.run([*self.tmux, "new-session", "-d", "-s", "x"], check=True)
        self.addCleanup(support.kill_server, self.tmux)
        self.env = dict(os.environ, TMUX=f"{sock},1,0")

    def bind(self, *options):
        """Set OPTIONS, source tsesh.tmux, return the prefix table."""
        for name, value in options:
            subprocess.run([*self.tmux, "set-option", "-g", name, value], check=True)
        subprocess.run(["bash", str(ROOT / "tsesh.tmux")], env=self.env, check=True)
        return subprocess.run(
            [*self.tmux, "list-keys", "-T", "prefix"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    @staticmethod
    def bound(keys, key):
        return [k for k in keys.splitlines() if re.search(rf"prefix\s+{key}\s", k)]

    def test_prefix_a_opens_the_agents_view(self):
        keys = self.bound(self.bind(), "a")
        self.assertEqual(len(keys), 1, keys)
        self.assertIn("--mode agents", keys[0])
        self.assertIn("--client", keys[0])
        self.assertIn("display-popup", keys[0])

    def test_empty_option_unbinds(self):
        keys = self.bind(("@tsesh_key_agents", ""))
        self.assertNotIn("--mode agents", keys)

    def test_empty_option_unbinds_a_key_bound_by_an_earlier_source(self):
        defaults = {"pick": "s", "agents": "a", "last": "g", "root": "T"}
        for name, key in defaults.items():
            with self.subTest(option=name):
                option = f"@tsesh_key_{name}"
                self.assertTrue(self.bound(self.bind(), key))
                self.assertFalse(self.bound(self.bind((option, "")), key))
                self.assertTrue(self.bound(self.bind((option, "z")), "z"))
                self.assertFalse(self.bound(self.bind((option, "")), "z"))
                subprocess.run([*self.tmux, "set-option", "-gu", option], check=True)

    def test_moving_a_key_frees_the_old_one(self):
        self.bind(("@tsesh_key_agents", "z"))
        keys = self.bind(("@tsesh_key_agents", "y"))
        self.assertFalse(self.bound(keys, "z"))
        self.assertIn("--mode agents", self.bound(keys, "y")[0])

    def test_a_key_the_user_rebound_is_left_alone(self):
        self.bind(("@tsesh_key_agents", "z"))
        subprocess.run(
            [*self.tmux, "bind-key", "z", "display-message", "mine"], check=True
        )
        keys = self.bind(("@tsesh_key_agents", ""))
        self.assertIn("mine", self.bound(keys, "z")[0])


@support.live("tmux", "fzf")
class RealFzf(Harness):
    """The real fzf in a pane of the isolated server, keys sent by tmux."""

    def picker(self, *args, **env):
        full = {**self.env, "PATH": os.environ["PATH"], **env}
        script = self.tmp / "picker.sh"
        exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in full.items())
        cmd = " ".join(shlex.quote(a) for a in (str(TSESH), *args))
        script.write_text(f"{exports}{cmd}\necho EXIT=$?\nsleep 60\n")
        script.chmod(0o755)
        self.tmux("new-window", "-d", "-t", "notes:", "-n", "picker", str(script))

    def screen(self, wait=0.0):
        time.sleep(wait)
        return self.tmux("capture-pane", "-p", "-t", "notes:picker")

    def wait_for(self, text):
        if screen := support.wait_until(lambda: text in (s := self.screen()) and s):
            return screen
        self.fail(f"{text!r} never appeared:\n{self.screen()}")

    def test_enter_on_the_empty_view_keeps_it_open(self):
        self.picker("pick-and-connect", "--mode", "agents")
        self.wait_for("No agents")
        self.tmux("send-keys", "-t", "notes:picker", "Enter")
        screen = self.screen(1.0)
        self.assertNotIn("EXIT=", screen)
        self.assertIn("No agents", screen)
        self.tmux("send-keys", "-t", "notes:picker", "Escape")
        self.assertIn("EXIT=0", self.wait_for("EXIT="))

    def test_inherited_fzf_options_do_not_skip_the_view(self):
        cases = (
            ("--exit-0", [], "No agents"),
            ("--select-1", [self.own(label="only-one")], "only-one"),
        )
        for opts, panes, shown in cases:
            with self.subTest(opts=opts):
                self.snapshot(panes)
                self.tmux("kill-window", "-t", "notes:picker")
                self.picker(
                    "pick-and-connect", "--mode", "agents", FZF_DEFAULT_OPTS=opts
                )
                self.wait_for(shown)
                self.assertNotIn("EXIT=", self.screen(1.0))
                self.tmux("send-keys", "-t", "notes:picker", "Escape")
                self.wait_for("EXIT=0")

    def test_enter_on_a_row_still_picks_it(self):
        self.snapshot([agent_pane(local=False, host="peer-a", jump_target="j9:x")])
        Path(self.env["FAKE_MURMUR_LOG"]).write_text("")
        self.picker("pick-and-connect", "--mode", "agents")
        self.wait_for("agent-a")
        self.tmux("send-keys", "-t", "notes:picker", "Enter")
        self.assertIn("EXIT=0", self.wait_for("EXIT="))
        self.assertIn("jump j9:x", self.murmur_calls())


if __name__ == "__main__":
    unittest.main()


@support.live("tmux")
class NamedSocketAlias(Harness):
    """A -L name is an alias too: the proof pins the socket it resolves to."""

    def test_preview_after_retargeting_a_named_socket(self):
        tmpdir = self.tmp / "tmuxdir"
        tmpdir.mkdir()
        sockdir = Path(os.path.realpath(tmpdir)) / f"tmux-{os.getuid()}"
        env = {**self.env, "TMUX_TMPDIR": str(tmpdir)}

        def server(sock, text):
            subprocess.run(
                [
                    "tmux",
                    "-f",
                    "/dev/null",
                    "-S",
                    str(sock),
                    "new-session",
                    "-d",
                    "-s",
                    "srv",
                    f"echo {text}; sleep 60",
                ],
                check=True,
            )
            self.addCleanup(self.kill, sock)
            shown = support.wait_until(  # until the pane has printed it
                lambda: text in self.tmux("capture-pane", "-p", "-t", "srv", sock=sock)
            )
            self.assertTrue(shown, f"{text} never shown")

        sockdir.mkdir(mode=0o700)
        physical_a, physical_b = self.tmp / "a-sock", self.tmp / "b-sock"
        server(physical_a, "A_CONTENT")
        server(physical_b, "B_CONTENT")
        alias = sockdir / "alias"
        alias.symlink_to(physical_a)
        self.snapshot(
            [
                agent_pane(
                    pane="%0",
                    session_name="srv",
                    server={"kind": "label", "value": "alias"},
                )
            ]
        )
        self.env = env
        out = self.tsesh("list", "--mode", "agents", TSESH_TMUX_SOCKET_NAME="alias")
        row = out.stdout.splitlines()[0].split("\t")
        fields = dict(zip(tsesh.FZF_ROW_FIELDS, row, strict=True))
        self.assertEqual(fields["here"], "1")

        def preview():
            return self.tsesh(
                "preview",
                "--kind",
                "agent",
                "--session-name",
                "srv",
                "--host",
                "box",
                "--pane",
                "%0",
                "--here",
                "1",
                "--socket",
                fields["socket"],
                TSESH_TMUX_SOCKET_NAME="alias",
            ).stdout

        self.assertIn("A_CONTENT", preview())
        alias.unlink()
        alias.symlink_to(physical_b)
        shown = preview()
        self.assertNotIn("B_CONTENT", shown)
        self.assertIn("host:", shown)


class FailureOnTheInvokingServer(Harness):
    def test_jump_failure_reaches_the_client_server_not_the_override(self):
        other = self.tmp / "other"
        self.tmux("new-session", "-d", "-s", "data", sock=other)
        self.addCleanup(self.kill, other)
        client = self.attach("notes")
        for given, target in ((client, "j2:x"), ("", "j2:y")):
            with self.subTest(client=given):
                remote = agent_pane(local=False, host="peer-a", jump_target=target)
                self.snapshot([remote])
                args = ["--client", given] if given else []
                out = self.tsesh(
                    "pick-and-connect",
                    "--mode",
                    "agents",
                    *args,
                    pick="agent-a",
                    FAKE_MURMUR_JUMP_RC="42",
                    TSESH_TMUX_SOCKET_PATH=str(other),
                    **self.in_tmux(),
                )
                self.assertEqual(out.returncode, 1)
                self.assertIn(target, out.stderr)
                here = self.tmux("show-messages")
                self.assertIn(f"murmur jump {target} failed", here)
                self.assertNotIn(target, self.tmux("show-messages", sock=other))


@support.live("tmux", "fzf")
class PluginPathQuoting(Harness):
    """tsesh.tmux sourced from a directory whose name a shell would split."""

    def source_from(self, name):
        link = self.tmp / name
        link.symlink_to(ROOT)
        for key in (
            "TSESH_MURMUR",
            "FAKE_MURMUR_LOG",
            "FAKE_MURMUR_JSON",
            "TSESH_CONFIG",
            "XDG_STATE_HOME",
            "_ZO_DATA_DIR",
        ):
            self.tmux("set-environment", "-g", key, self.env[key])
        subprocess.run(
            ["bash", str(link / "tsesh.tmux")],
            env={**os.environ, "TMUX": f"{self.sock},1,0"},
            check=True,
        )

    def wait_for_cwd(self, target, path):
        """Until the pane's shell has run the cd: shell startup time varies."""
        want = os.path.realpath(path)

        def now():
            return self.tmux("display", "-p", "-t", target, "#{pane_current_path}")

        if not support.wait_until(lambda: os.path.realpath(now().strip()) == want):
            self.fail(f"pane never reached {want}: {now()!r}")

    def host_screen(self, host):
        return self.tmux("capture-pane", "-p", "-t", "h:", sock=host)

    def test_keys_work_from_a_path_with_quote_space_and_hash(self):
        for name in ("Plugin path", "Plugin's path", "Plugin's #{path} $HOME"):
            with self.subTest(name=name):
                self.source_from(name)
                self.snapshot([self.own(label=f"agent-{len(name)}")])
                host = self.tmp / "host-notes"
                self.kill(host)
                client = self.attach("notes")
                self.tmux("send-keys", "-t", "h:", "C-b", "a", sock=host)
                label = f"agent-{len(name)}"
                if not support.wait_until(
                    lambda h=host, t=label: t in self.host_screen(h)
                ):
                    self.fail(f"no agents popup:\n{self.host_screen(host)}")
                self.tmux("send-keys", "-t", "h:", "Escape", sock=host)
                support.wait_until(lambda h=host, t=label: t not in self.host_screen(h))
                # prefix T: `connect --pane` makes a session at the pane's cwd.
                cwd = self.tmp / f"cwd{len(name)}"
                cwd.mkdir()
                self.tmux("send-keys", "-t", "notes:", f"cd {cwd}", "Enter")
                self.wait_for_cwd("notes:", cwd)
                self.tmux("send-keys", "-t", "h:", "C-b", "T", sock=host)
                made = f"cwd{len(name)}"
                if not support.wait_until(
                    lambda t=made: t in self.tmux("list-sessions")
                ):
                    self.fail(
                        "prefix T made no session: "
                        + self.tmux("list-sessions")
                        + self.tmux(
                            "display", "-p", "-t", client, "#{pane_current_path}"
                        )
                        + self.tmux("show-messages")
                    )
                self.tmux("switch-client", "-c", client, "-t", "notes")
                self.kill(host)


@support.live("tmux")
class SocketPinnedAtStart(Harness):
    """The server is resolved once, before murmur is read: a name retargeted
    during the read cannot turn a row from one server into a local action on
    another."""

    def test_named_socket_retargeted_during_the_murmur_read(self):
        tmpdir = self.tmp / "tmuxdir"
        sockdir = Path(os.path.realpath(tmpdir)) / f"tmux-{os.getuid()}"
        sockdir.mkdir(parents=True, mode=0o700)
        physical_a = self.tmp / "a-sock"
        self.tmux("new-session", "-d", "-s", "SERVER_A", sock=physical_a)
        self.addCleanup(self.kill, physical_a)
        alias = sockdir / "review"
        alias.symlink_to(physical_a)
        # self.sock is server B; its %0 is in "notes", the client sits elsewhere.
        self.tmux("new-session", "-d", "-s", "ORIGIN_B")
        client = self.attach("ORIGIN_B")
        row = agent_pane(
            pane="%0",
            session_name="SERVER_A",
            label="cache-from-A",
            jump_target="j1:on-A",
            server={"kind": "label", "value": "review"},
        )
        self.snapshot([row])
        out = self.tsesh(
            "pick-and-connect",
            "--mode",
            "agents",
            "--client",
            client,
            pick="cache-from-A",
            TMUX_TMPDIR=str(tmpdir),
            TSESH_TMUX_SOCKET_NAME="review",
            FAKE_MURMUR_ON_STATUS=f"ln -sfn {shlex.quote(str(self.sock))} "
            f"{shlex.quote(str(alias))}",
            **self.in_tmux(),
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("jump j1:on-A", self.murmur_calls())
        on = self.tmux("display-message", "-p", "-t", client, "#{session_name}")
        self.assertEqual(on.strip(), "ORIGIN_B")


@support.live("tmux")
class WindowPaths(unittest.TestCase):
    """Live rows show where the session is; its windows' dirs are its own."""

    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sock = self.tmp / "s"
        self.tmux = ["tmux", "-f", "/dev/null", "-S", str(self.sock)]
        self.addCleanup(support.kill_server, self.tmux)
        self.dirs = {}
        for name in ("root", "other", "same", "zox"):
            self.dirs[name] = self.tmp / name
            self.dirs[name].mkdir()
        bindir = self.tmp / "bin"
        bindir.mkdir()
        zoxide = bindir / "zoxide"
        listed = "\n".join(str(self.dirs[n]) for n in ("root", "other", "zox"))
        zoxide.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(listed)}\n")
        zoxide.chmod(0o755)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("TSESH_")},
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "HOME": str(self.tmp),
            "TSESH_TMUX_SOCKET_PATH": str(self.sock),
            "TSESH_CONFIG": str(self.config()),
            "TSESH_MURMUR": "/nonexistent/murmur",
            "XDG_STATE_HOME": str(self.tmp / "state"),
        }
        # proj: active window in root, two more in other; flat: one dir only.
        self.on_tmux(
            "new-session", "-d", "-s", "proj", "-c", str(self.dirs["root"]), "sleep 600"
        )
        for _ in range(2):
            self.on_tmux(
                "new-window",
                "-d",
                "-t",
                "proj:",
                "-n",
                "side",
                "-c",
                str(self.dirs["other"]),
                "sleep 600",
            )
        self.on_tmux("split-window", "-d", "-t", "proj:0", "sleep 600")
        self.on_tmux(
            "new-session", "-d", "-s", "flat", "-c", str(self.dirs["same"]), "sleep 600"
        )
        self.on_tmux(
            "new-window", "-d", "-t", "flat:", "-c", str(self.dirs["same"]), "sleep 600"
        )

    def config(self, extra=""):
        # No blacklist: every temporary directory lives under /tmp.
        cfg = self.tmp / "config.toml"
        cfg.write_text(f"blacklist = []\n{extra}")
        return cfg

    def on_tmux(self, *args):
        return subprocess.run(
            [*self.tmux, *args], capture_output=True, text=True, check=False
        ).stdout

    def tsesh(self, *args):
        return subprocess.run(
            [str(TSESH), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

    def rows(self, mode="all"):
        out = self.tsesh("list", "--mode", mode)
        self.assertEqual(out.returncode, 0, out.stderr)
        return {
            (r.split("\t")[1], r.split("\t")[2]): plain(r.split("\t")[0])
            for r in out.stdout.splitlines()
        }

    def test_live_row_shows_the_active_cwd_and_other_dirs(self):
        rows = self.rows()
        proj = rows[("tmux", "proj")]
        self.assertIn("~/root", proj)
        self.assertTrue(proj.rstrip().endswith("~/root +1"), proj)
        flat = rows[("tmux", "flat")]
        self.assertTrue(flat.rstrip().endswith("~/same"), flat)

    def test_live_rows_count_windows_and_panes_pins_not_running_do_not(self):
        self.config(f'[[sessions]]\nname = "pin"\npath = "{self.dirs["zox"]}"\n')
        rows = self.rows("sessions")
        self.assertIn(" 3w 4p ", rows[("tmux", "proj")])
        self.assertIn(" 2w 2p ", rows[("tmux", "flat")])
        self.assertNotRegex(rows[("default", "pin")], r"\dw \d+p")

    def test_zoxide_dirs_of_a_live_session_are_dropped(self):
        zoxide = [name for kind, name in self.rows() if kind == "zoxide"]
        self.assertEqual(zoxide, ["zox"])

    def test_preview_lists_every_window(self):
        out = self.tsesh("preview", "--kind", "tmux", "--session-name", "proj")
        lines = out.stdout.splitlines()
        windows = [line for line in lines if re.match(r"[* ] \d+ ", line)]
        self.assertEqual(len(windows), 3, out.stdout)
        self.assertTrue(windows[0].startswith("* 0 "), windows)
        self.assertIn("2p  ~/root", windows[0])
        self.assertIn("side  1p  ~/other", windows[1])

    def test_a_pinned_session_not_running_keeps_its_configured_path(self):
        self.config(f'[[sessions]]\nname = "pin"\npath = "{self.dirs["zox"]}"\n')
        rows = self.rows("sessions")
        self.assertTrue(rows[("default", "pin")].rstrip().endswith("~/zox"))
