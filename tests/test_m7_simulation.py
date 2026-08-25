import json
import os
import subprocess
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
            "repositories": [
                {key: item[key] for key in ("label", "cwd", "is_git_repository")}
                for item in report["repository_evidence"]
            ],
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
        self.assertTrue(all(first_report["contract_predicates"].values()))
        self.assertEqual(self.behavior(first_report), self.behavior(second_report))
        self.assertEqual(first_report["environment"]["target_cwds"], ["repo-a", "repo-b"])
        self.assertEqual(first_report["environment"]["watchtower_cwd"], "watchtower")
        self.assertFalse(first_report["environment"]["network_calls"])
        self.assertFalse(first_report["environment"]["billable_calls"])
        self.assertFalse(first_report["environment"]["provider_credentials_in_children"])
        self.assertFalse(first_report["environment"]["provider_config_in_children"])
        self.assertEqual(first_report["environment"]["child_environment"], "explicit-safe-whitelist")
        self.assertEqual(first_report["repository_evidence"][0]["cwd"], "repo-a")
        self.assertEqual(first_report["repository_evidence"][1]["cwd"], "repo-b")
        self.assertTrue(all(item["is_git_repository"] for item in first_report["repository_evidence"]))
        self.assertTrue(all(item["head"] for item in first_report["repository_evidence"]))

        turns = first_report["turns"]
        self.assertEqual([turn["stage"] for turn in turns], ["coder-a", "reviewer-a", "coder-b", "tester-b"])
        self.assertEqual([turn["target"] for turn in turns], ["repo-a", "repo-a", "repo-b", "repo-b"])
        self.assertTrue(all(turn["target_cwd_is_separate"] for turn in turns))
        self.assertTrue(all(turn["durable_cwd"] == turn["expected_target_cwd"] for turn in turns))
        self.assertEqual(len({turn["durable_cwd"] for turn in turns}), 2)
        self.assertTrue(all(turn["state"] == "settled" for turn in turns))
        self.assertTrue(all(turn["retry_preserved_event_id"] for turn in turns))
        public_refs = [ref for turn in turns for ref in turn["public_artifact_refs"]]
        self.assertEqual(len(public_refs), 4)
        self.assertEqual(len(set(public_refs)), 4)
        self.assertEqual([turn["runtime_evidence"]["runtime"] for turn in turns], ["fake-runtime"] * 4)
        self.assertTrue(all(turn["runtime_evidence"]["forbidden_provider_keys"] == [] for turn in turns))
        self.assertTrue(all(turn["runtime_evidence"]["private_config_home"] for turn in turns))
        self.assertTrue(all(turn["runtime_evidence"]["git_repository"] for turn in turns))

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

    def test_inherited_provider_environment_is_not_passed_to_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.json"
            environment = os.environ.copy()
            environment.update(
                {
                    "ANTHROPIC_API_KEY": "must-not-leak",
                    "CLAUDE_CONFIG_DIR": "/secret/claude",
                    "ACPX_TOKEN": "must-not-leak",
                    "PI_CONFIG_DIR": "/secret/pi",
                    "OPENAI_API_KEY": "must-not-leak",
                }
            )
            result = subprocess.run(
                [str(ROOT / "bin" / "zxro-m7-sim"), "--evidence", str(evidence)],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(evidence.read_text())
        self.assertFalse(report["environment"]["provider_credentials_in_children"])
        self.assertTrue(all(turn["runtime_evidence"]["forbidden_provider_keys"] == [] for turn in report["turns"]))
        self.assertTrue(all(turn["runtime_evidence"]["git_repository"] for turn in report["turns"]))

    def test_required_contract_faults_fail_closed_without_passed_output(self):
        for fault in ("stop-condition", "provider-environment", "repository", "durable-cwd", "artifact-refs", "swapped-refs", "wrong-artifact-owner", "empty-public-refs"):
            with self.subTest(fault=fault):
                result = subprocess.run(
                    [str(ROOT / "bin" / "zxro-m7-sim"), "--fault", fault],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('"result": "passed"', result.stdout)
                self.assertIn("required simulation predicates failed", result.stderr)

    def test_evidence_contains_durable_settlements_and_handled_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.json"
            result = self.run_simulation(evidence)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(evidence.read_text())

        records = [item for item in report["durable_evidence"] if "json" in item]
        events = [item["json"] for item in records if item["path"].startswith("inbox-events/")]
        turns = [item["json"] for item in records if item["path"].startswith("turns/")]
        artifacts = [item["json"] for item in records if item["path"].startswith("artifacts/")]
        handled = [item for item in records if item["path"].startswith("inbox-handled/")]
        self.assertEqual([event["generation"] for event in events], [1, 2, 3, 4])
        self.assertEqual(len({event["event_id"] for event in events}), 4)
        self.assertEqual(len(turns), 4)
        self.assertTrue(all(turn["state"] == "settled" for turn in turns))
        self.assertEqual(len(artifacts), 4)
        artifact_refs = {artifact["ref"] for artifact in artifacts}
        self.assertTrue(all(turn["artifact_refs"] and set(turn["artifact_refs"]).issubset(artifact_refs) for turn in turns))
        self.assertTrue(all(turn["artifact_refs"] == turn["public_artifact_refs"] for turn in report["turns"]))
        self.assertTrue(all(artifact["content_hex"] and artifact["bytes"] > 0 for artifact in artifacts))
        self.assertEqual(len(handled), 4)
        mailbox = next(item["json"] for item in records if item["path"] == "inbox/m7-sim-watchtower.json")
        self.assertEqual(mailbox["ack"], 4)
        self.assertEqual(mailbox["highest"], 4)
        self.assertEqual(mailbox["unresolved"], [])
        self.assertTrue(any(item["path"] == "work/m7-sim-work.json" and item["json"]["state"] == "closed" for item in records))


if __name__ == "__main__":
    unittest.main()
