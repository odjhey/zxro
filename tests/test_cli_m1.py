import concurrent.futures
import json
import subprocess

from helpers import CliCase, ROOT, BIN, run_cli


class DurableLoopCliTests(CliCase):
    def turn(self, work="job"):
        return self.cli("turn", "create", "--work", work, "--agent", "pi", "--session", "crew", "--cwd", "/tmp").stdout.strip()

    def settle(self, turn, *extra, input=None, env=None):
        args = ["turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done", *extra]
        if input is None:
            return self.cli(*args, env=env)
        return subprocess.run([str(BIN), *args], cwd=ROOT, env={**__import__("os").environ, "ZXRO_HOME": str(self.home), **(env or {})}, input=input, text=True, capture_output=True)

    def setUp(self):
        super().setUp(); self.seed()

    def test_settlement_idempotency_payload_and_artifact(self):
        turn = self.turn()
        first = self.settle(turn, "--stdin", input="raw hook payload")
        self.assertEqual(first.returncode, 0, first.stderr)
        event = self.ok_json("inbox", "unread", "--watchtower", "main")[0]
        self.assertNotIn("raw hook payload", json.dumps(event))
        retry = self.settle(turn)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        same = self.settle(turn, "--stdin", input="raw hook payload")
        self.assertEqual(same.returncode, 0, same.stderr)
        conflict = self.settle(turn, "--stdin", input="changed")
        self.assertEqual(conflict.returncode, 4)
        self.assertEqual(len(self.ok_json("inbox", "unread", "--watchtower", "main")), 1)
        ref = event["artifact_refs"][0]
        path = self.cli("artifact", "path", ref)
        self.assertEqual(path.returncode, 0, path.stderr)
        self.assertEqual(__import__("pathlib").Path(path.stdout.strip()).read_text(), "raw hook payload")

    def test_artifact_corruption_fails_closed(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, "--stdin", input="evidence").returncode, 0)
        ref = self.ok_json("turn", "show", turn)["artifact_refs"][0]
        path = __import__("pathlib").Path(self.cli("artifact", "path", ref).stdout.strip())
        path.chmod(0o600); path.write_text("tampered")
        self.assertEqual(self.cli("artifact", "path", ref).returncode, 5)
        path.unlink()
        record = self.home / "artifacts" / f"{turn}--stdin.json"
        data = json.loads(record.read_text()); data["content_hex"] = "zz"; record.write_text(json.dumps(data))
        self.assertEqual(self.cli("artifact", "path", ref).returncode, 5)

    def test_artifact_record_must_match_requested_reference(self):
        first, second = self.turn(), self.turn()
        self.assertEqual(self.settle(first, "--stdin", input="one").returncode, 0)
        self.assertEqual(self.settle(second, "--stdin", input="two").returncode, 0)
        source = self.home / "artifacts" / f"{second}--stdin.json"
        target = self.home / "artifacts" / f"{first}--stdin.json"
        target.write_bytes(source.read_bytes())
        result = self.cli("artifact", "path", f"artifact:{first}:stdin")
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_oversized_artifact_is_rejected_before_settlement(self):
        turn = self.turn()
        result = self.settle(turn, "--stdin", input="x" * (9 * 1024 * 1024))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.ok_json("turn", "show", turn)["state"], "running")
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "main"), [])
        self.assertEqual(list((self.home / "artifacts").iterdir()), [])

    def test_conflicts_bounds_unknown_and_filters(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn).returncode, 0)
        changed = self.cli("turn", "settle", turn, "--source", "other", "--status", "failed", "--message", "done")
        self.assertEqual(changed.returncode, 4)
        unknown = self.cli("turn", "settle", "00000000-0000-4000-8000-000000000000", "--source", "x", "--status", "completed", "--message", "done")
        self.assertEqual(unknown.returncode, 3)
        self.assertEqual(len(self.ok_json("inbox", "unread", "--watchtower", "main")), 1)
        too_long = self.cli("turn", "settle", self.turn(), "--source", "x", "--status", "completed", "--message", "x" * 1001)
        self.assertEqual(too_long.returncode, 2)
        settled = self.ok_json("turn", "list", "--state", "settled")
        self.assertEqual([item["id"] for item in settled], [turn])

    def test_read_ack_handled_and_work_close_are_independent(self):
        events = []
        for _ in range(10):
            self.assertEqual(self.settle(self.turn()).returncode, 0)
        events = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([e["generation"] for e in events], list(range(1, 11)))
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "10").returncode, 0)
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "main"), [])
        for index in (7, 2):
            event_id = events[index]["event_id"]
            self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
            self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
        pending = self.ok_json("inbox", "pending", "--watchtower", "main")
        self.assertEqual([e["generation"] for e in pending], [1, 2, 4, 5, 6, 7, 9, 10])
        self.assertEqual(self.cli("work", "close", "job").returncode, 0)
        self.assertEqual(len(self.ok_json("inbox", "pending", "--watchtower", "main")), 8)
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "9").returncode, 4)
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "11").returncode, 4)

    def test_handle_rejects_symlinked_inbox(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        event_id = self.ok_json("inbox", "unread", "--watchtower", "main")[0]["event_id"]
        inbox = self.home / "inbox"
        inbox.rename(self.home / "real-inbox")
        inbox.symlink_to(self.home / "real-inbox", target_is_directory=True)
        result = self.cli("inbox", "handle", event_id)
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_mailbox_ack_rejects_boolean_generation(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        (self.home / "inbox" / "main.json").write_text(json.dumps({"watchtower_id": "main", "ack": True}))
        self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)

    def test_pending_rejects_invalid_handled_state(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        event_id = self.ok_json("inbox", "unread", "--watchtower", "main")[0]["event_id"]
        self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
        path = self.home / "inbox-handled" / f"{event_id}.json"
        original = json.loads(path.read_text())
        for change in ({"handled_at": "2025-01-01T00:00:00"}, {"watchtower_id": "../invalid"}):
            path.write_text(json.dumps({**original, **change}))
            self.assertEqual(self.cli("inbox", "pending", "--watchtower", "main").returncode, 5)

    def test_handle_validates_all_event_paths(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        event = self.ok_json("inbox", "unread", "--watchtower", "main")[0]
        path = next((self.home / "inbox-events").iterdir())
        path.rename(path.with_name(f"wrong--{event['event_id']}.json"))
        self.assertEqual(self.cli("inbox", "handle", event["event_id"]).returncode, 5)

    def test_crash_gap_retry_preserves_event_identity(self):
        turn = self.turn()
        crashed = self.settle(turn, env={"ZXRO_FAULT_EXIT_AFTER": "turn-commit"})
        self.assertEqual(crashed.returncode, 86)
        record = self.ok_json("turn", "show", turn)
        event_id = record["settlement"]["event_id"]
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "main"), [])
        self.assertEqual(self.settle(turn).returncode, 0)
        event = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([(e["event_id"], e["generation"]) for e in event], [(event_id, 1)])

    def test_crash_repair_rejects_mismatched_existing_event(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, env={"ZXRO_FAULT_EXIT_AFTER": "turn-commit"}).returncode, 86)
        event_id = self.ok_json("turn", "show", turn)["settlement"]["event_id"]
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        path = next((self.home / "inbox-events").iterdir())
        event = json.loads(path.read_text())
        event["event_id"] = event_id
        replacement = path.with_name(path.name.rsplit("--", 1)[0] + f"--{event_id}.json")
        path.rename(replacement)
        replacement.write_text(json.dumps(event))
        self.assertEqual(self.settle(turn).returncode, 5)

    def test_mailbox_events_validate_all_envelope_fields(self):
        turn = self.turn()
        other = self.turn()
        self.assertEqual(self.settle(turn).returncode, 0)
        path = next((self.home / "inbox-events").iterdir())
        original = json.loads(path.read_text())
        changes = (
            {"agent": 3},
            {"summary": []},
            {"created_at": "2025-01-01T00:00:00"},
            {"artifact_refs": [f"artifact:{other}:stdin"]},
        )
        for change in changes:
            path.write_text(json.dumps({**original, **change}))
            self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)

    def test_concurrent_settlements_have_unique_ordered_generations(self):
        turns = [self.turn() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda turn: run_cli(self.home, "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done"), turns))
        self.assertTrue(all(item.returncode == 0 for item in results), [item.stderr for item in results])
        events = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([e["generation"] for e in events], list(range(1, 13)))
        self.assertEqual(len({e["event_id"] for e in events}), 12)
        self.assertEqual({e["turn_id"] for e in events}, set(turns))
