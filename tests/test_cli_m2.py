import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest import mock

from tests.helpers import CliCase, ROOT, BIN, run_cli
from zxro.errors import UnsafeStateError
from zxro.localfs import m1_capabilities, m2_capabilities, providers
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

    def test_native_session_source_uses_bounded_provenance_grammar(self):
        turn_id = self.create_turn().stdout.strip()
        for source in ("manual source", "acpx/agent", ".manual", "a" * 65):
            with self.subTest(source=source):
                self.assertEqual(self.cli("turn", "bind", turn_id, "--source", source).returncode, 2)

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

    def test_m1_without_sidecars_uses_bounded_metadata_reads(self):
        turn_id = self.create_turn()
        payload = "legacy-payload-" + "x" * (128 * 1024)
        self.assertEqual(self.settle(turn_id, payload).returncode, 0)
        (self.home / "artifact-metadata" / f"{turn_id}--stdin.json").unlink()
        registry, work, turns = providers(self.home)
        inspector = m2_capabilities(self.home, registry, work, turns)
        original = durable_module.os.pread
        read_sizes = []

        def counted(fd, size, offset):
            read_sizes.append(size)
            return original(fd, size, offset)

        with mock.patch.object(durable_module.os, "pread", side_effect=counted):
            result = inspector.inspect("job")
        self.assertEqual(result["turns"][0]["artifact_bytes"], len(payload.encode()))
        self.assertLess(sum(read_sizes), 4096)

        calls = []
        original_json = durable_module.read_json

        def counted_json(access, directory, filename):
            if directory == "artifacts":
                calls.append(filename)
            return original_json(access, directory, filename)

        with mock.patch.object(durable_module, "read_json", side_effect=counted_json):
            inspector.inspect("job")
        self.assertEqual(calls, [])

    def test_malformed_artifact_envelopes_fail_closed_without_tracebacks(self):
        turn_id = self.create_turn()
        self.assertEqual(self.settle(turn_id, "payload").returncode, 0)
        artifact = self.home / "artifacts" / f"{turn_id}--stdin.json"
        original = artifact.read_bytes()
        artifact.write_bytes(original + b"TRAILING-NON-JSON")
        for command in (("inspect", "job"), ("inbox", "unread", "--watchtower", "main")):
            with self.subTest(command=command):
                result = self.cli(*command)
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
        artifact.write_bytes(original)
        artifact.write_bytes(original + (b" " * 2048) + b"HIDDEN-NON-JSON" + (b" " * 2048))
        result = self.cli("inspect", "job")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)
        artifact.write_bytes(original)
        artifact.write_bytes(original + (b" " * 2048) + b"\xff" + (b" " * 2048))
        result = self.cli("inspect", "job")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)
        artifact.write_bytes(original)
        invalid_utf8 = original.replace(b'"kind":"stdin"', b'"kind":"\\xffdin"')
        self.assertNotEqual(invalid_utf8, original)
        artifact.write_bytes(invalid_utf8)
        result = self.cli("inspect", "job")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

        sidecar = self.home / "artifact-metadata" / f"{turn_id}--stdin.json"
        sidecar_original = sidecar.read_bytes()
        sidecar.write_bytes(sidecar_original.replace(b'"sha256"', b'"sha\xff256"'))
        result = self.cli("inspect", "job")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_artifact_path_races_and_filesystem_errors_fail_closed(self):
        turn_id = self.create_turn()
        self.assertEqual(self.settle(turn_id, "payload").returncode, 0)
        artifact = self.home / "artifacts" / f"{turn_id}--stdin.json"
        original = artifact.read_bytes()
        registry, work, turns = providers(self.home)
        inspector = m2_capabilities(self.home, registry, work, turns)
        real_stat = durable_module.os.stat

        def replace_before_revalidation(delete=False):
            replaced = False

            def raced_stat(path, *args, **kwargs):
                nonlocal replaced
                if path == artifact.name and kwargs.get("dir_fd") is not None and not replaced:
                    replaced = True
                    if delete:
                        artifact.unlink()
                    else:
                        swap = artifact.with_name(artifact.name + ".swap")
                        swap.write_bytes(b" " * len(original))
                        os.chmod(swap, 0o600)
                        os.replace(swap, artifact)
                return real_stat(path, *args, **kwargs)

            with mock.patch.object(durable_module.os, "stat", side_effect=raced_stat):
                with self.assertRaises(UnsafeStateError):
                    inspector.inspect("job")
            self.assertTrue(replaced)
            if not artifact.exists():
                artifact.write_bytes(original)
            else:
                artifact.write_bytes(original)
            os.chmod(artifact, 0o600)

        replace_before_revalidation()
        replace_before_revalidation(delete=True)

        # A cache hit must still verify that the current pathname names the
        # identity whose metadata was cached.
        inspector.inspect("job")
        replace_before_revalidation()

        with mock.patch.object(durable_module.os, "pread", side_effect=OSError("I/O failure")):
            with self.assertRaises(UnsafeStateError):
                inspector.inspect("job")
        with mock.patch.object(durable_module.os, "stat", side_effect=OSError("stat failure")):
            with self.assertRaises(UnsafeStateError):
                inspector.inspect("job")

    def test_artifact_metadata_cache_is_bounded(self):
        turn_id = self.create_turn()
        self.assertEqual(self.settle(turn_id, "payload").returncode, 0)
        artifact = self.home / "artifacts" / f"{turn_id}--stdin.json"
        original = artifact.read_bytes()
        durable_module.LocalDurableLoop._artifact_envelope_cache.clear()
        registry, work, turns = providers(self.home)
        for _ in range(durable_module.LocalDurableLoop._ARTIFACT_CACHE_LIMIT + 8):
            artifact.write_bytes(original)
            os.chmod(artifact, 0o600)
            self.assertEqual(
                m2_capabilities(self.home, registry, work, turns).inspect("job")["turns"][0]["artifact_bytes"],
                len(b"payload"),
            )
        self.assertLessEqual(
            len(durable_module.LocalDurableLoop._artifact_envelope_cache),
            durable_module.LocalDurableLoop._ARTIFACT_CACHE_LIMIT,
        )

    def test_sidecar_and_body_metadata_mismatches_fail_closed(self):
        turn_id = self.create_turn()
        self.assertEqual(self.settle(turn_id, "payload").returncode, 0)
        sidecar = self.home / "artifact-metadata" / f"{turn_id}--stdin.json"
        artifact = self.home / "artifacts" / f"{turn_id}--stdin.json"
        original_sidecar = sidecar.read_bytes()
        value = json.loads(original_sidecar)
        value["bytes"] += 1
        sidecar.write_text(json.dumps(value))
        self.assertEqual(self.cli("inspect", "job").returncode, 5)
        sidecar.write_bytes(original_sidecar)

        original_artifact = artifact.read_bytes()
        body = json.loads(original_artifact)
        body["bytes"] += 1
        artifact.write_text(json.dumps(body))
        self.assertEqual(self.cli("inspect", "job").returncode, 5)
        artifact.write_bytes(original_artifact)
        artifact.unlink()
        self.assertEqual(self.cli("inspect", "job").returncode, 5)

    def test_inspect_uses_a_coherent_locked_snapshot(self):
        turn_id = self.create_turn()
        registry, work, turns = providers(self.home)
        inspector = m2_capabilities(self.home, registry, work, turns)
        loop = m1_capabilities(self.home, registry, turns)
        entered = threading.Event()
        release = threading.Event()
        settled = threading.Event()
        result = {}
        original_summary = inspector._artifact_summary_for_turn

        def paused_summary(access, turn, artifact_cache=None):
            entered.set()
            self.assertTrue(release.wait(5))
            return original_summary(access, turn, artifact_cache)

        def inspect():
            result["value"] = inspector.inspect("job")

        def settle():
            loop.settle(turn_id, "manual", "completed", "done", None)
            settled.set()

        with mock.patch.object(inspector, "_artifact_summary_for_turn", side_effect=paused_summary):
            inspect_thread = threading.Thread(target=inspect)
            inspect_thread.start()
            self.assertTrue(entered.wait(5))
            settle_thread = threading.Thread(target=settle)
            settle_thread.start()
            self.assertFalse(settled.wait(0.1))
            release.set()
            inspect_thread.join(5)
            settle_thread.join(5)
        self.assertFalse(inspect_thread.is_alive())
        self.assertTrue(settled.is_set())
        self.assertEqual(result["value"]["inbox"]["highest_generation"], 0)
        self.assertEqual(result["value"]["turns"][0]["state"], "running")

    def test_m1_rollback_rejects_m2_native_source_records(self):
        created = self.cli(
            "turn", "create", "--work", "job", "--agent", "pi", "--session", "native",
            "--cwd", "/crew", "--native-session-id", "native-1", "--native-session-source", "acpx.agentSessionId",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        turn_id = created.stdout.strip()
        record = json.loads((self.home / "turns" / f"{turn_id}.json").read_text())
        pre_m2_optional = {"native_session_id", "outcome", "summary", "artifact_refs", "settlement"}
        self.assertIn("native_session_source", set(record) - pre_m2_optional)

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
        cli_spec = (ROOT / "docs/v0.x/surfaces/cli.md").read_text()
        section = cli_spec.split("## Manual full-loop example\n", 1)[1]
        script = re.search(r"```sh\n(.*?)\n```", section, re.DOTALL).group(1)
        result = subprocess.run(
            ["/bin/sh", "-eu", "-c", script],
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pending attention: 0", result.stdout)


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
