import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zxro.errors import UnsafeStateError
from zxro.localfs import m1_capabilities, providers
import zxro.localfs.durable as durable_module

from conformance.m1_base import M1ProviderConformance


class BuiltinM1ProviderConformance(M1ProviderConformance, unittest.TestCase):
    unsafe_error = UnsafeStateError
    settlement_cost_limit = 10

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.registry, self.work, self.turns = providers(self.home)
        self.m1 = m1_capabilities(self.home, self.registry, self.turns)
        self.registry.create("main", "/watchtower")
        self.work.create("job", "main")
        self.published = 0

    def tearDown(self):
        self.temp.cleanup()

    def remove_turn(self, turn_id):
        path = self.home / "turns" / f"{turn_id}.json"
        saved = path.read_bytes(); path.unlink()
        return lambda: path.write_bytes(saved)

    def remove_artifact(self, turn_id, kind):
        (self.home / "artifacts" / f"{turn_id}--{kind}.json").unlink()

    def operation_cost(self, operation):
        calls = 0
        original = durable_module.read_json

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        with mock.patch.object(durable_module, "read_json", side_effect=counted):
            operation()
        return calls
