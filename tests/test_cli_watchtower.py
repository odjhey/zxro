from tests.helpers import CliCase


class WatchtowerCliTests(CliCase):
    def test_create_show_list_and_optional_fields_round_trip(self):
        created = self.ok_json("watchtower", "create", "main", "--cwd", "~/wt/../watchtower", "--agent", "pi", "--session", "watch")
        shown = self.ok_json("watchtower", "show", "main")
        self.assertEqual(created, shown)
        self.assertEqual(shown["agent"], "pi"); self.assertEqual(shown["session"], "watch")
        self.assertTrue(shown["cwd"].startswith("/")); self.assertNotIn("..", shown["cwd"])
        self.ok_json("watchtower", "create", "aaa", "--cwd", "/a")
        self.assertEqual([x["id"] for x in self.ok_json("watchtower", "list")], ["aaa", "main"])

    def test_duplicate_rejected_without_overwrite(self):
        first = self.ok_json("watchtower", "create", "main", "--cwd", "/first")
        result = self.cli("watchtower", "create", "main", "--cwd", "/second")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.ok_json("watchtower", "show", "main"), first)

    def test_unknown_show_is_missing(self):
        self.assertEqual(self.cli("watchtower", "show", "none").returncode, 3)

    def test_invalid_ids_are_validation_errors(self):
        values = ["a/b", ".", "..", "", "x" * 65, "space here", "é"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(self.cli("watchtower", "create", value, "--cwd", "/x").returncode, 2)
