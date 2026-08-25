import json
from concurrent.futures import ThreadPoolExecutor

from tests.helpers import CliCase
from zxro.settle import MAX_STDIN_BYTES


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
        for namespace in ("zxro", "Upper", "-bad", "a" * 65):
            with self.subTest(show_namespace=namespace):
                self.assertEqual(self.cli("work", "meta", "show", "job", namespace).returncode, 2)
        for namespace, payload in (("zxro", "{}"), ("Upper", "{}"), ("ok", "null"), ("ok", "{"), ("ok", '{"x":1.2}')):
            with self.subTest(namespace=namespace, payload=payload):
                self.assertEqual(self.cli("work", "meta", "set", "job", namespace, "--stdin", input_text=payload).returncode, 2)
        self.assertNotIn("metadata", self.ok_json("work", "show", "job"))

    def test_metadata_show_argument_errors_precede_missing_work(self):
        self.assertEqual(self.cli("work", "meta", "show", "missing-work", "valid").returncode, 3)
        for namespace in ("zxro", "Upper", "-bad", "a" * 65):
            with self.subTest(namespace=namespace):
                self.assertEqual(self.cli("work", "meta", "show", "missing-work", namespace).returncode, 2)

    def test_metadata_set_ignores_insignificant_raw_json_whitespace(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        payload = " " * 10_000 + '{"key":"value"}' + " " * 10_000
        result = self.cli("work", "meta", "set", "job", "tracker", "--stdin", input_text=payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ok_json("work", "meta", "show", "job", "tracker"), {"key": "value"})

    def test_metadata_bounds_through_public_cli(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        accepted = {
            "a" * 64: {"k" * 64: {"b": {"c": {"d": "x" * 2048}}}},
        }
        namespace, payload = next(iter(accepted.items()))
        result = self.cli("work", "meta", "set", "job", namespace, "--stdin", input_text=json.dumps(payload))
        self.assertEqual(result.returncode, 0, result.stderr)
        rejected = (
            ("a" * 65, {}),
            ("valid", {"k" * 65: 1}),
            ("valid", {"a": {"b": {"c": {"d": {"e": 1}}}}}),
            ("valid", {"k": "x" * 2049}),
            ("valid", {"k": 1.5}),
            ("valid", {"k": None}),
            ("valid", {"k": [{}]}),
            ("zxro", {}),
        )
        for namespace, payload in rejected:
            with self.subTest(namespace=namespace, payload_type=type(payload).__name__):
                self.assertEqual(self.cli("work", "meta", "set", "job", namespace, "--stdin", input_text=json.dumps(payload)).returncode, 2)
        self.assertEqual(self.cli("work", "meta", "unset", "job", "a" * 64).returncode, 0)
        exact = {f"k{i}": "x" * 2048 for i in range(7)}
        exact["tail"] = ""
        wrapped = {"size": exact}
        current = len(json.dumps(wrapped, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        exact["tail"] = "x" * (16 * 1024 - current)
        self.assertEqual(self.cli("work", "meta", "set", "job", "size", "--stdin", input_text=json.dumps(exact, separators=(",", ":"))).returncode, 0)
        exact["tail"] += "x"
        self.assertEqual(self.cli("work", "meta", "set", "job", "size", "--stdin", input_text=json.dumps(exact, separators=(",", ":"))).returncode, 2)

    def test_metadata_set_rejects_oversized_stdin_before_buffering(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        oversized = "x" * (MAX_STDIN_BYTES + 1)
        result = self.cli("work", "meta", "set", "job", "tracker", "--stdin", input_text=oversized)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("stdin payload too large", result.stderr)
        self.assertNotIn("metadata", self.ok_json("work", "show", "job"))

    def test_metadata_unset_rejects_reserved_namespace(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        self.assertEqual(self.cli("work", "meta", "set", "job", "tracker", "--stdin", input_text='{"issue":29}').returncode, 0)
        result = self.cli("work", "meta", "unset", "job", "zxro")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.ok_json("work", "meta", "show", "job", "tracker"), {"issue": 29})

    def test_malformed_and_newer_durable_work_records_fail_closed(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        path = self.home / "work" / "job.json"
        records = (
            {"id": "job", "metadata": {"bad": {"key": None}}, "state": "open", "watchtower_id": "main"},
            {"id": "job", "metadata": None, "state": "open", "watchtower_id": "main"},
            {"id": "job", "metadata": {"bad": {"key": "e\u0301"}}, "state": "open", "watchtower_id": "main"},
            {"id": "job", "state": "open", "watchtower_id": "main", "future_field": {}},
        )
        for record in records:
            with self.subTest(record=record):
                path.write_text(json.dumps(record) + "\n")
                self.assertEqual(self.cli("work", "show", "job").returncode, 5)

    def test_metadata_preserves_a1_envelope_and_c1_artifact_views(self):
        self.ok_json("work", "create", "job", "--watchtower", "main")
        self.assertEqual(self.cli("work", "meta", "set", "job", "tracker", "--stdin", input_text='{"issue":39}').returncode, 0)
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "coder", "--cwd", "/crew").stdout.strip()
        artifact = self.cli("--json", "artifact", "put", turn, "--kind", "review", "--stdin", input_text="evidence")
        self.assertEqual(json.loads(artifact.stdout)["data"], {"bytes": 8, "kind": "review", "ref": f"artifact:{turn}:review"})
        settled = self.cli("--json", "turn", "settle", turn, "--source", "test", "--status", "completed", "--message", "done", "--verdict", "done")
        settled_data = json.loads(settled.stdout)["data"]
        self.assertNotIn("artifacts", settled_data)
        shown_turn = self.ok_json("turn", "show", turn)
        self.assertEqual(shown_turn["artifacts"], [{"bytes": 8, "kind": "review", "ref": f"artifact:{turn}:review"}])
        shown_work = json.loads(self.cli("--json", "work", "show", "job").stdout)
        self.assertEqual(shown_work["schema_version"], 1)
        self.assertEqual(shown_work["data"]["metadata"], {"tracker": {"issue": 39}})

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
