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
        from zxro.localfs.ioutil import atomic_replace
        with mock.patch("zxro.localfs.ioutil.os.replace", side_effect=OSError("stop")):
            with self.assertRaises(OSError): atomic_replace(target, {"id": "main", "cwd": "/two"})
        self.assertEqual(registry.get("main"), original); self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

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

    def test_symlink_home_and_unsafe_permissions_fail_closed(self):
        target = Path(self.temp.name) / "target"; target.mkdir(); link = Path(self.temp.name) / "link"; link.symlink_to(target)
        self.assertEqual(self.cli("--home", str(link), "watchtower", "list").returncode, 5)
        self.seed(); os.chmod(self.home / "work", 0o777)
        self.assertEqual(self.cli("work", "list").returncode, 5)
