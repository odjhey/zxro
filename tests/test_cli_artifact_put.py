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
        self.assertEqual(self.put("review", b"same").returncode, 0)
        self.assertEqual(self.shown()["artifact_refs"], [f"artifact:{self.turn}:review"])

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
