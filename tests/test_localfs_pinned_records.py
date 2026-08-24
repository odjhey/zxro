import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError
from zxro.localfs.ioutil import (
    PinnedRecordSet,
    mutation,
    open_json_pinned,
    publish_json_exact_pinned,
)


class PinnedRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        with mutation(self.home):
            pass

    def tearDown(self):
        self.temp.cleanup()

    def write_record(self, name, value, mode=0o400):
        path = self.home / "work" / name
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        path.chmod(mode)
        return path

    def test_pin_retains_descriptors_and_repeated_checkpoints(self):
        path = self.write_record("job.json", {"id": "job"})
        with mutation(self.home) as access:
            with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                self.assertEqual(pin.value, {"id": "job"})
                self.assertEqual(pin.raw, path.read_bytes())
                os.fstat(pin.directory_fd)
                os.fstat(pin.record_fd)
                pin.verify_current()
                pin.verify_current()
                record_fd = pin.record_fd
        with self.assertRaises(OSError):
            os.fstat(record_fd)

    def rewrite_in_place(self, path, content):
        path.chmod(0o600)
        fd = os.open(path, os.O_WRONLY)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, content)
        finally:
            os.close(fd)
        path.chmod(0o400)

    def test_checkpoint_rejects_path_and_content_changes(self):
        changes = {
            "replace": lambda path: (path.rename(path.with_suffix(".old")), self.write_record("job.json", {"id": "job"})),
            "delete": lambda path: path.unlink(),
            "writable": lambda path: path.chmod(0o600),
            "truncate": lambda path: self.rewrite_in_place(path, b"{}\n"),
            "same inode": lambda path: self.rewrite_in_place(path, b'{"id":"jab"}\n'),
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                path = self.write_record("job.json", {"id": "job"})
                try:
                    with mutation(self.home) as access:
                        with self.assertRaises((NotFoundError, UnsafeStateError)):
                            with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                                change(path)
                                pin.verify_current()
                finally:
                    old = path.with_suffix(".old")
                    if old.exists():
                        old.unlink()
                    if path.exists():
                        path.chmod(0o600)
                        path.unlink()

    def test_checkpoint_rejects_symlink_and_managed_directory_swap(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text('{"id":"outside"}\n')
        outside.chmod(0o400)
        path = self.write_record("job.json", {"id": "job"})
        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError):
                with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                    path.rename(path.with_suffix(".old"))
                    path.symlink_to(outside)
                    pin.verify_current()
        self.assertEqual(outside.read_text(), '{"id":"outside"}\n')

        path.unlink()
        path.with_suffix(".old").unlink()
        self.write_record("job.json", {"id": "job"})
        managed = self.home / "work"
        detached = self.home / "work-old"
        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError):
                with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                    managed.rename(detached)
                    managed.mkdir(mode=0o700)
                    pin.verify_current()

    def test_exact_publication_accepts_exact_and_rejects_unsafe_existing(self):
        expected = {"id": "job", "state": "open"}
        validate = lambda value: {"id": value["id"], "state": value["state"]}
        with mutation(self.home) as access:
            with publish_json_exact_pinned(access, "work", "job.json", expected, validate=validate) as pin:
                self.assertEqual(pin.value, expected)
                self.assertEqual(stat.S_IMODE(os.fstat(pin.record_fd).st_mode), 0o400)
        target = self.home / "work" / "job.json"
        original = target.read_bytes()
        with mutation(self.home) as access:
            with publish_json_exact_pinned(access, "work", "job.json", expected, validate=validate) as pin:
                pin.verify_current()
        self.assertEqual(target.read_bytes(), original)

        for label, content, mode, error in (
            ("different", {"id": "job", "state": "closed"}, 0o400, ConflictError),
            ("malformed", b"{", 0o400, UnsafeStateError),
            ("writable", expected, 0o600, UnsafeStateError),
        ):
            with self.subTest(label=label):
                target.chmod(0o600)
                target.unlink()
                target.write_bytes(content if isinstance(content, bytes) else (json.dumps(content) + "\n").encode())
                target.chmod(mode)
                before = target.read_bytes()
                with mutation(self.home) as access:
                    with self.assertRaises(error):
                        with publish_json_exact_pinned(access, "work", "job.json", expected, validate=validate):
                            pass
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_publication_never_overwrites_symlink_and_cleans_partial_write(self):
        outside = Path(self.temp.name) / "outside"
        outside.write_text("untouched")
        target = self.home / "work" / "job.json"
        target.symlink_to(outside)
        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertEqual(outside.read_text(), "untouched")
        target.unlink()

        with mutation(self.home) as access:
            with mock.patch("zxro.localfs.ioutil.os.write", side_effect=OSError("stop")):
                with self.assertRaises(UnsafeStateError):
                    with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                        pass
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_record_set_checks_every_live_pin(self):
        first = self.write_record("one.json", {"id": "one"})
        second = self.write_record("two.json", {"id": "two"})
        with self.assertRaises(UnsafeStateError):
            with mutation(self.home) as access:
                with open_json_pinned(access, "work", "one.json", readonly=True) as one:
                    with open_json_pinned(access, "work", "two.json", readonly=True) as two:
                        pins = PinnedRecordSet()
                        pins.add(one)
                        pins.add(two)
                        pins.verify_current()
                        self.rewrite_in_place(second, b'{"id":"twa"}\n')
                        pins.verify_current()
        first.chmod(0o600)

    @unittest.skipUnless(Path("/proc/self/fd").exists(), "requires procfs")
    def test_closed_pin_loop_does_not_leak_descriptors(self):
        self.write_record("job.json", {"id": "job"})
        before = len(list(Path("/proc/self/fd").iterdir()))
        with mutation(self.home) as access:
            for _ in range(50):
                with open_json_pinned(access, "work", "job.json", readonly=True):
                    pass
        after = len(list(Path("/proc/self/fd").iterdir()))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
