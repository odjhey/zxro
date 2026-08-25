import json
import os
import subprocess
from pathlib import Path

from helpers import BIN, ROOT, CliCase
from zxro.settle import MAX_STDIN_BYTES


def payload(value):
    return value.get("data", value) if isinstance(value, dict) else value


class ArtifactPutCliTests(CliCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.turn = self.cli(
            "turn", "create", "--work", "job", "--agent", "pi",
            "--session", "crew", "--cwd", "/tmp",
        ).stdout.strip()

    def binary_cli(self, *args, body=b"", env=None):
        environment = {**os.environ, "ZXRO_HOME": str(self.home), **(env or {})}
        return subprocess.run(
            [str(BIN), *args], cwd=ROOT, env=environment, input=body,
            capture_output=True,
        )

    def put(self, kind, body=b"evidence", env=None):
        return self.binary_cli("artifact", "put", self.turn, "--kind", kind, "--stdin", body=body, env=env)

    def shown(self):
        result = self.cli("--json", "turn", "show", self.turn)
        self.assertEqual(result.returncode, 0, result.stderr)
        return payload(json.loads(result.stdout))

    def test_multiple_kinds_round_trip_and_settlement_freezes_metadata(self):
        bodies = {"review": b"review\x00body", "test-log": b"tests passed\n"}
        for kind, body in bodies.items():
            result = self.put(kind, body)
            self.assertEqual(result.returncode, 0, result.stderr)
        running = self.shown()
        listed = payload(json.loads(self.cli("--json", "turn", "list", "--work", "job").stdout))[0]
        self.assertNotIn("artifacts", listed)
        self.assertEqual(running["artifact_refs"], [f"artifact:{self.turn}:{kind}" for kind in bodies])
        self.assertEqual(
            running["artifacts"],
            [{"ref": f"artifact:{self.turn}:{kind}", "kind": kind, "bytes": len(body)} for kind, body in bodies.items()],
        )
        for kind, body in bodies.items():
            resolved = self.cli("--json", "artifact", "path", f"artifact:{self.turn}:{kind}")
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            path_record = payload(json.loads(resolved.stdout))
            self.assertEqual(Path(path_record["path"]).read_bytes(), body)
            durable = json.loads((self.home / "artifacts" / f"{self.turn}--{kind}.json").read_text())
            self.assertEqual(durable["bytes"], len(body))
            self.assertEqual(durable["sha256"], __import__("hashlib").sha256(body).hexdigest())
        settled = self.binary_cli(
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed",
            "--message", "done", "--stdin", body=b"hook payload",
        )
        self.assertEqual(settled.returncode, 0, settled.stderr)
        shown = self.shown()
        self.assertEqual([item["kind"] for item in shown["artifacts"]], ["review", "test-log", "stdin"])
        event = payload(json.loads(self.cli("--json", "inbox", "unread", "--watchtower", "main").stdout))[0]
        self.assertEqual(event["artifact_refs"], shown["artifact_refs"])
        self.assertNotIn("artifacts", event)
        self.assertEqual(self.put("late").returncode, 4)

    def test_rejections_have_no_partial_write(self):
        self.assertEqual(self.put("review", b"first").returncode, 0)
        before_turn = (self.home / "turns" / f"{self.turn}.json").read_bytes()
        before_artifact = (self.home / "artifacts" / f"{self.turn}--review.json").read_bytes()
        self.assertEqual(self.put("review", b"replacement").returncode, 4)
        self.assertEqual(self.put("stdin").returncode, 2)
        for kind in ("bad/kind", "_leading", "", "."):
            self.assertEqual(self.put(kind).returncode, 2, kind)
        unknown = self.binary_cli(
            "artifact", "put", "00000000-0000-4000-8000-000000000000",
            "--kind", "review", "--stdin", body=b"x",
        )
        self.assertEqual(unknown.returncode, 3)
        self.assertEqual((self.home / "turns" / f"{self.turn}.json").read_bytes(), before_turn)
        self.assertEqual((self.home / "artifacts" / f"{self.turn}--review.json").read_bytes(), before_artifact)
        self.assertEqual(sorted(path.name for path in (self.home / "artifacts").iterdir()), [f"{self.turn}--review.json"])

    def test_oversize_and_artifact_cap_are_atomic(self):
        oversized = self.put("large", b"x" * (MAX_STDIN_BYTES + 1))
        self.assertEqual(oversized.returncode, 2)
        self.assertFalse((self.home / "artifacts" / f"{self.turn}--large.json").exists())
        for index in range(32):
            self.assertEqual(self.put(f"k-{index}", bytes([index])).returncode, 0)
        before = self.shown()
        self.assertEqual(self.put("thirty-third").returncode, 2)
        settle = self.binary_cli(
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed",
            "--message", "done", "--stdin", body=b"payload",
        )
        self.assertEqual(settle.returncode, 2)
        self.assertEqual(self.shown(), before)
        self.assertFalse((self.home / "artifacts" / f"{self.turn}--stdin.json").exists())

    def test_artifact_commit_gap_retries_without_overwrite(self):
        crashed = self.put("review", b"same", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-commit"})
        self.assertEqual(crashed.returncode, 86)
        self.assertNotIn("artifact_refs", self.shown())
        orphan_ref = f"artifact:{self.turn}:review"
        self.assertEqual(self.cli("artifact", "path", orphan_ref).returncode, 3)
        self.assertEqual(self.put("review", b"same").returncode, 0)
        self.assertEqual(self.shown()["artifact_refs"], [f"artifact:{self.turn}:review"])

    def test_orphan_record_does_not_consume_attachment_cap(self):
        crashed = self.put("orphan", b"body", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-commit"})
        self.assertEqual(crashed.returncode, 86)
        for index in range(32):
            self.assertEqual(self.put(f"attached-{index}", b"x").returncode, 0)
        self.assertEqual(len(self.shown()["artifact_refs"]), 32)
        self.assertEqual(self.cli("artifact", "path", f"artifact:{self.turn}:orphan").returncode, 3)
        self.assertEqual(self.put("thirty-third", b"x").returncode, 2)

    def test_custom_artifact_digest_is_anchored_in_turn_metadata(self):
        self.assertEqual(self.put("review", b"original").returncode, 0)
        self.assertEqual(self.cli(
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed", "--message", "done",
        ).returncode, 0)
        record_path = self.home / "artifacts" / f"{self.turn}--review.json"
        record = json.loads(record_path.read_text())
        replacement = b"modified"
        record.update(
            bytes=len(replacement),
            sha256=__import__("hashlib").sha256(replacement).hexdigest(),
            content_hex=replacement.hex(),
        )
        record_path.write_text(json.dumps(record))
        ref = f"artifact:{self.turn}:review"
        self.assertEqual(self.cli("artifact", "path", ref).returncode, 5)
        self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)

    def test_legacy_reference_only_turn_still_enforces_cap(self):
        turn_path = self.home / "turns" / f"{self.turn}.json"
        record = json.loads(turn_path.read_text())
        record["artifact_refs"] = [f"artifact:{self.turn}:k-{index}" for index in range(33)]
        turn_path.write_text(json.dumps(record))
        shown = self.cli("turn", "show", self.turn)
        self.assertEqual(shown.returncode, 5)

    def test_settlement_stdin_metadata_commit_gap_is_resumable(self):
        settle_args = (
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed",
            "--message", "done", "--stdin",
        )
        crashed = self.binary_cli(*settle_args, body=b"hook", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-metadata-commit"})
        self.assertEqual(crashed.returncode, 86)
        running = self.shown()
        self.assertEqual(running["state"], "running")
        self.assertEqual([item["kind"] for item in running["artifacts"]], ["stdin"])
        mismatch = self.binary_cli(*settle_args, body=b"changed")
        self.assertEqual(mismatch.returncode, 4)
        retry = self.binary_cli(*settle_args, body=b"hook")
        self.assertEqual(retry.returncode, 0, retry.stderr)

        second = self.cli(
            "turn", "create", "--work", "job", "--agent", "pi",
            "--session", "crew-2", "--cwd", "/tmp",
        ).stdout.strip()
        second_args = (
            "turn", "settle", second, "--source", "manual", "--status", "completed",
            "--message", "done", "--stdin",
        )
        crashed = self.binary_cli(*second_args, body=b"second", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-metadata-commit"})
        self.assertEqual(crashed.returncode, 86)
        omitted = self.cli(
            "turn", "settle", second, "--source", "manual", "--status", "completed", "--message", "done",
        )
        self.assertEqual(omitted.returncode, 0, omitted.stderr)
        shown = payload(json.loads(self.cli("--json", "turn", "show", second).stdout))
        self.assertEqual(shown["settlement"]["payload_sha256"], __import__("hashlib").sha256(b"second").hexdigest())

    def test_settlement_wire_output_omits_artifact_metadata(self):
        self.assertEqual(self.put("review", b"review").returncode, 0)
        result = self.binary_cli(
            "--json", "turn", "settle", self.turn, "--source", "manual",
            "--status", "completed", "--message", "done", body=b"",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        wire = payload(json.loads(result.stdout))
        self.assertIn("artifact_refs", wire)
        self.assertNotIn("artifacts", wire)
        human = self.cli(
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed", "--message", "done",
        )
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertNotIn("artifacts:", human.stdout)
        shown = self.shown()
        self.assertIn("artifacts", shown)

    def test_routine_reads_do_not_inline_or_scale_with_bodies(self):
        self.assertEqual(self.put("small", b"x").returncode, 0)
        small_turn = len(self.cli("--json", "turn", "show", self.turn).stdout)
        self.assertEqual(self.put("large", b"z" * (1024 * 1024)).returncode, 0)
        large_turn = len(self.cli("--json", "turn", "show", self.turn).stdout)
        self.assertLess(large_turn - small_turn, 200)
        settle = self.cli(
            "turn", "settle", self.turn, "--source", "manual", "--status", "completed", "--message", "done",
        )
        self.assertEqual(settle.returncode, 0, settle.stderr)
        self.assertLess(len(self.cli("--json", "inbox", "unread", "--watchtower", "main").stdout), 2000)
        self.assertLess(len(self.cli("--json", "work", "show", "job").stdout), 500)
