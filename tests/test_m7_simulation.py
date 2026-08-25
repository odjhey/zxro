import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


class ProviderFreeM7SimulationTests(unittest.TestCase):
    def run_simulation(self, evidence: Path):
        return subprocess.run(
            [str(ROOT / "bin" / "zxro-m7-sim"), "--evidence", str(evidence)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    @staticmethod
    def behavior(report):
        return {
            "environment": report["environment"],
            "turns": [
                {
                    key: turn[key]
                    for key in (
                        "ordinal",
                        "stage",
                        "target",
                        "target_cwd_is_separate",
                        "state",
                        "outcome",
                        "summary",
                        "artifact_count",
                    )
                }
                for turn in report["turns"]
            ],
            "wake_and_reconciliation": [
                {
                    "turn_ordinal": item["turn_ordinal"],
                    "dropped_wake_count": len(item["dropped_wake"]),
                    "duplicate_wake_count": item["duplicate_wake_count"],
                    "poll_handled": item["poll_after_dropped_wake"]["handled_expected_turn"],
                    "stage_released": item["stage_released_after_handling"],
                    "wake_handled": [
                        check["reconcile"]["handled_expected_turn"]
                        for check in item["wake_reconciliations"]
                    ],
                }
                for item in report["wake_and_reconciliation"]
            ],
            "stop_conditions": report["stop_conditions"],
            "cleanup": report["cleanup"],
        }

    def test_public_cli_simulation_is_bounded_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "first.json"
            second_path = Path(temporary) / "second.json"
            first = self.run_simulation(first_path)
            second = self.run_simulation(second_path)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_report = json.loads(first_path.read_text())
            second_report = json.loads(second_path.read_text())

        self.assertEqual(first_report["result"], "passed")
        self.assertEqual(self.behavior(first_report), self.behavior(second_report))
        self.assertEqual(first_report["environment"]["target_cwds"], ["repo-a", "repo-b"])
        self.assertEqual(first_report["environment"]["watchtower_cwd"], "watchtower")
        self.assertFalse(first_report["environment"]["network"])
        self.assertFalse(first_report["environment"]["credentials"])
        self.assertFalse(first_report["environment"]["billable_calls"])

        turns = first_report["turns"]
        self.assertEqual([turn["stage"] for turn in turns], ["coder-a", "reviewer-a", "coder-b", "tester-b"])
        self.assertEqual([turn["target"] for turn in turns], ["repo-a", "repo-a", "repo-b", "repo-b"])
        self.assertTrue(all(turn["target_cwd_is_separate"] for turn in turns))
        self.assertTrue(all(turn["state"] == "settled" for turn in turns))
        self.assertEqual([turn["runtime_evidence"]["runtime"] for turn in turns], ["fake-runtime"] * 4)

        wake = first_report["wake_and_reconciliation"]
        self.assertEqual(len(wake[0]["dropped_wake"]), 2)
        self.assertEqual(wake[0]["duplicate_wake_count"], 0)
        self.assertTrue(wake[0]["poll_after_dropped_wake"]["handled_expected_turn"])
        self.assertTrue(all(item["stage_released_after_handling"] for item in wake))
        for item in wake[1:]:
            self.assertEqual(item["dropped_wake"], [])
            self.assertEqual(item["duplicate_wake_count"], 2)
            self.assertEqual(item["wake_reconciliations"][0]["reconcile"]["handled_expected_turn"], True)
            self.assertEqual(item["wake_reconciliations"][1]["reconcile"]["handled_expected_turn"], False)

        stop = first_report["stop_conditions"]
        self.assertEqual(stop["turn_count"], 4)
        self.assertEqual(stop["bounded_by"], 4)
        self.assertEqual(stop["final_work_state"], "closed")
        self.assertTrue(stop["new_turn_after_close_rejected"])
        self.assertTrue(stop["terminal_retry_after_close"])
        self.assertEqual(stop["unread_after_close"], 0)
        self.assertEqual(stop["pending_after_close"], 0)
        self.assertTrue(first_report["cleanup"]["fake_runtime_processes_reaped"])
        self.assertTrue(first_report["cleanup"]["temporary_home_removed"])

    def test_evidence_contains_durable_settlements_and_handled_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.json"
            result = self.run_simulation(evidence)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(evidence.read_text())

        records = [item for item in report["durable_evidence"] if "json" in item]
        events = [item["json"] for item in records if item["path"].startswith("inbox-events/")]
        turns = [item["json"] for item in records if item["path"].startswith("turns/")]
        handled = [item for item in records if item["path"].startswith("inbox-handled/")]
        self.assertEqual([event["generation"] for event in events], [1, 2, 3, 4])
        self.assertEqual(len({event["event_id"] for event in events}), 4)
        self.assertEqual(len(turns), 4)
        self.assertTrue(all(turn["state"] == "settled" for turn in turns))
        self.assertEqual(len(handled), 4)
        mailbox = next(item["json"] for item in records if item["path"] == "inbox/m7-sim-watchtower.json")
        self.assertEqual(mailbox["ack"], 4)
        self.assertEqual(mailbox["highest"], 4)
        self.assertEqual(mailbox["unresolved"], [])
        self.assertTrue(any(item["path"] == "work/m7-sim-work.json" and item["json"]["state"] == "closed" for item in records))


if __name__ == "__main__":
    unittest.main()
