import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from tests.helpers import CliCase, ROOT, BIN, run_cli
from zxro.localfs import m2_capabilities, providers
import zxro.localfs.durable as durable_module


class TurnBindingCliTests(CliCase):
    def setUp(self):
        super().setUp()
        self.seed()

    def create_turn(self, native=None, source=None):
        args = ["turn", "create", "--work", "job", "--agent", "pi", "--session", "coder", "--cwd", "/crew"]
        if native is not None:
            args += ["--native-session-id", native]
        if source is not None:
            args += ["--native-session-source", source]
        return self.cli(*args)

    def test_turn_bind_enriches_in_stages_and_rejects_conflicts(self):
        turn_id = self.create_turn().stdout.strip()
        with_id = self.ok_json("turn", "bind", turn_id, "--native-session-id", "native-1")
        self.assertEqual(with_id["native_session_id"], "native-1")
        self.assertNotIn("native_session_source", with_id)

        with_source = self.ok_json("turn", "bind", turn_id, "--source", "acpx.agentSessionId")
        repeated = self.ok_json(
            "turn", "bind", turn_id,
            "--native-session-id", "native-1",
            "--source", "acpx.agentSessionId",
        )
        self.assertEqual(with_source, repeated)
        self.assertEqual(with_source["native_session_source"], "acpx.agentSessionId")
        self.assertEqual(self.cli("turn", "bind", turn_id, "--native-session-id", "native-2").returncode, 4)
        self.assertEqual(self.cli("turn", "bind", turn_id, "--source", "acpx.recoverSession").returncode, 4)

    def test_turn_bind_validates_partial_binding_and_supports_settled_turns(self):
        turn_id = self.create_turn().stdout.strip()
        self.assertEqual(self.cli("turn", "bind", turn_id).returncode, 2)
        self.assertEqual(self.cli("turn", "bind", turn_id, "--source", "manual").returncode, 2)
        settled = self.cli(
            "turn", "settle", turn_id,
            "--source", "manual",
            "--status", "completed",
            "--message", "done",
        )
        self.assertEqual(settled.returncode, 0, settled.stderr)
        bound = self.ok_json(
            "turn", "bind", turn_id,
            "--native-session-id", "native-settled",
            "--source", "manual",
        )
        self.assertEqual(bound["state"], "settled")
        self.assertEqual(bound["native_session_id"], "native-settled")

    def test_turn_create_round_trips_native_identity_and_source(self):
        result = self.create_turn("native-1", "acpx.agentSessionId")
        self.assertEqual(result.returncode, 0, result.stderr)
        turn = self.ok_json("turn", "show", result.stdout.strip())
        self.assertEqual(turn["native_session_id"], "native-1")
        self.assertEqual(turn["native_session_source"], "acpx.agentSessionId")
        self.assertEqual(self.create_turn(source="manual").returncode, 2)

    def test_turn_env_outputs_exact_resume_metadata_and_shell_quotes_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home'quoted"
            self.assertEqual(run_cli(home, "watchtower", "create", "main", "--cwd", "/watchtower").returncode, 0)
            self.assertEqual(run_cli(home, "work", "create", "job", "--watchtower", "main").returncode, 0)
            created = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "coder", "--cwd", "/crew")
            self.assertEqual(created.returncode, 0, created.stderr)
            turn_id = created.stdout.strip()
            result = run_cli(home, "turn", "env", turn_id)
            self.assertEqual(result.returncode, 0, result.stderr)
            probe = subprocess.run(
                ["/bin/sh", "-c", result.stdout + "\nprintf '%s\\n' \"$ZXRO_TURN_ID\" \"$ZXRO_WORK_ID\" \"$ZXRO_WATCHTOWER_ID\" \"$ZXRO_HOME\""],
                text=True,
                capture_output=True,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.splitlines(), [turn_id, "job", "main", str(home)])
            values = run_cli(home, "--json", "turn", "env", turn_id)
            self.assertEqual(values.returncode, 0, values.stderr)
            import json
            self.assertEqual(
                json.loads(values.stdout),
                {
                    "ZXRO_HOME": str(home),
                    "ZXRO_TURN_ID": turn_id,
                    "ZXRO_WATCHTOWER_ID": "main",
                    "ZXRO_WORK_ID": "job",
                },
            )


