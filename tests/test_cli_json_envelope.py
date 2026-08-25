import json
import os
import subprocess

from tests.helpers import BIN, ROOT, CliCase


class JsonEnvelopeTests(CliCase):
    def assert_envelope(self, result, expected_type):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        envelope = json.loads(result.stdout)
        self.assertEqual(set(envelope), {"schema_version", "data"})
        self.assertEqual(envelope["schema_version"], 1)
        self.assertIs(type(envelope["schema_version"]), int)
        self.assertIsInstance(envelope["data"], expected_type)
        self.assertEqual(result.stdout, json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n")
        return envelope["data"]

    def test_representative_object_and_list_wire_results(self):
        self.seed()
        shown = self.cli("--json", "watchtower", "show", "main")
        self.assertEqual(shown.stdout, self.cli("--json", "watchtower", "show", "main").stdout)
        self.assert_envelope(shown, dict)
        self.assert_envelope(self.cli("--json", "work", "show", "job"), dict)
        self.assert_envelope(self.cli("--json", "work", "list"), list)

        created = self.assert_envelope(
            self.cli("--json", "turn", "create", "--work", "job", "--agent", "pi", "--session", "crew", "--cwd", "/tmp"),
            dict,
        )
        turn_id = created["id"]
        settled = self.assert_envelope(
            subprocess.run(
                [str(BIN), "--json", "turn", "settle", turn_id, "--source", "manual", "--status", "completed", "--message", "done", "--stdin"],
                cwd=ROOT,
                env={**os.environ, "ZXRO_HOME": str(self.home)},
                input="evidence",
                text=True,
                capture_output=True,
            ),
            dict,
        )
        ref = settled["artifact_refs"][0]
        unread = self.assert_envelope(self.cli("--json", "inbox", "unread", "--watchtower", "main"), list)
        self.assert_envelope(self.cli("--json", "ack", "--watchtower", "main", "--through", "1"), dict)
        self.assert_envelope(self.cli("--json", "inbox", "pending", "--watchtower", "main"), list)
        self.assert_envelope(self.cli("--json", "inbox", "handle", unread[0]["event_id"]), dict)
        path = self.assert_envelope(self.cli("--json", "artifact", "path", ref), dict)
        self.assertIn("path", path)
