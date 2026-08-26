import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from tests.helpers import BIN, ROOT, CliCase
from zxro.errors import UnsafeStateError
from zxro.localfs import providers
from zxro.settle import MAX_STDIN_BYTES


class WorkBriefCliTests(CliCase):
    def setUp(self):
        super().setUp()
        self.cli("watchtower", "create", "main", "--cwd", "/wt")

    def binary(self, *args, body=b"", env=None):
        return subprocess.run(
            [str(BIN), *args], cwd=ROOT, input=body, capture_output=True,
            env={**os.environ, "ZXRO_HOME": str(self.home), **(env or {})},
        )

    def show(self, work_id="job"):
        return self.ok_json("work", "show", work_id)

    def test_create_show_path_close_restart_and_no_body_leak(self):
        body = b"original request\x00\n"
        created = self.binary("--json", "work", "create", "job", "--watchtower", "main", "--brief-stdin", body=body)
        self.assertEqual(created.returncode, 0, created.stderr)
        public = json.loads(created.stdout)["data"]
        self.assertEqual(public["brief"], {"ref": "artifact:work:job:brief", "bytes": len(body)})
        self.assertNotIn(body.decode(errors="ignore"), created.stdout.decode())
        resolved = self.cli("--json", "work", "brief", "path", "job")
        path = Path(json.loads(resolved.stdout)["data"]["path"])
        self.assertEqual(path.read_bytes(), body)
        self.assertEqual(self.cli("work", "close", "job").returncode, 0)
        self.assertEqual(self.show()["brief"], public["brief"])
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 0)

    def test_large_brief_keeps_show_bounded_and_module_matches_bin(self):
        body = b"z" * (1024 * 1024)
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=body).returncode, 0)
        binary_show = self.binary("--json", "work", "show", "job")
        module_show = subprocess.run(
            [os.environ.get("PYTHON", "python3"), "-m", "zxro", "--json", "work", "show", "job"],
            cwd=ROOT, capture_output=True, env={**os.environ, "ZXRO_HOME": str(self.home)},
        )
        self.assertEqual(module_show.returncode, 0, module_show.stderr)
        self.assertEqual(module_show.stdout, binary_show.stdout)
        self.assertLess(len(binary_show.stdout), 300)
        self.assertNotIn(b"z" * 100, binary_show.stdout)

    def test_set_once_open_only_and_absent_omission(self):
        self.assertEqual(self.cli("work", "create", "job", "--watchtower", "main").returncode, 0)
        self.assertNotIn("brief", self.show())
        self.assertEqual(self.binary("work", "brief", "set", "job", "--stdin", body=b"first").returncode, 0)
        before = (self.home / "work" / "job.json").read_bytes()
        self.assertEqual(self.binary("work", "brief", "set", "job", "--stdin", body=b"first").returncode, 4)
        self.assertEqual((self.home / "work" / "job.json").read_bytes(), before)
        self.cli("work", "create", "closed", "--watchtower", "main")
        self.cli("work", "close", "closed")
        self.assertEqual(self.binary("work", "brief", "set", "closed", "--stdin", body=b"x").returncode, 4)
        self.assertEqual(self.cli("work", "brief", "path", "closed").returncode, 3)

    def test_oversize_and_failed_create_leave_no_work(self):
        result = self.binary("work", "create", "large", "--watchtower", "main", "--brief-stdin", body=b"x" * (MAX_STDIN_BYTES + 1))
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.home / "work" / "large.json").exists())
        self.assertFalse((self.home / "artifacts" / "work--large--brief.json").exists())
        missing = self.binary("work", "create", "orphan", "--watchtower", "missing", "--brief-stdin", body=b"x")
        self.assertEqual(missing.returncode, 3)
        self.assertFalse((self.home / "work" / "orphan.json").exists())

    def test_work_record_write_exception_reconciles_exact_commit(self):
        _, work, _ = providers(self.home)
        real_create = __import__("zxro.localfs.work", fromlist=["atomic_create"]).atomic_create

        def commit_then_fail(*args, **kwargs):
            result = real_create(*args, **kwargs)
            if args[1] == "work":
                raise OSError("post-commit failure")
            return result

        with mock.patch("zxro.localfs.work.atomic_create", side_effect=commit_then_fail):
            created = work.create("job", "main", brief=b"same")
        self.assertEqual(created.brief.bytes, 4)
        self.assertEqual(providers(self.home)[1].get("job"), created)

    def test_work_record_write_failure_keeps_orphan_invisible_and_retry_safe(self):
        _, work, _ = providers(self.home)
        real_create = __import__("zxro.localfs.work", fromlist=["atomic_create"]).atomic_create

        def fail_work_write(*args, **kwargs):
            if args[1] == "work":
                raise OSError("pre-commit failure")
            return real_create(*args, **kwargs)

        with mock.patch("zxro.localfs.work.atomic_create", side_effect=fail_work_write):
            with self.assertRaises(UnsafeStateError):
                work.create("job", "main", brief=b"same")
        self.assertFalse((self.home / "work" / "job.json").exists())
        self.assertEqual(self.cli("work", "show", "job").returncode, 3)
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"same").returncode, 0)

    def test_uncertain_write_does_not_accept_mismatched_durable_record(self):
        _, work, _ = providers(self.home)
        target = self.home / "work" / "job.json"

        real_create = __import__("zxro.localfs.work", fromlist=["atomic_create"]).atomic_create

        def install_mismatch(*args, **kwargs):
            if args[1] != "work":
                return real_create(*args, **kwargs)
            target.write_text('{"id":"job","state":"open","watchtower_id":"other"}\n')
            raise OSError("uncertain write")

        with mock.patch("zxro.localfs.work.atomic_create", side_effect=install_mismatch):
            with self.assertRaises(UnsafeStateError):
                work.create("job", "main", brief=b"same")
        self.assertEqual(json.loads(target.read_text())["watchtower_id"], "other")

    def test_set_brief_reconciles_post_commit_exception(self):
        self.assertEqual(self.cli("work", "create", "job", "--watchtower", "main").returncode, 0)
        _, work, _ = providers(self.home)
        real_replace = __import__("zxro.localfs.work", fromlist=["atomic_replace"]).atomic_replace

        def commit_then_fail(*args, **kwargs):
            real_replace(*args, **kwargs)
            raise OSError("post-commit failure")

        with mock.patch("zxro.localfs.work.atomic_replace", side_effect=commit_then_fail):
            updated = work.set_brief("job", b"body")
        self.assertEqual(updated.brief.bytes, 4)
        self.assertEqual(providers(self.home)[1].get("job"), updated)

    def test_crash_orphan_is_invisible_and_same_retry_converges(self):
        crashed = self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"same", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-commit"})
        self.assertEqual(crashed.returncode, 86)
        self.assertFalse((self.home / "work" / "job.json").exists())
        self.assertEqual(self.cli("work", "show", "job").returncode, 3)
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 3)
        retried = self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"same")
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(self.show()["brief"]["bytes"], 4)

    def test_different_retry_conflicts_without_mutation(self):
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"same", env={"ZXRO_FAULT_EXIT_AFTER": "artifact-commit"}).returncode, 86)
        before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        retry = self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"different")
        self.assertEqual(retry.returncode, 4)
        self.assertEqual({p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}, before)

    def test_turn_settlement_metadata_and_brief_integrate(self):
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"brief").returncode, 0)
        self.assertEqual(self.cli("work", "meta", "set", "job", "tracker", "--stdin", input_text='{"issue":39}').returncode, 0)
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/tmp").stdout.strip()
        self.assertEqual(self.cli("artifact", "put", turn, "--kind", "review", "--stdin", input_text="evidence").returncode, 0)
        self.assertEqual(self.cli("turn", "settle", turn, "--source", "test", "--status", "completed", "--message", "done", "--verdict", "done").returncode, 0)
        shown = self.show()
        self.assertEqual(shown["metadata"], {"tracker": {"issue": 39}})
        self.assertEqual(shown["brief"], {"ref": "artifact:work:job:brief", "bytes": 5})

    def test_concurrent_set_has_one_attachment(self):
        self.cli("work", "create", "job", "--watchtower", "main")
        def set_value(value):
            return self.binary("work", "brief", "set", "job", "--stdin", body=value).returncode
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(set_value, [b"same"] * 8))
        self.assertEqual(results.count(0), 1)
        self.assertEqual(results.count(4), 7)
        self.assertEqual(self.show()["brief"]["bytes"], 4)

    def test_malformed_ownership_digest_and_materialized_path_fail_closed(self):
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"body").returncode, 0)
        artifact_path = self.home / "artifacts" / "work--job--brief.json"
        original = json.loads(artifact_path.read_text())
        for update in ({"work_id": "other"}, {"sha256": "0" * 64}, {"bytes": 99}, {"future": True}):
            record = {**original, **update}
            artifact_path.write_text(json.dumps(record))
            self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 5)
        artifact_path.write_text(json.dumps(original))
        materialized = self.home / "artifacts" / "work--job--brief.bin"
        materialized.symlink_to("/tmp")
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 5)
        materialized.unlink()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"body")
        outside.chmod(0o400)
        os.link(outside, materialized)
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 5)
        materialized.unlink()
        materialized.write_bytes(b"body" + b"x" * (2 * 1024 * 1024))
        materialized.chmod(0o400)
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 5)

    def test_routine_show_does_not_read_brief_body_record(self):
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"body").returncode, 0)
        _, work, _ = providers(self.home)
        with mock.patch.object(work, "_brief_record", side_effect=AssertionError("body record read")):
            shown = work.get("job")
        self.assertEqual(shown.brief.bytes, 4)
        self.assertEqual(self.show()["brief"]["bytes"], 4)

    def test_durable_work_schema_is_strict_and_digest_is_anchored(self):
        self.assertEqual(self.binary("work", "create", "job", "--watchtower", "main", "--brief-stdin", body=b"body").returncode, 0)
        work_path = self.home / "work" / "job.json"
        record = json.loads(work_path.read_text())
        record["brief"]["sha256"] = hashlib.sha256(b"other").hexdigest()
        work_path.write_text(json.dumps(record))
        self.assertEqual(self.cli("work", "brief", "path", "job").returncode, 5)
