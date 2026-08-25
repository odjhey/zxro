import json
from concurrent.futures import ThreadPoolExecutor

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

    def test_metadata_replace_show_unset_and_lifecycle(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        first = self.cli("--json", "work", "meta", "set", "job", "beads", "--stdin", input_text='{"issue":"e\\u0301"}')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["data"]["metadata"], {"beads": {"issue": "é"}})
        self.assertEqual(self.cli("work", "meta", "set", "job", "github", "--stdin", input_text='{"issue":29}').returncode, 0)
        self.assertEqual(self.cli("work", "meta", "set", "job", "beads", "--stdin", input_text='{"issue":"new"}').returncode, 0)
        self.assertEqual(self.ok_json("work", "meta", "show", "job"), {"beads": {"issue": "new"}, "github": {"issue": 29}})
        self.assertEqual(self.ok_json("work", "meta", "show", "job", "github"), {"issue": 29})
        turn_id = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "coder", "--cwd", "/crew").stdout.strip()
        settled = self.cli("turn", "settle", turn_id, "--source", "test", "--status", "completed", "--message", "done")
        self.assertEqual(settled.returncode, 0, settled.stderr)
        self.assertEqual(self.ok_json("work", "meta", "show", "job", "github"), {"issue": 29})
        self.ok_json("work", "close", "job")
        self.assertEqual(self.cli("work", "meta", "unset", "job", "beads").returncode, 0)
        self.assertEqual(self.cli("work", "meta", "unset", "job", "beads").returncode, 0)
        shown = self.ok_json("work", "show", "job")
        self.assertEqual(shown["state"], "closed"); self.assertEqual(shown["metadata"], {"github": {"issue": 29}})

    def test_metadata_errors_and_absence(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        self.assertNotIn("metadata", self.ok_json("work", "show", "job"))
        self.assertEqual(self.cli("work", "meta", "show", "job", "missing").returncode, 3)
        for namespace, payload in (("zxro", "{}"), ("Upper", "{}"), ("ok", "null"), ("ok", "{"), ("ok", '{"x":1.2}')):
            with self.subTest(namespace=namespace, payload=payload):
                self.assertEqual(self.cli("work", "meta", "set", "job", namespace, "--stdin", input_text=payload).returncode, 2)
        self.assertNotIn("metadata", self.ok_json("work", "show", "job"))

    def test_malformed_durable_metadata_fails_closed(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        path = self.home / "work" / "job.json"
        path.write_text('{"id":"job","metadata":{"bad":{"key":null}},"state":"open","watchtower_id":"main"}\n')
        self.assertEqual(self.cli("work", "show", "job").returncode, 5)

    def test_concurrent_namespace_writers_serialize(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        def write(index):
            return self.cli("work", "meta", "set", "job", f"ns{index}", "--stdin", input_text=json.dumps({"value": index})).returncode
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(write, range(8))), [0] * 8)
        metadata = self.ok_json("work", "meta", "show", "job")
        self.assertEqual(metadata, {f"ns{i}": {"value": i} for i in range(8)})
        listing = self.cli("work", "list").stdout.strip()
        self.assertIn("metadata=" + ",".join(f"ns{i}" for i in range(8)), listing)
        self.assertEqual(len(listing.splitlines()), 1)
