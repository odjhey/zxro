import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import CliCase
from zxro.errors import UnsafeStateError
from zxro.localfs import providers


class LocalFsInvariantTests(CliCase):
    def test_layout_permissions_and_records_survive_process_exit(self):
        self.seed(); turn_id = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        for name in ("watchtowers", "work", "turns"):
            path = self.home / name; self.assertTrue(path.is_dir()); self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.home / ".lock").stat().st_mode), 0o600)
        for path in self.home.glob("*/*.json"): self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(self.ok_json("turn", "show", turn_id)["session"], "s")

    def test_atomic_write_uses_fsync_replace_and_directory_fsync(self):
        registry, _, _ = providers(self.home)
        with mock.patch("zxro.localfs.ioutil.os.fsync", wraps=os.fsync) as fsync, mock.patch("zxro.localfs.ioutil.os.replace", wraps=os.replace) as replace:
            registry.create("main", "/wt")
        self.assertEqual(replace.call_count, 1); self.assertGreaterEqual(fsync.call_count, 2)
        self.assertEqual(json.loads((self.home / "watchtowers" / "main.json").read_text())["id"], "main")

    def test_every_mutation_takes_global_lock(self):
        registry, work, turn = providers(self.home)
        import fcntl
        with mock.patch("zxro.localfs.ioutil.fcntl.flock", wraps=fcntl.flock) as flock:
            registry.create("main", "/wt"); work.create("job", "main"); turn.create("job", "pi", "s", "/crew"); work.close("job")
        exclusive = [call for call in flock.call_args_list if call.args[1] == fcntl.LOCK_EX]
        self.assertEqual(len(exclusive), 4)

    def test_interrupted_replace_leaves_prior_record_and_no_temp_record(self):
        registry, _, _ = providers(self.home); original = registry.create("main", "/one")
        target = self.home / "watchtowers" / "main.json"
        from zxro.localfs.ioutil import atomic_replace, mutation
        with mock.patch("zxro.localfs.ioutil.os.replace", side_effect=OSError("stop")):
            with self.assertRaises(UnsafeStateError):
                with mutation(self.home) as access:
                    atomic_replace(access, "watchtowers", "main.json", {"id": "main", "cwd": "/two"})
        self.assertEqual(registry.get("main"), original); self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_directory_fsync_failure_leaves_complete_old_or_new_and_requires_reread(self):
        registry, _, _ = providers(self.home); registry.create("main", "/one")
        from zxro.localfs.ioutil import atomic_replace, mutation
        real_fsync = os.fsync
        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory fsync failed")
            return real_fsync(fd)
        with self.assertRaises(UnsafeStateError):
            with mutation(self.home) as access:
                with mock.patch("zxro.localfs.ioutil.os.fsync", side_effect=fail_directory_fsync):
                    atomic_replace(access, "watchtowers", "main.json", {"id": "main", "cwd": "/two"})
        reread = registry.get("main")
        self.assertIn(reread.cwd, ("/one", "/two"))
        self.assertEqual(json.loads((self.home / "watchtowers" / "main.json").read_text())["cwd"], reread.cwd)

    def test_managed_directory_swap_cannot_escape_during_write(self):
        registry, _, _ = providers(self.home); registry.create("main", "/one")
        managed = self.home / "watchtowers"; detached = self.home / "watchtowers-old"; outside = Path(self.temp.name) / "outside"; outside.mkdir()
        real_open = os.open; swapped = False
        def swap_before_temp(path, *args, **kwargs):
            nonlocal swapped
            if isinstance(path, str) and path.startswith(".zxro-tmp-") and not swapped:
                swapped = True; managed.rename(detached); managed.symlink_to(outside, target_is_directory=True)
            return real_open(path, *args, **kwargs)
        with mock.patch("zxro.localfs.ioutil.os.open", side_effect=swap_before_temp):
            with self.assertRaises(UnsafeStateError): registry.create("escaped", "/outside")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((outside / "escaped.json").exists())

    def test_managed_directory_swap_fails_closed_during_read(self):
        registry, _, _ = providers(self.home); registry.create("main", "/one")
        managed = self.home / "watchtowers"; detached = self.home / "watchtowers-old"; outside = Path(self.temp.name) / "outside"; outside.mkdir()
        (outside / "main.json").write_text('{"id":"main","cwd":"/outside"}')
        real_open = os.open; swapped = False
        def swap_before_record(path, *args, **kwargs):
            nonlocal swapped
            if path == "main.json" and not swapped:
                swapped = True; managed.rename(detached); managed.symlink_to(outside, target_is_directory=True)
            return real_open(path, *args, **kwargs)
        with mock.patch("zxro.localfs.ioutil.os.open", side_effect=swap_before_record):
            with self.assertRaises(UnsafeStateError): registry.get("main")
        self.assertEqual(json.loads((outside / "main.json").read_text())["cwd"], "/outside")

    def test_stale_temp_file_is_not_a_record(self):
        self.seed(); (self.home / "work" / ".zxro-tmp-stale").write_text("not json")
        self.assertEqual([x["id"] for x in self.ok_json("work", "list")], ["job"])

    def test_malformed_records_fail_closed_for_show_and_list(self):
        cases = ["{", "[]", '{}', '{"id":"job","watchtower_id":"main","state":7}', '{"id":"job","watchtower_id":"missing","state":"open"}']
        for content in cases:
            with self.subTest(content=content):
                self.seed(); path = self.home / "work" / "job.json"; path.write_text(content)
                self.assertEqual(self.cli("work", "show", "job").returncode, 5)
                self.assertEqual(self.cli("work", "list").returncode, 5)
                self.tearDown(); self.setUp()

    def test_record_identity_must_match_filename(self):
        self.seed(); path = self.home / "work" / "job.json"; data = json.loads(path.read_text()); data["id"] = "different"; path.write_text(json.dumps(data))
        self.assertEqual(self.cli("work", "show", "job").returncode, 5)
        self.assertEqual(self.cli("work", "list").returncode, 5)

    def test_corrupt_turn_cwd_fails_closed_with_unsafe_state_exit(self):
        self.seed(); turn_id = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        path = self.home / "turns" / f"{turn_id}.json"; data = json.loads(path.read_text()); data["cwd"] = "/crew\x01bad"; path.write_text(json.dumps(data))
        self.assertEqual(self.cli("turn", "show", turn_id).returncode, 5)
        self.assertEqual(self.cli("turn", "list").returncode, 5)

    def test_impossible_turn_owner_link_fails_closed(self):
        self.seed(); turn_id = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        path = self.home / "turns" / f"{turn_id}.json"; data = json.loads(path.read_text()); data["watchtower_id"] = "other"; path.write_text(json.dumps(data))
        self.assertEqual(self.cli("turn", "show", turn_id).returncode, 5); self.assertEqual(self.cli("turn", "list").returncode, 5)

    def test_symlinked_record_and_directory_fail_without_changing_target(self):
        self.seed(); external = Path(self.temp.name) / "external"; external.write_text('{"id":"job","watchtower_id":"main","state":"open"}')
        record = self.home / "work" / "job.json"; record.unlink(); record.symlink_to(external)
        self.assertEqual(self.cli("work", "close", "job").returncode, 5); self.assertIn('"state":"open"', external.read_text())
        record.unlink(); (self.home / "work").rmdir(); directory_target = Path(self.temp.name) / "outside"; directory_target.mkdir(); (self.home / "work").symlink_to(directory_target)
        self.assertEqual(self.cli("work", "create", "new", "--watchtower", "main").returncode, 5); self.assertEqual(list(directory_target.iterdir()), [])

    def test_every_show_rejects_symlinked_or_writable_active_home(self):
        self.seed(); turn_id = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        link = Path(self.temp.name) / "link"; link.symlink_to(self.home, target_is_directory=True)
        commands = (("watchtower", "show", "main"), ("work", "show", "job"), ("turn", "show", turn_id))
        for command in commands:
            self.assertEqual(self.cli("--home", str(link), *command).returncode, 5)
        os.chmod(self.home, 0o777)
        try:
            for command in commands:
                self.assertEqual(self.cli(*command).returncode, 5)
        finally:
            os.chmod(self.home, 0o700)

    def test_symlink_home_and_unsafe_permissions_fail_closed(self):
        target = Path(self.temp.name) / "target"; target.mkdir(); link = Path(self.temp.name) / "link"; link.symlink_to(target)
        self.assertEqual(self.cli("--home", str(link), "watchtower", "list").returncode, 5)
        self.seed(); os.chmod(self.home / "work", 0o777)
        self.assertEqual(self.cli("work", "list").returncode, 5)
