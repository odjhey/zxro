import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zxro.errors import UnsafeStateError
from zxro.localfs import LocalDurableLoop, providers
import zxro.settle as settlement_module


class MailboxScalingConformance(unittest.TestCase):
    """Provider-operation budgets for bounded M1 reconciliation.

    The assertions target unread, pending, handle, and settle semantics. The
    read counter is supplied by this provider fixture; another provider can
    expose an equivalent operation counter while reusing the same cases.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.registry, self.work, self.turns = providers(self.home)
        self.loop = LocalDurableLoop(self.home, self.turns, self.registry)
        self.published = 0
        self.registry.create("main", "/watchtower")
        self.work.create("job", "main")

    def tearDown(self):
        self.temp.cleanup()

    def publish_and_handle(self, count):
        for _ in range(count):
            turn = self.turns.create("job", "pi", "crew", "/tmp")
            _, event = self.loop.settle(turn.id, "test", "completed", "done", None)
            self.loop.handle(event.event_id)
            self.published += 1
        self.loop.ack("main", self.published)

    def read_count(self, operation):
        calls = 0
        original = settlement_module.read_json

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        with mock.patch.object(settlement_module, "read_json", side_effect=counted):
            operation()
        return calls

    def test_missing_terminal_result_or_artifact_fails_closed(self):
        turn = self.turns.create("job", "pi", "crew", "/tmp")
        self.loop.settle(turn.id, "test", "completed", "done", b"evidence")
        turn_path = self.home / "turns" / f"{turn.id}.json"
        saved = turn_path.read_bytes(); turn_path.unlink()
        with self.assertRaisesRegex(UnsafeStateError, "missing turn"):
            self.loop.unread("main")
        turn_path.write_bytes(saved)
        (self.home / "artifacts" / f"{turn.id}--stdin.json").unlink()
        with self.assertRaisesRegex(UnsafeStateError, "missing artifact"):
            self.loop.pending("main")

    def test_empty_views_and_new_settlement_ignore_handled_history(self):
        self.publish_and_handle(5)
        small_unread = self.read_count(lambda: self.loop.unread("main"))
        small_pending = self.read_count(lambda: self.loop.pending("main"))
        self.publish_and_handle(35)
        self.assertEqual(self.read_count(lambda: self.loop.unread("main")), small_unread)
        self.assertEqual(self.read_count(lambda: self.loop.pending("main")), small_pending)

        turn = self.turns.create("job", "pi", "crew", "/tmp")
        reads = self.read_count(lambda: self.loop.settle(turn.id, "test", "completed", "new", None))
        self.assertLessEqual(reads, 8)
        self.assertEqual([event.turn_id for event in self.loop.unread("main")], [turn.id])
