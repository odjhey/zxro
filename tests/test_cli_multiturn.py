import json
import subprocess

from helpers import BIN, ROOT, CliCase


class MultiTurnOperatorFlowTests(CliCase):
    """One public-CLI-only work lifecycle across independent processes."""

    def create_turn(self, role, sequence):
        result = self.cli(
            "turn", "create", "--work", "release-fix", "--agent", "manual",
            "--session", f"{role}-{sequence}", "--cwd", f"/tmp/{role}-{sequence}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def settle(self, turn, status, message, payload=None):
        args = [
            str(BIN), "turn", "settle", turn, "--source", "manual",
            "--status", status, "--message", message,
        ]
        if payload is not None:
            args.append("--stdin")
        return subprocess.run(
            args,
            cwd=ROOT,
            env={**__import__("os").environ, "ZXRO_HOME": str(self.home)},
            input=payload,
            text=True,
            capture_output=True,
        )

    def test_complete_multiturn_lifecycle_survives_restart_and_retry(self):
        self.assertEqual(
            self.cli("watchtower", "create", "ops", "--cwd", "/tmp/operator").returncode,
            0,
        )
        self.assertEqual(
            self.cli("work", "create", "release-fix", "--watchtower", "ops").returncode,
            0,
        )

        turns = []
        stages = (
            ("coder", "completed", "Patch ready for review.", "diff summary\nfiles: 2\n"),
            ("reviewer", "failed", "Review process exited before a verdict.", "reviewer exit 17\n"),
            ("reviewer", "completed", "Review found one blocking validation bug.", "BLOCKER: reject empty token\n"),
            ("coder", "completed", "Validation bug fixed; focused tests pass.", "tests: 14 passed\n"),
            ("tester", "completed", "Regression suite passed; ready to close.", "suite: pass\n"),
        )
        for sequence, (role, status, message, payload) in enumerate(stages, 1):
            turn = self.create_turn(role, sequence)
            turns.append(turn)
            result = self.settle(turn, status, message, payload)
            self.assertEqual(result.returncode, 0, result.stderr)

            # Each read starts a fresh CLI process, which proves persisted state is sufficient.
            shown = self.ok_json("turn", "show", turn)
            self.assertEqual(shown["outcome"], status)
            self.assertEqual(shown["summary"], message)
            self.assertEqual(len(shown["artifact_refs"]), 1)
            artifact = self.cli("artifact", "path", shown["artifact_refs"][0])
            self.assertEqual(artifact.returncode, 0, artifact.stderr)
            self.assertEqual(__import__("pathlib").Path(artifact.stdout.strip()).read_text(), payload)

        unread = self.ok_json("inbox", "unread", "--watchtower", "ops")
        self.assertEqual([event["generation"] for event in unread], [1, 2, 3, 4, 5])
        self.assertEqual([event["outcome"] for event in unread], [stage[1] for stage in stages])
        self.assertTrue(all("BLOCKER:" not in json.dumps(event) for event in unread))

        retry = self.settle(turns[-1], "completed", stages[-1][2])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        conflict = self.settle(turns[-1], "failed", "changed terminal result")
        self.assertEqual(conflict.returncode, 4)
        self.assertEqual(len(self.ok_json("inbox", "unread", "--watchtower", "ops")), 5)

        self.assertEqual(self.cli("ack", "--watchtower", "ops", "--through", "5").returncode, 0)
        self.assertEqual(self.ok_json("inbox", "unread", "--watchtower", "ops"), [])
        self.assertEqual(
            [event["generation"] for event in self.ok_json("inbox", "pending", "--watchtower", "ops")],
            [1, 2, 3, 4, 5],
        )

        for generation in (5, 2, 1, 3, 4):
            event_id = unread[generation - 1]["event_id"]
            self.assertEqual(self.cli("inbox", "handle", event_id).returncode, 0)
        self.assertEqual(self.cli("inbox", "handle", unread[0]["event_id"]).returncode, 0)
        self.assertEqual(self.ok_json("inbox", "pending", "--watchtower", "ops"), [])

        history = self.ok_json("turn", "list", "--work", "release-fix")
        self.assertEqual({turn["id"] for turn in history}, set(turns))
        outcomes = {turn["id"]: turn["outcome"] for turn in history}
        self.assertEqual([outcomes[turn] for turn in turns], [stage[1] for stage in stages])
        current = self.ok_json("work", "show", "release-fix")
        self.assertEqual(current["state"], "open")

        self.assertEqual(self.cli("work", "close", "release-fix").returncode, 0)
        self.assertEqual(self.cli("work", "close", "release-fix").returncode, 0)
        self.assertEqual(self.ok_json("work", "show", "release-fix")["state"], "closed")
        self.assertEqual(len(self.ok_json("turn", "list", "--work", "release-fix")), 5)
        self.assertEqual(self.ok_json("inbox", "pending", "--watchtower", "ops"), [])