class InspectCliTests(CliCase):
    def setUp(self):
        super().setUp()
        self.seed()

    def create_turn(self, session="coder"):
        result = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", session, "--cwd", "/crew")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def settle(self, turn_id, payload=None):
        args = [
            str(BIN), "turn", "settle", turn_id,
            "--source", "manual",
            "--status", "completed",
            "--message", "done",
        ]
        if payload is not None:
            args.append("--stdin")
        env = os.environ.copy()
        env["ZXRO_HOME"] = str(self.home)
        return subprocess.run(args, cwd=ROOT, env=env, input=payload, text=True, capture_output=True)

    def test_inspect_reports_counts_and_bytes_without_inlining_payloads(self):
        first = self.create_turn("coder-1")
        second = self.create_turn("coder-2")
        payload = "payload-body-" + "x" * 32
        first_settlement = self.settle(first, payload)
        second_settlement = self.settle(second)
        self.assertEqual((first_settlement.returncode, second_settlement.returncode), (0, 0), first_settlement.stderr or second_settlement.stderr)
        inspect = self.ok_json("inspect", "job")
        self.assertEqual(inspect["work"], {"id": "job", "state": "open", "watchtower_id": "main"})
        self.assertEqual(inspect["watchtower"], {"id": "main", "cwd": "/watchtower"})
        self.assertEqual(inspect["inbox"]["highest_generation"], 2)
        self.assertEqual(inspect["inbox"]["read_ack_generation"], 0)
        self.assertEqual(inspect["inbox"]["unread_count"], 2)
        self.assertEqual(inspect["inbox"]["pending_attention_count"], 2)
        first_summary = next(item for item in inspect["turns"] if item["id"] == first)
        second_summary = next(item for item in inspect["turns"] if item["id"] == second)
        self.assertEqual((first_summary["artifact_count"], first_summary["artifact_bytes"]), (1, len(payload.encode())))
        self.assertEqual((second_summary["artifact_count"], second_summary["artifact_bytes"]), (0, 0))
        human = self.cli("inspect", "job")
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("pending attention: 2", human.stdout)
        self.assertNotIn(payload, human.stdout)

    def test_large_artifact_history_stays_behind_metadata(self):
        turn_ids = []
        payloads = []
        for index in range(8):
            turn_id = self.create_turn(f"coder-{index}")
            payload = f"secret-{index}-" + chr(65 + index) * (32 * 1024)
            settled = self.settle(turn_id, payload)
            self.assertEqual(settled.returncode, 0, settled.stderr)
            turn_ids.append(turn_id)
            payloads.append(payload)

        baseline = {
            "inspect": self.cli("inspect", "job").stdout,
            "work_show": self.cli("--json", "work", "show", "job").stdout,
            "turn_show": self.cli("--json", "turn", "show", turn_ids[0]).stdout,
            "unread": self.cli("--json", "inbox", "unread", "--watchtower", "main").stdout,
            "pending": self.cli("--json", "inbox", "pending", "--watchtower", "main").stdout,
        }
        for payload in payloads:
            self.assertNotIn(payload[:128], "".join(baseline.values()))

        artifact = self.home / "artifacts" / f"{turn_ids[0]}--stdin.json"
        artifact.write_text(artifact.read_text() + " " * (128 * 1024))
        self.assertEqual(self.cli("inspect", "job").stdout, baseline["inspect"])
        self.assertEqual(self.cli("--json", "work", "show", "job").stdout, baseline["work_show"])
        self.assertEqual(self.cli("--json", "turn", "show", turn_ids[0]).stdout, baseline["turn_show"])
        self.assertEqual(self.cli("--json", "inbox", "unread", "--watchtower", "main").stdout, baseline["unread"])
        self.assertEqual(self.cli("--json", "inbox", "pending", "--watchtower", "main").stdout, baseline["pending"])

        registry, work, turns = providers(self.home)
        inspector = m2_capabilities(self.home, registry, work, turns)
        artifact_body_reads = []
        original = durable_module.read_json

        def counted(access, directory, filename):
            if directory == "artifacts":
                artifact_body_reads.append(filename)
            return original(access, directory, filename)

        with mock.patch.object(durable_module, "read_json", side_effect=counted):
            direct = inspector.inspect("job")
        self.assertEqual(len(direct["turns"]), 8)
        self.assertEqual(artifact_body_reads, [])

    def test_inspect_is_read_only_and_fails_closed_on_bad_metadata(self):
        turn_id = self.create_turn()
        self.assertEqual(self.settle(turn_id, "payload").returncode, 0)
        before = {
            path.relative_to(self.home): (path.stat().st_mtime_ns, path.read_bytes())
            for path in self.home.rglob("*")
            if path.is_file()
        }
        self.assertEqual(self.cli("inspect", "job").returncode, 0)
        after = {
            path.relative_to(self.home): (path.stat().st_mtime_ns, path.read_bytes())
            for path in self.home.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

        metadata = self.home / "artifact-metadata" / f"{turn_id}--stdin.json"
        metadata.write_text('{"bytes":true}\n')
        result = self.cli("inspect", "job")
        self.assertEqual(result.returncode, 5)
        self.assertEqual(result.stdout, "")


class FullLoopWalkthroughTests(CliCase):
    def test_disposable_full_loop_walkthrough(self):
        self.assertEqual(self.cli("watchtower", "create", "main", "--cwd", "/tmp/watchtower", "--agent", "pi", "--session", "watchtower").returncode, 0)
        self.assertEqual(self.cli("work", "create", "smoke", "--watchtower", "main").returncode, 0)
        created = self.cli("turn", "create", "--work", "smoke", "--agent", "claude", "--session", "coder-1", "--cwd", "/tmp/acpx-test")
        self.assertEqual(created.returncode, 0, created.stderr)
        turn_id = created.stdout.strip()

        metadata = self.cli("turn", "env", turn_id)
        probe = subprocess.run(
            ["/bin/sh", "-c", metadata.stdout + f"\ntest \"$ZXRO_TURN_ID\" = '{turn_id}' && test \"$ZXRO_WORK_ID\" = smoke"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)

        settled = self.cli("turn", "settle", turn_id, "--source", "manual", "--status", "completed", "--message", "Worker returned.")
        self.assertEqual(settled.returncode, 0, settled.stderr)
        unread = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([event["turn_id"] for event in unread], [turn_id])
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "1").returncode, 0)
        self.assertEqual(self.ok_json("inbox", "pending", "--watchtower", "main"), unread)
        self.assertEqual(self.cli("inbox", "handle", unread[0]["event_id"]).returncode, 0)
        self.assertEqual(self.ok_json("inbox", "pending", "--watchtower", "main"), [])
        inspect = self.ok_json("inspect", "smoke")
        self.assertEqual(inspect["inbox"]["unread_count"], 0)
        self.assertEqual(inspect["inbox"]["pending_attention_count"], 0)


class MissingM2ObjectsHaveNoSideEffects(CliCase):
    def test_missing_m2_objects_leave_home_absent(self):
        missing_turn = "12345678-1234-4234-8234-123456789abc"
        commands = [
            ("turn", "env", missing_turn),
            ("turn", "bind", missing_turn, "--native-session-id", "native-1"),
            ("inspect", "missing-work"),
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(self.home.exists())
                result = self.cli(*command)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.home.exists())
