import tempfile
from pathlib import Path


class ProviderConformance:
    factory = None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = Path(self.temp.name) / "state"
        self.registry, self.work, self.turn = self.factory(self.home)

    def tearDown(self): self.temp.cleanup()

    def test_registry_work_turn_crud_and_identity_separation(self):
        watchtower = self.registry.create("main", "/watchtower", "pi", "wt")
        work = self.work.create("job", "main")
        turn = self.turn.create("job", "claude", "coder", "/crew", "native")
        self.assertEqual(self.registry.get("main"), watchtower); self.assertEqual(self.work.get("job"), work); self.assertEqual(self.turn.get(turn.id), turn)
        self.assertNotEqual(turn.id, work.id); self.assertNotEqual(turn.cwd, watchtower.cwd); self.assertEqual(turn.runtime, "acpx")

    def test_filters_close_and_duplicate_semantics(self):
        from zxro.errors import ConflictError
        self.registry.create("main", "/wt"); self.work.create("a", "main"); self.work.create("b", "main"); self.work.close("b")
        self.assertEqual([x.id for x in self.work.list(state="open")], ["a"])
        with self.assertRaises(ConflictError): self.work.create("a", "main")

    def test_namespace_isolation(self):
        other_home = Path(self.temp.name) / "other"; registry2, work2, _ = self.factory(other_home)
        self.registry.create("main", "/one"); self.work.create("same", "main")
        registry2.create("main", "/two"); work2.create("same", "main"); self.work.close("same")
        self.assertEqual(work2.get("same").state, "open")
