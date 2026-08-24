import concurrent.futures
import json
import os
import subprocess
import tempfile
from pathlib import Path

from zxro.settle import MAX_STDIN_BYTES
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

    def test_artifact_record_rejects_boolean_byte_count(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, "--stdin", input="").returncode, 0)
        record = self.home / "artifacts" / f"{turn}--stdin.json"
        data = json.loads(record.read_text())
        data["bytes"] = False
        record.write_text(json.dumps(data))
        self.assertEqual(self.cli("artifact", "path", f"artifact:{turn}:stdin").returncode, 5)

    def test_oversized_artifact_is_rejected_before_settlement(self):
        turn = self.turn()
        payload = self.home.parent / "oversized.bin"
        with payload.open("wb") as stream:
            stream.truncate(MAX_STDIN_BYTES + 1)
        environment = {**os.environ, "ZXRO_HOME": str(self.home)}
        with payload.open("rb") as stream:
            result = subprocess.run([str(BIN), "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done", "--stdin"], cwd=ROOT, env=environment, stdin=stream, capture_output=True, text=True)
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
        (self.home / "inbox" / "main.json").write_text(json.dumps({"watchtower_id": "main", "ack": True, "highest": 1, "unresolved": []}))
        self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)

    def test_handle_rejects_mismatched_direct_index(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        event = self.ok_json("inbox", "unread", "--watchtower", "main")[0]
        path = self.home / "inbox-index" / f"{event['event_id']}.json"
        value = json.loads(path.read_text()); value["generation"] = 2; path.write_text(json.dumps(value))
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

    def test_three_record_publication_resumes_without_overwrite(self):
        for point in ("before-event-commit", "event-commit", "before-index-commit", "index-commit", "before-mailbox-commit", "mailbox-commit"):
            with self.subTest(point=point):
                first = self.turn()
                crashed = self.settle(first, env={"ZXRO_FAULT_EXIT_AFTER": point})
                self.assertEqual(crashed.returncode, 86)
                first_id = self.ok_json("turn", "show", first)["settlement"]["event_id"]
                second = self.turn()
                self.assertEqual(self.settle(second).returncode, 0)
                self.assertEqual(self.settle(first).returncode, 0)
                events = [event for event in self.ok_json("inbox", "unread", "--watchtower", "main") if event["turn_id"] in {first, second}]
                self.assertEqual([event["generation"] for event in events], list(range(events[0]["generation"], events[0]["generation"] + 2)))
                self.assertEqual({event["turn_id"] for event in events}, {first, second})
                self.assertEqual(next(event["event_id"] for event in events if event["turn_id"] == first), first_id)

    def test_handle_between_index_and_mailbox_survives_repair(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, env={"ZXRO_FAULT_EXIT_AFTER": "index-commit"}).returncode, 86)
        event_id = self.ok_json("turn", "show", turn)["settlement"]["event_id"]
        self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
        self.assertEqual(self.settle(turn).returncode, 0)
        self.assertNotIn(event_id, [event["event_id"] for event in self.ok_json("inbox", "pending", "--watchtower", "main")])

    def test_handle_fault_matrix_converges_without_lost_attention(self):
        for point in ("before-handle-marker-commit", "handle-marker-commit", "before-handle-mailbox-commit", "handle-mailbox-commit"):
            with self.subTest(point=point):
                turn = self.turn()
                self.assertEqual(self.settle(turn).returncode, 0)
                event_id = next(event["event_id"] for event in self.ok_json("inbox", "pending", "--watchtower", "main") if event["turn_id"] == turn)
                result = self.cli("inbox", "handle", event_id, env={"ZXRO_FAULT_EXIT_AFTER": point})
                self.assertEqual(result.returncode, 86)
                pending = [event["event_id"] for event in self.ok_json("inbox", "pending", "--watchtower", "main")]
                marker = self.home / "inbox-handled" / f"{event_id}.json"
                self.assertTrue(event_id in pending or marker.exists())
                self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
                self.assertNotIn(event_id, [event["event_id"] for event in self.ok_json("inbox", "pending", "--watchtower", "main")])
                self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)

    def test_crash_repair_rejects_mismatched_existing_event(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, env={"ZXRO_FAULT_EXIT_AFTER": "turn-commit"}).returncode, 86)
        event_id = self.ok_json("turn", "show", turn)["settlement"]["event_id"]
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        index = next((self.home / "inbox-index").iterdir())
        value = json.loads(index.read_text()); value["event_id"] = event_id
        (self.home / "inbox-index" / f"{event_id}.json").write_text(json.dumps(value))
        self.assertEqual(self.settle(turn).returncode, 5)

    def test_artifact_digest_and_unresolved_owner_are_cross_checked(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, "--stdin", input="original").returncode, 0)
        artifact = self.home / "artifacts" / f"{turn}--stdin.json"
        original_record = artifact.read_bytes()
        value = json.loads(original_record)
        replacement = b"replacement"
        value.update(bytes=len(replacement), sha256=__import__("hashlib").sha256(replacement).hexdigest(), content_hex=replacement.hex())
        artifact.write_text(json.dumps(value))
        self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)
        artifact.write_bytes(original_record)

        self.assertEqual(self.cli("watchtower", "create", "other", "--cwd", "/other").returncode, 0)
        self.assertEqual(self.cli("work", "create", "other-job", "--watchtower", "other").returncode, 0)
        other_turn = self.turn("other-job")
        self.assertEqual(self.settle(other_turn).returncode, 0)
        other_event = self.ok_json("inbox", "unread", "--watchtower", "other")[0]
        box = self.home / "inbox" / "main.json"
        state = json.loads(box.read_text()); state["unresolved"].append(other_event["event_id"]); box.write_text(json.dumps(state))
        self.assertEqual(self.cli("inbox", "pending", "--watchtower", "main").returncode, 5)

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

    def test_settled_turn_rejects_non_normalized_summary(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn).returncode, 0)
        path = self.home / "turns" / f"{turn}.json"
        data = json.loads(path.read_text())
        data["summary"] = data["settlement"]["summary"] = "e\u0301"
        path.write_text(json.dumps(data))
        self.assertEqual(self.cli("turn", "show", turn).returncode, 5)

    def test_partial_publication_index_corruption_precedes_unrelated_turn_mutation(self):
        corruptions = {
            "boolean": lambda value: {**value, "generation": True},
            "integral-float": lambda value: {**value, "generation": 1.0},
            "string": lambda value: {**value, "generation": "1"},
            "missing-generation": lambda value: {key: item for key, item in value.items() if key != "generation"},
            "mismatched-owner": lambda value: {**value, "watchtower_id": "other"},
            "mismatched-generation": lambda value: {**value, "generation": 2},
        }
        for label, corrupt in corruptions.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / "home"
                self.assertEqual(run_cli(home, "watchtower", "create", "main", "--cwd", "/wt").returncode, 0)
                self.assertEqual(run_cli(home, "work", "create", "job", "--watchtower", "main").returncode, 0)
                first = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "one", "--cwd", "/tmp").stdout.strip()
                crashed = run_cli(home, "turn", "settle", first, "--source", "test", "--status", "completed", "--message", "first", env={"ZXRO_FAULT_EXIT_AFTER": "index-commit"})
                self.assertEqual(crashed.returncode, 86)
                first_record = json.loads(run_cli(home, "--json", "turn", "show", first).stdout)
                index = home / "inbox-index" / f"{first_record['settlement']['event_id']}.json"
                index.write_text(json.dumps(corrupt(json.loads(index.read_text()))))
                second = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "two", "--cwd", "/tmp").stdout.strip()
                mailbox = home / "inbox" / "main.json"
                before = mailbox.read_bytes() if mailbox.exists() else None
                result = run_cli(home, "turn", "settle", second, "--source", "test", "--status", "completed", "--message", "second")
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertEqual(mailbox.read_bytes() if mailbox.exists() else None, before)
                second_record = json.loads(run_cli(home, "--json", "turn", "show", second).stdout)
                self.assertEqual(second_record["state"], "running")

    def test_published_boundary_index_corruption_precedes_requested_turn_mutation(self):
        corruptions = {
            "missing": None,
            "boolean": lambda value: {**value, "generation": True},
            "integral-float": lambda value: {**value, "generation": 1.0},
            "wrong-owner": lambda value: {**value, "watchtower_id": "other"},
            "wrong-generation": lambda value: {**value, "generation": 2},
        }
        for label, corrupt in corruptions.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / "home"
                self.assertEqual(run_cli(home, "watchtower", "create", "main", "--cwd", "/wt").returncode, 0)
                self.assertEqual(run_cli(home, "work", "create", "job", "--watchtower", "main").returncode, 0)
                first = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "one", "--cwd", "/tmp").stdout.strip()
                self.assertEqual(run_cli(home, "turn", "settle", first, "--source", "test", "--status", "completed", "--message", "first").returncode, 0)
                event = json.loads(run_cli(home, "--json", "inbox", "unread", "--watchtower", "main").stdout)[0]
                index = home / "inbox-index" / f"{event['event_id']}.json"
                if corrupt is None:
                    index.unlink()
                else:
                    index.write_text(json.dumps(corrupt(json.loads(index.read_text()))))
                second = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "two", "--cwd", "/tmp").stdout.strip()
                mailbox = home / "inbox" / "main.json"; before = mailbox.read_bytes()
                result = run_cli(home, "turn", "settle", second, "--source", "test", "--status", "completed", "--message", "second")
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertEqual(mailbox.read_bytes(), before)
                self.assertEqual(json.loads(run_cli(home, "--json", "turn", "show", second).stdout)["state"], "running")

    def test_missing_partial_index_remains_a_repairable_event_commit_window(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, env={"ZXRO_FAULT_EXIT_AFTER": "event-commit"}).returncode, 86)
        event_id = self.ok_json("turn", "show", turn)["settlement"]["event_id"]
        self.assertFalse((self.home / "inbox-index" / f"{event_id}.json").exists())
        self.assertEqual(self.settle(turn).returncode, 0)
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "main")[0]["event_id"], event_id)

    def test_malformed_next_event_leaves_requested_turn_running(self):
        turn = self.turn()
        events = self.home / "inbox-events"
        events.mkdir(parents=True, exist_ok=True)
        (events / f"main--{1:020d}.json").write_text("{}")
        result = self.settle(turn)
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(self.ok_json("turn", "show", turn)["state"], "running")
        self.assertEqual(list((self.home / "artifacts").iterdir()), [])

    def test_unread_and_ack_reject_missing_or_mismatched_direct_index(self):
        for mode in ("missing", "mismatched"):
            with self.subTest(mode=mode):
                turn = self.turn(); self.assertEqual(self.settle(turn).returncode, 0)
                event = next(event for event in self.ok_json("inbox", "unread", "--watchtower", "main") if event["turn_id"] == turn)
                index = self.home / "inbox-index" / f"{event['event_id']}.json"
                if mode == "missing":
                    index.unlink()
                else:
                    value = json.loads(index.read_text()); value["generation"] += 1; index.write_text(json.dumps(value))
                self.assertEqual(self.cli("inbox", "unread", "--watchtower", "main").returncode, 5)
                before = json.loads((self.home / "inbox" / "main.json").read_text())["ack"]
                self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", str(event["generation"])).returncode, 5)
                self.assertEqual(json.loads((self.home / "inbox" / "main.json").read_text())["ack"], before)
                if mode == "missing":
                    index.write_text(json.dumps({"event_id": event["event_id"], "watchtower_id": "main", "generation": event["generation"]}))
                else:
                    value["generation"] -= 1; index.write_text(json.dumps(value))
                self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", str(event["generation"])).returncode, 0)

    def test_direct_index_generation_requires_strict_integer_for_all_consumers(self):
        for invalid in (True, "1", 1.5):
            with self.subTest(invalid=invalid):
                turn = self.turn(); self.assertEqual(self.settle(turn).returncode, 0)
                event = next(event for event in self.ok_json("inbox", "unread", "--watchtower", "main") if event["turn_id"] == turn)
                index = self.home / "inbox-index" / f"{event['event_id']}.json"
                value = json.loads(index.read_text()); original = value["generation"]; value["generation"] = invalid; index.write_text(json.dumps(value))
                commands = (
                    ("inbox", "unread", "--watchtower", "main"),
                    ("inbox", "pending", "--watchtower", "main"),
                    ("inbox", "handle", event["event_id"]),
                    ("ack", "--watchtower", "main", "--through", str(event["generation"])),
                )
                for command in commands:
                    self.assertEqual(self.cli(*command).returncode, 5, command)
                value["generation"] = original; index.write_text(json.dumps(value))
                self.assertEqual(self.cli("inbox", "handle", event["event_id"]).returncode, 0)
                self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", str(event["generation"])).returncode, 0)

    def test_ack_rejects_missing_terminal_and_intermediate_generations_without_advancing(self):
        first = self.turn(); self.assertEqual(self.settle(first).returncode, 0)
        generation_one = self.home / "inbox-events" / f"main--{1:020d}.json"
        saved = generation_one.read_bytes(); generation_one.unlink()
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "1").returncode, 5)
        self.assertEqual(json.loads((self.home / "inbox" / "main.json").read_text())["ack"], 0)
        generation_one.write_bytes(saved)
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        (self.home / "inbox-events" / f"main--{2:020d}.json").unlink()
        self.assertEqual(self.cli("ack", "--watchtower", "main", "--through", "3").returncode, 5)
        self.assertEqual(json.loads((self.home / "inbox" / "main.json").read_text())["ack"], 0)

    def test_settlement_rejects_invalid_mailbox_order_before_commit(self):
        self.assertEqual(self.settle(self.turn()).returncode, 0)
        path = next((self.home / "inbox-events").iterdir())
        event = json.loads(path.read_text())
        event["generation"] = 3
        replacement = path.with_name(f"main--{3:020d}.json")
        path.rename(replacement)
        replacement.write_text(json.dumps(event))
        box = self.home / "inbox" / "main.json"
        state = json.loads(box.read_text()); state["highest"] = 3; box.write_text(json.dumps(state))
        turn = self.turn()
        self.assertEqual(self.settle(turn).returncode, 5)
        self.assertEqual(self.ok_json("turn", "show", turn)["state"], "running")

    def test_inbox_fails_closed_for_missing_terminal_turn_or_artifact(self):
        turn = self.turn()
        self.assertEqual(self.settle(turn, "--stdin", input="evidence").returncode, 0)
        turn_path = self.home / "turns" / f"{turn}.json"
        saved = turn_path.read_bytes(); turn_path.unlink()
        for command in (("inbox", "unread"), ("inbox", "pending")):
            self.assertEqual(self.cli(*command, "--watchtower", "main").returncode, 5)
        turn_path.write_bytes(saved)
        (self.home / "artifacts" / f"{turn}--stdin.json").unlink()
        for command in (("inbox", "unread"), ("inbox", "pending")):
            self.assertEqual(self.cli(*command, "--watchtower", "main").returncode, 5)

    def test_concurrent_settlements_have_unique_ordered_generations(self):
        turns = [self.turn() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda turn: run_cli(self.home, "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done"), turns))
        self.assertTrue(all(item.returncode == 0 for item in results), [item.stderr for item in results])
        events = self.ok_json("inbox", "unread", "--watchtower", "main")
        self.assertEqual([e["generation"] for e in events], list(range(1, 13)))
        self.assertEqual(len({e["event_id"] for e in events}), 12)
        self.assertEqual({e["turn_id"] for e in events}, set(turns))


class MissingM1ObjectsHaveNoSideEffects(CliCase):
    def test_missing_commands_do_not_create_home(self):
        commands = (
            ("inbox", "unread", "--watchtower", "main"),
            ("inbox", "pending", "--watchtower", "main"),
            ("ack", "--watchtower", "main", "--through", "1"),
            ("inbox", "handle", "evt-" + "0" * 32),
            ("artifact", "path", "artifact:00000000-0000-4000-8000-000000000000:stdin"),
            ("turn", "settle", "00000000-0000-4000-8000-000000000000", "--source", "x", "--status", "completed", "--message", "done"),
        )
        for command in commands:
            with self.subTest(command=command):
                result = self.cli(*command)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(self.home.exists())
