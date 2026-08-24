import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
HOOK = HERE / "zxro_hook.py"
ROOT = HERE.parents[1]
REAL_ZXRO = ROOT / "bin" / "zxro"


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "calls.jsonl"
        self.fake = self.root / "fake zxro;not-shell"
        self.fake.write_text("""#!/usr/bin/env python3
import json, os, sys, time
raw = sys.stdin.buffer.read()
with open(os.environ['CALL_LOG'], 'a') as f:
    f.write(json.dumps({'argv': sys.argv[1:], 'stdin_hex': raw.hex()}) + '\\n')
mode = os.environ.get('FAKE_MODE')
if mode == 'fail':
    print('deliberate failure', file=sys.stderr); raise SystemExit(7)
if mode == 'sleep': time.sleep(2)
if mode == 'signal': os.kill(os.getpid(), 15)
""")
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        self.env = {
            **os.environ,
            "ZXRO_HOME": str(self.home),
            "ZXRO_TURN_ID": "turn;$(touch nope)\n雪",
            "ZXRO_CLI": str(self.fake),
            "CALL_LOG": str(self.log),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, event="Stop", **changes):
        value = {
            "session_id": "claude-session",
            "cwd": "/tmp/target",
            "hook_event_name": event,
            "stop_hook_active": False,
            "last_assistant_message": "done\n雪; $(touch nope)",
            "background_tasks": [],
            "session_crons": [],
        }
        if event == "StopFailure":
            value = {"session_id": "claude-session", "cwd": "/tmp/target", "hook_event_name": event, "error": "rate_limit", "error_details": "429\n雪"}
        if event == "SessionEnd":
            value = {"session_id": "claude-session", "cwd": "/tmp/target", "hook_event_name": event, "reason": "prompt_input_exit"}
        value.update(changes)
        return value

    def run_hook(self, payload, *args, env=None, raw=None):
        data = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode()
        return subprocess.run([str(HOOK), *args], input=data, capture_output=True, env={**self.env, **(env or {})})

    def calls(self):
        if not self.log.exists(): return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_official_terminal_events_map_to_one_argv_call(self):
        cases = [("Stop", "completed"), ("StopFailure", "failed"), ("SessionEnd", "cancelled")]
        for event, status in cases:
            with self.subTest(event=event):
                before = len(self.calls())
                result = self.run_hook(self.payload(event))
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.calls()[before]
                self.assertEqual(call["argv"][:3], ["turn", "settle", self.env["ZXRO_TURN_ID"]])
                self.assertEqual(call["argv"][3:7], ["--source", "claude", "--status", status])
                self.assertLessEqual(len(call["argv"][8]), 1000)
                self.assertEqual(call["stdin_hex"], "")
                self.assertFalse((self.root / "nope").exists())

    def test_payload_retention_is_explicit_and_exact(self):
        raw = json.dumps(self.payload(), ensure_ascii=False).encode()
        result = self.run_hook(None, "--retain-payload", raw=raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.calls()[0]
        self.assertEqual(call["argv"][-1], "--stdin")
        self.assertEqual(bytes.fromhex(call["stdin_hex"]), raw)
        self.assertNotIn("last_assistant_message", " ".join(call["argv"]))

    def test_nonterminal_ambiguous_and_malformed_payloads_do_not_call(self):
        bad = [
            self.payload("Notification"),
            self.payload(background_tasks=[{"id": "running"}]),
            self.payload(session_crons=[{"id": "cron"}]),
            self.payload("SessionEnd", reason="other"),
            self.payload("StopFailure", error="made_up"),
            [],
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                result = self.run_hook(payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"zxro Claude hook failed", result.stderr)
        result = self.run_hook(None, raw=b"{not json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_metadata_never_calls(self):
        for key, value in [("ZXRO_TURN_ID", ""), ("ZXRO_HOME", "relative")]:
            with self.subTest(key=key):
                result = self.run_hook(self.payload(), env={key: value})
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_cli_exit_signal_and_timeout_are_visible_failures(self):
        for mode, args in [("fail", ()), ("signal", ()), ("sleep", ("--timeout", "0.05"))]:
            with self.subTest(mode=mode):
                result = self.run_hook(self.payload(), *args, env={"FAKE_MODE": mode})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"zxro Claude hook failed", result.stderr)

    def test_size_limit_rejects_before_cli(self):
        result = self.run_hook(None, raw=b" " * (8 * 1024 * 1024))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_real_cli_retry_converges_and_payload_is_artifact_only(self):
        env = {**os.environ, "ZXRO_HOME": str(self.home)}
        def zxro(*args, input=None):
            return subprocess.run([str(REAL_ZXRO), *args], input=input, text=True, capture_output=True, env=env, cwd=ROOT)
        self.assertEqual(zxro("watchtower", "create", "main", "--cwd", "/tmp").returncode, 0)
        self.assertEqual(zxro("work", "create", "job", "--watchtower", "main").returncode, 0)
        turn = zxro("turn", "create", "--work", "job", "--agent", "claude", "--session", "crew", "--cwd", "/tmp").stdout.strip()
        hook_env = {"ZXRO_CLI": str(REAL_ZXRO), "ZXRO_TURN_ID": turn}
        raw = json.dumps(self.payload(), ensure_ascii=False).encode()
        first = self.run_hook(None, "--retain-payload", env=hook_env, raw=raw)
        retry = self.run_hook(None, "--retain-payload", env=hook_env, raw=raw)
        self.assertEqual((first.returncode, retry.returncode), (0, 0), (first.stderr, retry.stderr))
        events = json.loads(zxro("--json", "inbox", "unread", "--watchtower", "main").stdout)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["generation"], 1)
        envelope = json.dumps(event, ensure_ascii=False)
        self.assertNotIn("last_assistant_message", envelope)
        self.assertEqual(len(event["artifact_refs"]), 1)
        path = Path(zxro("artifact", "path", event["artifact_refs"][0]).stdout.strip())
        self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
