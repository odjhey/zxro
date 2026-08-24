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
        path.write_text("tampered")
        self.assertEqual(self.cli("artifact", "path", ref).returncode, 5)
        path.unlink()
        record = self.home / "artifacts" / f"{turn}--stdin.json"
        data = json.loads(record.read_text()); data["content_hex"] = "zz"; record.write_text(json.dumps(data))
        self.assertEqual(self.cli("artifact", "path", ref).returncode, 5)

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

    def test_concurrent_settlements_have_unique_ordered_generations(self):
        turns = [self.turn() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda turn: run_cli(self.home, "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done"), turns))
        self.assertTrue(all(item.returncode == 0 for item in results), [item.stderr for item in results])
        events = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([e["generation"] for e in events], list(range(1, 13)))
        self.assertEqual(len({e["event_id"] for e in events}), 12)
        self.assertEqual({e["turn_id"] for e in events}, set(turns))
