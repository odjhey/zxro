from tests.helpers import CliCase


class WorkCliTests(CliCase):
    def setUp(self):
        super().setUp(); self.cli("watchtower", "create", "main", "--cwd", "/wt"); self.cli("watchtower", "create", "other", "--cwd", "/other")

    def test_create_show_list_close_and_idempotent_close(self):
        created = self.ok_json("work", "create", "job", "--watchtower", "main")
        self.assertEqual(created["state"], "open"); self.assertEqual(self.ok_json("work", "show", "job"), created)
        closed = self.ok_json("work", "close", "job"); again = self.ok_json("work", "close", "job")
        self.assertEqual(closed, again); self.assertEqual(closed["state"], "closed")

    def test_filters_compose_and_lists_are_deterministic(self):
        self.ok_json("work", "create", "z", "--watchtower", "main"); self.ok_json("work", "create", "a", "--watchtower", "main"); self.ok_json("work", "create", "b", "--watchtower", "other"); self.ok_json("work", "close", "a")
        self.assertEqual([x["id"] for x in self.ok_json("work", "list", "--watchtower", "main")], ["a", "z"])
        self.assertEqual([x["id"] for x in self.ok_json("work", "list", "--state", "open")], ["b", "z"])
        self.assertEqual([x["id"] for x in self.ok_json("work", "list", "--watchtower", "main", "--state", "closed")], ["a"])

    def test_unknown_parent_creates_nothing(self):
        result = self.cli("work", "create", "orphan", "--watchtower", "missing")
        self.assertEqual(result.returncode, 3); self.assertFalse((self.home / "work" / "orphan.json").exists())

    def test_duplicate_and_unknown_show_close(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        self.assertEqual(self.cli("work", "create", "job", "--watchtower", "main").returncode, 4)
        self.assertEqual(self.cli("work", "show", "none").returncode, 3); self.assertEqual(self.cli("work", "close", "none").returncode, 3)

    def test_show_stays_bounded_after_many_turns(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        before = self.cli("--json", "work", "show", "job").stdout
        for i in range(20): self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", f"s{i}", "--cwd", "/crew")
        self.assertEqual(self.cli("--json", "work", "show", "job").stdout, before)
