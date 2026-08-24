import json
import os
import queue
import socket
import stat
import tempfile
import threading
import unittest
from contextlib import nullcontext
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

    def test_temp_path_replacement_cannot_publish_attacker_state(self):
        outside = Path(self.temp.name) / "outside"
        outside.write_text("unchanged")
        target = self.home / "work" / "job.json"
        real_link = os.link

        def replace_temp_before_link(source, destination, **kwargs):
            os.unlink(source, dir_fd=kwargs["src_dir_fd"])
            os.symlink(outside, source, dir_fd=kwargs["src_dir_fd"])
            return real_link(source, destination, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.link", side_effect=replace_temp_before_link
        ):
            with self.assertRaises(UnsafeStateError):
                with publish_json_exact_pinned(
                    access, "work", "job.json", {"id": "job"}, validate=lambda value: value
                ):
                    pass
        self.assertTrue(target.samefile(outside))
        self.assertEqual(outside.read_text(), "unchanged")
        target.unlink()
        attacker_entries = list(target.parent.glob(".zxro-tmp-*"))
        self.assertEqual(len(attacker_entries), 1)
        self.assertTrue(attacker_entries[0].is_symlink())
        self.assertTrue(attacker_entries[0].resolve().samefile(outside))
        attacker_entries[0].unlink()

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
        target.write_text('{"id":"other"}\n')
        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError):
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

    def test_home_open_failure_closes_new_descriptor(self):
        opened = []
        closed = []
        real_open = os.open
        real_close = os.close

        def track_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd

        def track_close(fd):
            closed.append(fd)
            return real_close(fd)

        with mock.patch("zxro.localfs.ioutil.os.open", side_effect=track_open), mock.patch(
            "zxro.localfs.ioutil.os.fstat", side_effect=OSError("injected home fstat failure")
        ), mock.patch("zxro.localfs.ioutil.os.close", side_effect=track_close):
            with self.assertRaises(UnsafeStateError):
                with StoreAccess(self.home):
                    pass
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened, closed)

    def test_live_pin_rejects_active_home_swap(self):
        self.write_record("job.json", {"id": "job"}, mode=0o400)
        detached = self.home.with_name("home-old")
        with self.assertRaises(UnsafeStateError):
            with mutation(self.home) as access:
                with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                    self.home.rename(detached)
                    self.home.mkdir(mode=0o700)
                    pin.verify_current()

    def test_live_pin_rejects_home_and_directory_permission_changes(self):
        self.write_record("job.json", {"id": "job"}, mode=0o400)
        for changed in (self.home, self.home / "work"):
            with self.subTest(changed=changed):
                with mutation(self.home) as access:
                    with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                        changed.chmod(0o777)
                        try:
                            with self.assertRaises(UnsafeStateError):
                                pin.verify_current()
                        finally:
                            changed.chmod(0o700)

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
                                with self.assertRaises(UnsafeStateError):
                                    pins.verify_current()
                                unaffected = two if changed is first else one
                                unaffected.verify_current()
                                pins.verify_current()
                for path in (first, second):
                    path.chmod(0o600)
                    path.unlink()

    def test_record_sample_lookup_is_the_checkpoint(self):
        path = self.write_record("job.json", {"id": "job"})
        replacement = path.with_suffix(".new")
        replacement.write_text('{"id":"job"}\n')
        replacement.chmod(0o400)
        real_open = os.open
        real_fstat = os.fstat

        with mutation(self.home) as access:
            with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                replaced = False

                def replace_before_open(name, flags, *args, **kwargs):
                    nonlocal replaced
                    if name == "job.json" and not replaced:
                        replaced = True
                        path.rename(path.with_suffix(".original"))
                        os.replace(replacement, path)
                    return real_open(name, flags, *args, **kwargs)

                with mock.patch("zxro.localfs.ioutil.os.open", side_effect=replace_before_open):
                    with self.assertRaises(UnsafeStateError):
                        pin.verify_current()
                self.assertTrue(replaced)
                path.unlink()
                path.with_suffix(".original").rename(path)

        path.chmod(0o600)
        path.unlink()
        self.write_record("job.json", {"id": "job"})
        with mutation(self.home) as access:
            with open_json_pinned(access, "work", "job.json", readonly=True) as pin:
                moved = path.with_suffix(".sampled")
                swapped = False

                def replace_after_open(fd):
                    nonlocal swapped
                    info = real_fstat(fd)
                    if fd not in (access.home_fd, pin.directory_fd, pin.record_fd) and stat.S_ISREG(info.st_mode) and not swapped:
                        swapped = True
                        path.rename(moved)
                        self.write_record("job.json", {"id": "job"})
                    return info

                with mock.patch("zxro.localfs.ioutil.os.fstat", side_effect=replace_after_open):
                    pin.verify_current()
                self.assertTrue(swapped)
                path.chmod(0o600)
                path.unlink()
                moved.rename(path)

    def test_post_link_destination_replacement_is_indeterminate_and_not_rolled_back(self):
        target = self.home / "work" / "job.json"
        attacker = self.home / "work" / "attacker.json"
        attacker.write_text('{"id":"attacker"}\n')
        attacker.chmod(0o400)
        real_open = os.open
        replaced = False

        def replace_before_destination_open(name, flags, *args, **kwargs):
            nonlocal replaced
            if name == "job.json" and not replaced:
                replaced = True
                target.unlink()
                os.link(attacker, target)
            return real_open(name, flags, *args, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.open", side_effect=replace_before_destination_open
        ):
            with self.assertRaisesRegex(UnsafeStateError, "may have been published"):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(target.samefile(attacker))
        self.assertEqual(json.loads(attacker.read_text()), {"id": "attacker"})

    def test_exact_publication_rejects_mode_widening(self):
        target = self.home / "work" / "job.json"
        with self.assertRaisesRegex(UnsafeStateError, "may have been published"):
            with mutation(self.home) as access:
                with publish_json_exact_pinned(
                    access, "work", "job.json", {"id": "job"}, validate=lambda value: value
                ) as pin:
                    target.chmod(0o444)
                    pin.verify_current()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o444)

    def test_pre_sample_temp_replacement_preserves_unknown_name(self):
        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside-pre-sample"
        outside.write_text("untouched")
        real_open = os.open
        fired = False

        def replace_before_temp_sample(name, flags, *args, **kwargs):
            nonlocal fired
            if isinstance(name, str) and name.startswith(".zxro-tmp-") and not flags & os.O_CREAT and not fired:
                fired = True
                os.unlink(name, dir_fd=kwargs["dir_fd"])
                os.symlink(outside, name, dir_fd=kwargs["dir_fd"])
            return real_open(name, flags, *args, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.open", side_effect=replace_before_temp_sample
        ):
            with self.assertRaises(UnsafeStateError):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(fired)
        self.assertFalse(target.exists())
        entries = list(target.parent.glob(".zxro-tmp-*"))
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_symlink())
        self.assertEqual(outside.read_text(), "untouched")
        entries[0].unlink()

    def test_direct_cleanup_window_may_remove_undetected_replacements(self):
        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside-direct-window"
        outside.write_text("untouched")
        real_fsync = os.fsync
        fired = False

        def replace_during_file_fsync(fd):
            nonlocal fired
            if not stat.S_ISDIR(os.fstat(fd).st_mode) and not fired:
                fired = True
                temporary = next(target.parent.glob(".zxro-tmp-*"))
                temporary.unlink()
                temporary.symlink_to(outside)
                raise OSError("injected pre-sample fsync failure")
            return real_fsync(fd)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.fsync", side_effect=replace_during_file_fsync
        ):
            with self.assertRaisesRegex(UnsafeStateError, "cannot publish"):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(fired)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])
        self.assertEqual(outside.read_text(), "untouched")

    def test_replacement_after_matching_observation_is_admitted_unlink_window(self):
        import zxro.localfs.ioutil as ioutil

        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside-after-match"
        outside.write_text("untouched")
        real_remove = ioutil._remove_temp
        fired = False

        def replace_before_direct_unlink(directory_fd, temporary):
            nonlocal fired
            if not fired:
                fired = True
                os.unlink(temporary, dir_fd=directory_fd)
                os.symlink(outside, temporary, dir_fd=directory_fd)
            return real_remove(directory_fd, temporary)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil._remove_temp", side_effect=replace_before_direct_unlink
        ):
            with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                pass
        self.assertTrue(fired)
        self.assertEqual(json.loads(target.read_text()), {"id": "job"})
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])
        self.assertEqual(outside.read_text(), "untouched")

    def test_generic_link_failure_preserves_replaced_temp_name(self):
        target = self.home / "work" / "job.json"
        outside = Path(self.temp.name) / "outside-link-failure"
        outside.write_text("untouched")
        fired = False

        def replace_then_fail(source, destination, **kwargs):
            nonlocal fired
            fired = True
            os.unlink(source, dir_fd=kwargs["src_dir_fd"])
            os.symlink(outside, source, dir_fd=kwargs["src_dir_fd"])
            raise OSError("injected generic link failure")

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.link", side_effect=replace_then_fail
        ):
            with self.assertRaisesRegex(UnsafeStateError, "cannot publish"):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(fired)
        self.assertFalse(target.exists())
        entries = list(target.parent.glob(".zxro-tmp-*"))
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_symlink())
        self.assertEqual(outside.read_text(), "untouched")
        entries[0].unlink()

    def test_generic_link_failure_cleans_freshly_resampled_operation_temp(self):
        target = self.home / "work" / "job.json"
        fired = False

        def fail_link(*args, **kwargs):
            nonlocal fired
            fired = True
            raise OSError("injected generic link failure")

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.link", side_effect=fail_link
        ):
            with self.assertRaisesRegex(UnsafeStateError, "cannot publish"):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(fired)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_success_and_eexist_cleanup_samples_fire(self):
        target = self.home / "work" / "job.json"
        real_link = os.link
        success_fired = False

        def successful_link(*args, **kwargs):
            nonlocal success_fired
            success_fired = True
            return real_link(*args, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.link", side_effect=successful_link
        ):
            with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                pass
        self.assertTrue(success_fired)
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

        eexist_fired = False

        def existing_link(*args, **kwargs):
            nonlocal eexist_fired
            eexist_fired = True
            raise FileExistsError("injected existing winner")

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.link", side_effect=existing_link
        ):
            with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                pass
        self.assertTrue(eexist_fired)
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_post_link_open_failure_cleans_when_no_mismatch_was_observed(self):
        target = self.home / "work" / "job.json"
        real_open = os.open
        fired = False

        def fail_destination_open(name, flags, *args, **kwargs):
            nonlocal fired
            if name == "job.json" and not fired:
                fired = True
                raise OSError("injected destination open failure")
            return real_open(name, flags, *args, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil.os.open", side_effect=fail_destination_open
        ):
            with self.assertRaisesRegex(UnsafeStateError, "may have been published"):
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertTrue(fired)
        self.assertEqual(json.loads(target.read_text()), {"id": "job"})
        self.assertEqual(list(target.parent.glob(".zxro-tmp-*")), [])

    def test_operation_created_body_and_common_reread_use_one_stable_boundary(self):
        import zxro.localfs.ioutil as ioutil

        target = self.home / "work" / "job.json"
        label = self.home / "work" / "job.json"
        prefix = f"state record may have been published: {label}"
        body_error = RuntimeError("body marker")
        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError) as caught:
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    raise body_error
        self.assertEqual(str(caught.exception), prefix)
        self.assertIs(caught.exception.__cause__, body_error)
        self.assertEqual(json.loads(target.read_text()), {"id": "job"})
        target.chmod(0o600)
        target.unlink()

        real_read = ioutil._read_bounded
        calls = 0
        marker = OSError("common reread marker")

        def fail_common_reread(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise marker
            return real_read(*args, **kwargs)

        with mutation(self.home) as access, mock.patch(
            "zxro.localfs.ioutil._read_bounded", side_effect=fail_common_reread
        ):
            with self.assertRaises(UnsafeStateError) as caught:
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    pass
        self.assertEqual(calls, 3)
        self.assertEqual(str(caught.exception), prefix)
        self.assertIs(caught.exception.__cause__, marker)
        self.assertEqual(json.loads(target.read_text()), {"id": "job"})

    def test_post_link_low_level_causes_are_direct_and_directory_exit_is_enclosed(self):
        import zxro.localfs.ioutil as ioutil

        target = self.home / "work" / "job.json"
        prefix = f"state record may have been published: {target}"
        real_open = os.open
        real_read = os.read
        real_fsync = os.fsync
        for case in ("open", "read", "fsync"):
            with self.subTest(case=case):
                if target.exists():
                    target.chmod(0o600)
                    target.unlink()
                marker = OSError(f"{case} low-level marker")
                linked = False
                fired = False
                real_link = os.link

                def link(*args, **kwargs):
                    nonlocal linked
                    result = real_link(*args, **kwargs)
                    linked = True
                    return result

                def opened(name, flags, *args, **kwargs):
                    nonlocal fired
                    if case == "open" and linked and name == "job.json" and not fired:
                        fired = True
                        raise marker
                    return real_open(name, flags, *args, **kwargs)

                def read(fd, size):
                    nonlocal fired
                    if case == "read" and linked and not fired:
                        fired = True
                        raise marker
                    return real_read(fd, size)

                def fsync(fd):
                    nonlocal fired
                    if case == "fsync" and linked and stat.S_ISDIR(os.fstat(fd).st_mode) and not fired:
                        fired = True
                        raise marker
                    return real_fsync(fd)

                with mutation(self.home) as access, mock.patch("zxro.localfs.ioutil.os.link", side_effect=link), mock.patch(
                    "zxro.localfs.ioutil.os.open", side_effect=opened
                ), mock.patch("zxro.localfs.ioutil.os.read", side_effect=read), mock.patch(
                    "zxro.localfs.ioutil.os.fsync", side_effect=fsync
                ):
                    with self.assertRaises(UnsafeStateError) as caught:
                        with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                            pass
                self.assertTrue(fired)
                self.assertEqual(str(caught.exception), prefix)
                self.assertIs(caught.exception.__cause__, marker)
                self.assertEqual(json.loads(target.read_text()), {"id": "job"})
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o400)

        target.chmod(0o600)
        target.unlink()
        marker = OSError("directory exit marker")
        fired = False
        with mutation(self.home) as access:
            real_verify = access.verify_directory

            def fail_directory_exit(*args, **kwargs):
                nonlocal fired
                fired = True
                raise UnsafeStateError("directory exit normalized") from marker

            with mock.patch.object(access, "verify_directory", side_effect=fail_directory_exit):
                with self.assertRaises(UnsafeStateError) as caught:
                    with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                        pass
        self.assertTrue(fired)
        self.assertEqual(str(caught.exception), prefix)
        self.assertIs(caught.exception.__cause__, marker)
        self.assertEqual(json.loads(target.read_text()), {"id": "job"})

    def test_post_link_metadata_identity_and_initial_checkpoint_are_enclosed(self):
        import zxro.localfs.ioutil as ioutil

        target = self.home / "work" / "job.json"
        prefix = f"state record may have been published: {target}"
        for case in ("metadata", "identity", "checkpoint"):
            with self.subTest(case=case):
                if target.exists():
                    target.chmod(0o600)
                    target.unlink()
                marker = RuntimeError(f"{case} marker")
                linked = False
                fired = False
                real_link = os.link
                real_check = ioutil._check_record_fd
                real_identity = ioutil._check_record_identity
                real_verify = ioutil.PinnedRecord.verify_current

                def link(*args, **kwargs):
                    nonlocal linked
                    result = real_link(*args, **kwargs)
                    linked = True
                    return result

                def check(*args, **kwargs):
                    nonlocal fired
                    if case == "metadata" and linked and not fired:
                        fired = True
                        raise marker
                    return real_check(*args, **kwargs)

                def identity(*args, **kwargs):
                    nonlocal fired
                    if case == "identity" and linked and not fired:
                        fired = True
                        raise marker
                    return real_identity(*args, **kwargs)

                def verify(*args, **kwargs):
                    nonlocal fired
                    if case == "checkpoint" and linked and not fired:
                        fired = True
                        raise marker
                    return real_verify(*args, **kwargs)

                with mutation(self.home) as access, mock.patch("zxro.localfs.ioutil.os.link", side_effect=link), mock.patch(
                    "zxro.localfs.ioutil._check_record_fd", side_effect=check
                ), mock.patch("zxro.localfs.ioutil._check_record_identity", side_effect=identity), mock.patch.object(
                    ioutil.PinnedRecord, "verify_current", side_effect=verify, autospec=True
                ):
                    with self.assertRaises(UnsafeStateError) as caught:
                        with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                            pass
                self.assertTrue(fired)
                self.assertEqual(str(caught.exception), prefix)
                self.assertIs(caught.exception.__cause__, marker)
                self.assertEqual(json.loads(target.read_text()), {"id": "job"})

    def test_post_link_parse_validator_and_mismatch_use_stable_boundary(self):
        target = self.home / "work" / "job.json"
        prefix = f"state record may have been published: {target}"
        cases = ("parse", "validator", "mismatch")
        for case in cases:
            with self.subTest(case=case):
                if target.exists():
                    target.chmod(0o600)
                    target.unlink()
                marker = ValueError(f"{case} marker")
                calls = 0

                def validator(value):
                    nonlocal calls
                    calls += 1
                    if case == "validator" and calls == 2:
                        raise marker
                    if case == "mismatch" and calls == 2:
                        return {"id": "different"}
                    return value

                patcher = mock.patch("zxro.localfs.ioutil._parse_object", side_effect=marker) if case == "parse" else nullcontext()
                with mutation(self.home) as access, patcher:
                    with self.assertRaises(UnsafeStateError) as caught:
                        with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=validator):
                            pass
                self.assertEqual(str(caught.exception), prefix)
                if case in ("parse", "validator"):
                    self.assertIs(caught.exception.__cause__, marker)
                else:
                    self.assertIsInstance(caught.exception.__cause__, UnsafeStateError)
                self.assertEqual(json.loads(target.read_text()), {"id": "job"})

    def test_eexist_body_and_exit_errors_are_not_indeterminate(self):
        target = self.write_record("job.json", {"id": "job"})
        body_error = RuntimeError("existing body marker")
        with mutation(self.home) as access:
            with self.assertRaises(RuntimeError) as caught:
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    raise body_error
        self.assertIs(caught.exception, body_error)

        with mutation(self.home) as access:
            with self.assertRaises(UnsafeStateError) as caught:
                with publish_json_exact_pinned(access, "work", "job.json", {"id": "job"}, validate=lambda value: value):
                    target.chmod(0o444)
        self.assertNotIn("may have been published", str(caught.exception))

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
