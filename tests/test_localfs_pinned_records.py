import json
import os
import queue
import socket
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError
from zxro.localfs.ioutil import (
    PinnedRecordSet,
    StoreAccess,
    atomic_create,
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

    def test_atomic_create_classifies_unsafe_existing_before_conflict(self):
        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside"
        outside.write_text("unchanged")
        cases = ("malformed", "symlink", "directory")
        for case in cases:
            with self.subTest(case=case):
                if case == "malformed":
                    target.write_text("{")
                elif case == "symlink":
                    target.symlink_to(outside)
                else:
                    target.mkdir()
                with mutation(self.home) as access:
                    with self.assertRaises(UnsafeStateError):
                        atomic_create(access, "work", "job.json", {"id": "job"})
                self.assertEqual(outside.read_text(), "unchanged")
                if target.is_symlink() or target.is_file():
                    target.unlink()
                else:
                    target.rmdir()
        self.write_record("job.json", {"id": "job"}, mode=0o600)
        with mutation(self.home) as access:
            with self.assertRaises(ConflictError):
                atomic_create(access, "work", "job.json", {"id": "job"})

    def test_injected_eexist_winners_are_pinned_and_classified(self):
        expected = {"id": "job", "state": "open"}
        target = self.home / "work" / "job.json"
        validate = lambda value: {"id": value["id"], "state": value["state"]}
        cases = (
            ("exact", expected, 0o400, None),
            ("conflict", {"id": "job", "state": "closed"}, 0o400, ConflictError),
            ("malformed", b"{", 0o400, UnsafeStateError),
            ("writable", expected, 0o600, UnsafeStateError),
        )
        for label, winner, mode, error in cases:
            with self.subTest(label=label):
                def install_winner(*args, **kwargs):
                    payload = winner if isinstance(winner, bytes) else (json.dumps(winner) + "\n").encode()
                    target.write_bytes(payload)
                    target.chmod(mode)
                    raise FileExistsError("injected winner")

                with mutation(self.home) as access, mock.patch(
                    "zxro.localfs.ioutil.os.link", side_effect=install_winner
                ):
                    if error is None:
                        with publish_json_exact_pinned(access, "work", "job.json", expected, validate=validate) as pin:
                            self.assertEqual(pin.value, expected)
                            pin.verify_current()
                    else:
                        with self.assertRaises(error):
                            with publish_json_exact_pinned(access, "work", "job.json", expected, validate=validate):
                                pass
                self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])
                target.chmod(0o600)
                target.unlink()

    def test_publication_fsync_order_and_failure_cleanup(self):
        expected = {"id": "job"}
        target = self.home / "work" / "job.json"
        order = []
        real_fsync = os.fsync

        def record_fsync(fd):
            order.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            return real_fsync(fd)

        with mutation(self.home) as access, mock.patch("zxro.localfs.ioutil.os.fsync", side_effect=record_fsync):
            with publish_json_exact_pinned(access, "work", "job.json", expected, validate=lambda value: value):
                pass
        self.assertEqual(order, ["file", "directory"])
        target.chmod(0o600)
        target.unlink()

        for failing_kind in ("file", "directory"):
            with self.subTest(failing_kind=failing_kind):
                def fail_fsync(fd):
                    kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
                    if kind == failing_kind:
                        raise OSError("injected fsync failure")
                    return real_fsync(fd)

                with mutation(self.home) as access, mock.patch("zxro.localfs.ioutil.os.fsync", side_effect=fail_fsync):
                    with self.assertRaises(UnsafeStateError):
                        with publish_json_exact_pinned(access, "work", "job.json", expected, validate=lambda value: value):
                            pass
                self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])
                if target.exists():
                    self.assertEqual(json.loads(target.read_text()), expected)
                    target.chmod(0o600)
                    target.unlink()

    def test_nonregular_records_fail_promptly_without_state_changes(self):
        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside"
        outside.write_text("unchanged")

        def assert_prompt(operation):
            results = queue.Queue()

            def run():
                try:
                    operation()
                except BaseException as exc:
                    results.put(exc)
                else:
                    results.put(None)

            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            thread.join(1)
            self.assertFalse(thread.is_alive(), "record operation blocked on a non-regular path")
            self.assertIsInstance(results.get_nowait(), UnsafeStateError)

        def open_operation():
            with mutation(self.home) as access:
                with open_json_pinned(access, "work", "job.json"):
                    pass

        def publish_operation():
            with mutation(self.home) as access:
                with publish_json_exact_pinned(
                    access, "work", "job.json", {"id": "job"}, validate=lambda value: value
                ):
                    pass

        fixtures = ["fifo"]
        if hasattr(socket, "AF_UNIX"):
            fixtures.append("socket")
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                bound_socket = None
                if fixture == "fifo":
                    os.mkfifo(target, 0o600)
                else:
                    bound_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    bound_socket.bind(str(target))
                try:
                    inode = target.lstat()
                    assert_prompt(open_operation)
                    self.assertEqual(target.lstat().st_ino, inode.st_ino)
                    assert_prompt(publish_operation)
                    self.assertEqual(target.lstat().st_ino, inode.st_ino)
                    self.assertEqual(outside.read_text(), "unchanged")
                    self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])
                finally:
                    if bound_socket is not None:
                        bound_socket.close()
                    target.unlink()

    def test_record_open_validation_failure_closes_all_new_descriptors(self):
        self.write_record("job.json", {"id": "job"}, mode=0o600)
        opened = []
        closed = []
        real_open = os.open
        real_close = os.close
        real_fstat = os.fstat
        with StoreAccess(self.home) as access:
            def track_open(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                opened.append(fd)
                return fd

            def fail_record_fstat(fd):
                info = real_fstat(fd)
                if stat.S_ISREG(info.st_mode):
                    raise OSError("injected record fstat failure")
                return info

            def track_close(fd):
                closed.append(fd)
                return real_close(fd)

            with mock.patch("zxro.localfs.ioutil.os.open", side_effect=track_open), mock.patch(
                "zxro.localfs.ioutil.os.fstat", side_effect=fail_record_fstat
            ), mock.patch("zxro.localfs.ioutil.os.close", side_effect=track_close):
                with self.assertRaises(UnsafeStateError):
                    with open_json_pinned(access, "work", "job.json"):
                        pass
        self.assertEqual(len(opened), 2)
        self.assertEqual(set(opened), set(closed))

    def test_directory_open_failure_closes_new_descriptor(self):
        opened = []
        closed = []
        real_open = os.open
        real_close = os.close
        real_fstat = os.fstat
        with StoreAccess(self.home) as access:
            def track_open(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                opened.append(fd)
                return fd

            def fail_directory_fstat(fd):
                if fd != access.home_fd:
                    raise OSError("injected fstat failure")
                return real_fstat(fd)

            def track_close(fd):
                closed.append(fd)
                return real_close(fd)

            with mock.patch("zxro.localfs.ioutil.os.open", side_effect=track_open), mock.patch(
                "zxro.localfs.ioutil.os.fstat", side_effect=fail_directory_fstat
            ), mock.patch("zxro.localfs.ioutil.os.close", side_effect=track_close):
                with self.assertRaises(UnsafeStateError):
                    with access.directory("work"):
                        pass
        self.assertEqual(len(opened), 1)
        self.assertIn(opened[0], closed)

    def test_record_set_detects_mutation_of_each_member(self):
        for changed_name in ("one.json", "two.json"):
            with self.subTest(changed_name=changed_name):
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
                                changed = first if changed_name == "one.json" else second
                                replacement = b'{"id":"ona"}\n' if changed is first else b'{"id":"twa"}\n'
                                self.rewrite_in_place(changed, replacement)
                                pins.verify_current()
                for path in (first, second):
                    path.chmod(0o600)
                    path.unlink()

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
