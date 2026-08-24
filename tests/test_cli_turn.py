import uuid
from tests.helpers import CliCase


class TurnCliTests(CliCase):
    def setUp(self):
        super().setUp(); self.seed()

    def create(self, session="coder", work="job", cwd="/crew", native=None):
        args = ["turn", "create", "--work", work, "--agent", "claude", "--session", session, "--cwd", cwd]
        if native: args += ["--native-session-id", native]
        return self.cli(*args)

    def test_create_prints_uuid_and_show_round_trips_distinct_identity(self):
        result = self.create(cwd="/crew/target", native="native-7")
        self.assertEqual(result.returncode, 0, result.stderr)
        turn_id = result.stdout.strip(); self.assertEqual(uuid.UUID(turn_id).version, 4)
        record = self.ok_json("turn", "show", turn_id)
        self.assertEqual(record["id"], turn_id); self.assertEqual(record["work_id"], "job"); self.assertEqual(record["watchtower_id"], "main")
        self.assertEqual(record["runtime"], "acpx"); self.assertEqual(record["state"], "running"); self.assertEqual(record["native_session_id"], "native-7")
        self.assertNotEqual(record["cwd"], self.ok_json("watchtower", "show", "main")["cwd"])

    def test_list_filters_compose(self):
        one = self.create(session="one").stdout.strip()
        self.cli("work", "create", "other", "--watchtower", "main"); two = self.create(session="two", work="other").stdout.strip()
        self.assertEqual([x["id"] for x in self.ok_json("turn", "list", "--work", "job")], [one])
        self.assertEqual({x["id"] for x in self.ok_json("turn", "list", "--state", "running")}, {one, two})
        self.assertEqual([x["id"] for x in self.ok_json("turn", "list", "--work", "other", "--state", "running")], [two])

    def test_unknown_work_creates_no_turn(self):
        result = self.create(work="missing")
        self.assertEqual(result.returncode, 3); self.assertEqual(list((self.home / "turns").glob("*.json")), [])

    def test_control_characters_are_rejected(self):
        for flag, value in (("--agent", "bad\nagent"), ("--session", "bad\tsession"), ("--native-session-id", "bad\x7f")):
            args = ["turn", "create", "--work", "job", "--agent", "ok", "--session", "ok", "--cwd", "/x", flag, value]
            self.assertEqual(self.cli(*args).returncode, 2)
