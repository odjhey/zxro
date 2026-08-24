import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout
from io import StringIO

from helpers import run_cli
from zxro.cli import parser, run
from zxro.errors import UnsafeStateError
from zxro.localfs import m1_capabilities, providers
import zxro.localfs.durable as durable


class ArtifactMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        registry, work, turns = providers(self.home)
        self.registry = registry
        registry.create("main", "/tmp")
        work.create("job", "main")
        self.turns = turns
        self.loop = m1_capabilities(self.home, registry, turns)

    def tearDown(self):
        self.temp.cleanup()

    def settle(self, payload=b"evidence"):
        turn = self.turns.create("job", "pi", "test", "/tmp")
        settled, event = self.loop.settle(turn.id, "test", "completed", "done", payload)
        return settled, event.artifact_refs[0]

    def test_stat_is_typed_and_does_not_read_artifact_body(self):
        turn, ref = self.settle(b"x" * 1_000_000)
        calls = []
        original = durable.read_json

        def observed(access, directory, filename):
            calls.append(directory)
            return original(access, directory, filename)

        with mock.patch.object(durable, "read_json", side_effect=observed):
            metadata = self.loop.stat(ref)
        self.assertEqual(metadata.turn_id, turn.id)
        self.assertEqual(metadata.bytes, 1_000_000)
        self.assertEqual(calls, ["artifact-metadata"])

    def test_all_artifact_consumers_dispatch_through_injected_stat_port(self):
        turn, ref = self.settle()
        backing = self.loop
        calls = []

        class InterceptedArtifacts:
            def stat(_, requested):
                calls.append(requested)
                return backing.stat(requested)

        loop = m1_capabilities(self.home, self.registry, self.turns, InterceptedArtifacts())
        loop.unread("main")
        loop.pending("main")
        loop.ack("main", 1)
        event = loop.pending("main")[0]
        loop.handle(event.event_id)
        loop.artifact_path(ref)
        next_turn = self.turns.create("job", "pi", "test", "/tmp")
        loop.settle(next_turn.id, "test", "completed", "done", b"next")
        self.assertGreaterEqual(calls.count(ref), 6)
        self.assertIn(f"artifact:{next_turn.id}:stdin", calls)

    def test_same_length_body_corruption_passes_stat_but_path_rejects_it(self):
        turn, ref = self.settle(b"evidence")
        body = self.home / "artifacts" / f"{turn.id}--stdin.json"
        value = json.loads(body.read_text())
        value["content_hex"] = b"tampered".hex()
        body.chmod(0o600); body.write_text(json.dumps(value)); body.chmod(0o400)
        self.assertEqual(self.loop.stat(ref).ref, ref)
        with self.assertRaises(UnsafeStateError):
            self.loop.artifact_path(ref)

    def test_missing_malformed_writable_and_symlink_metadata_fail_closed(self):
        turn, ref = self.settle()
        metadata = self.home / "artifact-metadata" / f"{turn.id}--stdin.json"
        metadata.unlink()
        with self.assertRaisesRegex(UnsafeStateError, "migration required"):
            self.loop.stat(ref)

        metadata.write_text("{}")
        metadata.chmod(0o400)
        with self.assertRaises(UnsafeStateError):
            self.loop.stat(ref)
        metadata.unlink(); metadata.symlink_to(self.home / "turns" / f"{turn.id}.json")
        with self.assertRaises(UnsafeStateError):
            self.loop.stat(ref)

    def test_missing_symlinked_and_writable_body_fail_closed(self):
        turn, ref = self.settle()
        body = self.home / "artifacts" / f"{turn.id}--stdin.json"
        body.chmod(0o600)
        with self.assertRaisesRegex(UnsafeStateError, "writable"):
            self.loop.stat(ref)
        body.unlink(); body.symlink_to(self.home / "turns" / f"{turn.id}.json")
        with self.assertRaises(UnsafeStateError):
            self.loop.stat(ref)

    def test_legacy_pending_failure_does_not_create_metadata_layout(self):
        turn, _ = self.settle()
        metadata = self.home / "artifact-metadata"
        for entry in metadata.iterdir():
            entry.unlink()
        metadata.rmdir()
        before = sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*"))
        result = run_cli(self.home, "inbox", "pending", "--watchtower", "main")
        self.assertEqual(result.returncode, 5)
        self.assertIn("migration required", result.stderr)
        self.assertFalse(metadata.exists())
        self.assertEqual(sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*")), before)

    def test_final_path_replacement_fails_closed(self):
        turn, ref = self.settle()
        body = self.home / "artifacts" / f"{turn.id}--stdin.json"
        replacement = self.home / "artifacts" / "replacement.json"
        replacement.write_bytes(body.read_bytes()); replacement.chmod(0o400)
        real_stat = durable.os.stat
        artifact_directory = (self.home / "artifacts").stat()
        target_calls = 0

        def replacing_stat(path, *args, **kwargs):
            nonlocal target_calls
            result = real_stat(path, *args, **kwargs)
            directory_fd = kwargs.get("dir_fd")
            in_artifacts = directory_fd is not None and os.fstat(directory_fd).st_ino == artifact_directory.st_ino
            if path == body.name and in_artifacts:
                target_calls += 1
                if target_calls == 2:
                    os.replace(replacement, body)
            return result

        with mock.patch.object(durable.os, "stat", side_effect=replacing_stat):
            with self.assertRaisesRegex(UnsafeStateError, "changed during verification"):
                self.loop.stat(ref)

    def test_legacy_migration_preserves_body_and_is_idempotent(self):
        turn, ref = self.settle()
        body = self.home / "artifacts" / f"{turn.id}--stdin.json"
        before = body.read_bytes()
        (self.home / "artifact-metadata" / f"{turn.id}--stdin.json").unlink()
        body.chmod(0o600)
        first = run_cli(self.home, "--json", "migrate", "artifact-metadata")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout), {"already_indexed": 0, "failed": 0, "migrated": 1})
        self.assertEqual(body.read_bytes(), before)
        self.assertEqual(self.loop.stat(ref).ref, ref)
        second = run_cli(self.home, "--json", "migrate", "artifact-metadata")
        self.assertEqual(json.loads(second.stdout), {"already_indexed": 1, "failed": 0, "migrated": 0})

    def test_failed_migration_reports_deterministic_partial_counts_and_refs(self):
        turns = [self.settle(payload)[0] for payload in (b"one", b"two", b"three")]
        turns.sort(key=lambda item: item.id)
        first = self.home / "artifact-metadata" / f"{turns[0].id}--stdin.json"
        first.unlink()
        for turn in turns[1:]:
            metadata = self.home / "artifact-metadata" / f"{turn.id}--stdin.json"
            value = json.loads(metadata.read_text()); value["sha256"] = "0" * 64
            metadata.chmod(0o600); metadata.write_text(json.dumps(value)); metadata.chmod(0o400)
        result = run_cli(self.home, "--json", "migrate", "artifact-metadata")
        self.assertEqual(result.returncode, 5)
        self.assertEqual(result.stdout, "")
        self.assertIn("migrated=1 already_indexed=0 failed=2", result.stderr)
        refs = ",".join(f"artifact:{turn.id}:stdin" for turn in turns[1:])
        self.assertIn(f"affected_refs={refs}", result.stderr)

    def test_migration_create_race_rereads_and_rejects_conflict_without_clobber(self):
        turn, _ = self.settle()
        path = self.home / "artifact-metadata" / f"{turn.id}--stdin.json"
        expected = json.loads(path.read_text()); path.unlink()
        conflicting = {**expected, "sha256": "0" * 64}
        original = durable.atomic_create
        injected = False
        def racing_create(access, directory, filename, value, **kwargs):
            nonlocal injected
            if not injected:
                injected = True
                path.write_text(json.dumps(conflicting)); path.chmod(0o400)
            return original(access, directory, filename, value, **kwargs)
        with mock.patch.object(durable, "atomic_create", side_effect=racing_create):
            with self.assertRaisesRegex(UnsafeStateError, "failed: migrated=0 already_indexed=0 failed=1"):
                self.loop.migrate_artifact_metadata()
        self.assertEqual(json.loads(path.read_text()), conflicting)

    def test_cli_injects_separate_migration_capability(self):
        class M1Only:
            pass
        class Migration:
            def migrate_artifact_metadata(self):
                return {"migrated": 0, "already_indexed": 0, "failed": 0}
        args = parser().parse_args(["--home", str(self.home), "--json", "migrate", "artifact-metadata"])
        output = StringIO()
        with redirect_stdout(output):
            run(args, core_factory=lambda home: (self.registry, object(), self.turns), m1_factory=lambda *args: M1Only(), migration_factory=lambda *args: Migration())
        self.assertEqual(json.loads(output.getvalue()), {"migrated": 0, "already_indexed": 0, "failed": 0})

    def test_migration_interruption_converges(self):
        first, _ = self.settle(b"one")
        second, _ = self.settle(b"two")
        for turn in (first, second):
            (self.home / "artifact-metadata" / f"{turn.id}--stdin.json").unlink()
            (self.home / "artifacts" / f"{turn.id}--stdin.json").chmod(0o600)
        crashed = run_cli(self.home, "migrate", "artifact-metadata", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-metadata-migration-write"})
        self.assertEqual(crashed.returncode, 86)
        retry = run_cli(self.home, "--json", "migrate", "artifact-metadata")
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(json.loads(retry.stdout)["already_indexed"], 1)
        self.assertEqual(json.loads(retry.stdout)["migrated"], 1)


if __name__ == "__main__":
    unittest.main()
