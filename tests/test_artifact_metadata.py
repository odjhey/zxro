import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import run_cli
from zxro.errors import UnsafeStateError
from zxro.localfs import m1_capabilities, providers
import zxro.localfs.durable as durable


class ArtifactMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        registry, work, turns = providers(self.home)
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
