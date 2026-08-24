import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from zxro.localfs import m1_capabilities, m2_capabilities, providers
import zxro.localfs.durable as durable_module

from conformance.m1_base import M1ProviderConformance
from conformance.m2_base import M2ProviderConformance
from helpers import run_cli


class BuiltinM1ProviderConformance(M2ProviderConformance, M1ProviderConformance, unittest.TestCase):
    unsafe_error = UnsafeStateError
    conflict_error = ConflictError
    not_found_error = NotFoundError
    validation_error = ValidationError
    settlement_cost_limit = 10

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.registry, self.work, self.turns = providers(self.home)
        self.m1 = m1_capabilities(self.home, self.registry, self.turns)
        self.m2 = m2_capabilities(self.home, self.registry, self.work, self.turns)
        self.registry.create("main", "/watchtower")
        self.work.create("job", "main")
        self.published = 0
        self.extra_temps = []

    def tearDown(self):
        for temporary in self.extra_temps:
            temporary.cleanup()
        self.temp.cleanup()

    def remove_turn(self, turn_id):
        path = self.home / "turns" / f"{turn_id}.json"
        saved = path.read_bytes(); path.unlink()
        return lambda: path.write_bytes(saved)

    def remove_artifact(self, turn_id, kind):
        (self.home / "artifacts" / f"{turn_id}--{kind}.json").unlink()

    def interrupt_after_terminal_commit(self, turn):
        result = run_cli(self.home, "turn", "settle", turn.id, "--source", "test", "--status", "completed", "--message", "done", env={"ZXRO_FAULT_EXIT_AFTER": "turn-commit"})
        self.assertEqual(result.returncode, 86, result.stderr)
        return self.turns.get(turn.id).settlement.event_id

    def corrupt_artifact_relationship(self, turn, event):
        path = self.home / "artifacts" / f"{turn.id}--stdin.json"; saved = path.read_bytes()
        value = json.loads(saved); content = b"replacement"
        value.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), content_hex=content.hex())
        path.write_text(json.dumps(value))
        return lambda: path.write_bytes(saved)

    def corrupt_event_identity_lookup(self, event, invalid_generation):
        path = self.home / "inbox-index" / f"{event.event_id}.json"; saved = path.read_bytes()
        value = json.loads(saved); value["generation"] = invalid_generation; path.write_text(json.dumps(value))
        return lambda: path.write_bytes(saved)

    def remove_ack_generation(self, event):
        path = self.home / "inbox-events" / f"{event.watchtower_id}--{event.generation:020d}.json"; saved = path.read_bytes(); path.unlink()
        return lambda: path.write_bytes(saved)

    def interrupt_handle_after_authoritative_commit(self, event):
        result = run_cli(self.home, "inbox", "handle", event.event_id, env={"ZXRO_FAULT_EXIT_AFTER": "handle-marker-commit"})
        self.assertEqual(result.returncode, 86, result.stderr)

    def new_namespace(self):
        temporary = tempfile.TemporaryDirectory(); self.extra_temps.append(temporary)
        home = Path(temporary.name) / "home"
        registry, work, turns = providers(home)
        registry.create("main", "/watchtower"); work.create("job", "main")
        return m1_capabilities(home, registry, turns), turns

    def missing_namespace(self):
        temporary = tempfile.TemporaryDirectory(); self.extra_temps.append(temporary)
        self.missing_home = Path(temporary.name) / "missing"
        registry, _, turns = providers(self.missing_home)
        return m1_capabilities(self.missing_home, registry, turns)

    def assert_missing_namespace_uncreated(self):
        self.assertFalse(self.missing_home.exists())

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
