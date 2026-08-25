import uuid
from tests.helpers import CliCase


class TurnCliTests(CliCase):
    def setUp(self):
        super().setUp(); self.seed()

    def create(self, session="coder", work="job", cwd="/crew", native=None):
        args = ["turn", "create", "--work", work, "--agent", "claude", "--session", session, "--cwd", cwd]
        if native is not None: args += ["--native-session-id", native]
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

    def test_empty_native_session_id_is_usage_error_without_turn(self):
        before = list((self.home / "turns").glob("*.json"))
        result = self.create(native="")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list((self.home / "turns").glob("*.json")), before)

    def test_empty_required_agent_and_session_are_usage_errors(self):
        for flag in ("--agent", "--session"):
            args = ["turn", "create", "--work", "job", "--agent", "ok", "--session", "ok", "--cwd", "/x", flag, ""]
            self.assertEqual(self.cli(*args).returncode, 2)

    def test_control_characters_are_rejected(self):
        for flag, value in (("--agent", "bad\nagent"), ("--session", "bad\tsession"), ("--native-session-id", "bad\x7f")):
            args = ["turn", "create", "--work", "job", "--agent", "ok", "--session", "ok", "--cwd", "/x", flag, value]
            self.assertEqual(self.cli(*args).returncode, 2)

    def bind(self, turn_id, native="native-7", source="manual recovery"):
        return self.cli("turn", "bind", turn_id, "--native-session-id", native, "--source", source)

    def test_bind_running_turn_round_trips_in_human_and_json_show(self):
        turn_id = self.create().stdout.strip()
        before = self.ok_json("turn", "show", turn_id)
        result = self.bind(turn_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.ok_json("turn", "show", turn_id)
        self.assertEqual(record["native_session_id"], "native-7")
        self.assertEqual(record["native_session_source"], "manual recovery")
        for key in ("id", "work_id", "watchtower_id", "runtime", "agent", "session", "cwd", "state"):
            self.assertEqual(record[key], before[key])
        human = self.cli("turn", "show", turn_id)
        self.assertIn("native_session_id: native-7\n", human.stdout)
        self.assertIn("native_session_source: manual recovery\n", human.stdout)

    def test_identical_rebind_is_idempotent_and_conflicts_do_not_mutate(self):
        turn_id = self.create().stdout.strip()
        self.assertEqual(self.bind(turn_id).returncode, 0)
        path = self.home / "turns" / f"{turn_id}.json"
        bound_bytes = path.read_bytes()
        self.assertEqual(self.bind(turn_id).returncode, 0)
        self.assertEqual(path.read_bytes(), bound_bytes)
        for native, source in (("other", "manual recovery"), ("native-7", "other source")):
            result = self.bind(turn_id, native, source)
            self.assertEqual(result.returncode, 4)
            self.assertEqual(path.read_bytes(), bound_bytes)

    def test_create_time_native_id_can_be_enriched_once_with_source(self):
        turn_id = self.create(native="native-7").stdout.strip()
        self.assertNotIn("native_session_source", self.ok_json("turn", "show", turn_id))
        self.assertEqual(self.bind(turn_id).returncode, 0)
        bound = self.ok_json("turn", "show", turn_id)
        self.assertEqual(bound["native_session_source"], "manual recovery")
        self.assertEqual(self.bind(turn_id, source="different").returncode, 4)
        self.assertEqual(self.bind(turn_id, native="other").returncode, 4)
        self.assertEqual(self.ok_json("turn", "show", turn_id), bound)

    def test_bind_settled_turn_after_work_close_changes_only_binding(self):
        turn_id = self.create().stdout.strip()
        settled = self.cli("turn", "settle", turn_id, "--source", "test", "--status", "completed", "--message", "done")
        self.assertEqual(settled.returncode, 0, settled.stderr)
        self.assertEqual(self.cli("work", "close", "job").returncode, 0)
        turn_before = self.ok_json("turn", "show", turn_id)
        work_before = self.ok_json("work", "show", "job")
        inbox_before = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual(self.bind(turn_id).returncode, 0)
        turn_after = self.ok_json("turn", "show", turn_id)
        for key, value in turn_before.items():
            self.assertEqual(turn_after[key], value)
        self.assertEqual(turn_after["native_session_id"], "native-7")
        self.assertEqual(turn_after["native_session_source"], "manual recovery")
        self.assertEqual(self.ok_json("work", "show", "job"), work_before)
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "main"), inbox_before)

    def test_bind_rejects_unknown_turn_and_malformed_values(self):
        unknown = str(uuid.uuid4())
        self.assertEqual(self.bind(unknown).returncode, 3)
        turn_id = self.create().stdout.strip()
        path = self.home / "turns" / f"{turn_id}.json"
        before = path.read_bytes()
        for native, source in (("", "source"), ("native", ""), ("bad\nvalue", "source"), ("native", "bad\x7f"), ("x" * 257, "source"), ("native", "x" * 257)):
            self.assertEqual(self.bind(turn_id, native, source).returncode, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_create_rejects_overlong_native_session_id(self):
        self.assertEqual(self.create(native="x" * 257).returncode, 2)
