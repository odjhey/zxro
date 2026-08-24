import json
import stat
from pathlib import Path

from tests.helpers import CliCase, BIN


class GlobalCliTests(CliCase):
    def test_entrypoints_have_parity_and_executable_shim(self):
        self.assertTrue(BIN.stat().st_mode & stat.S_IXUSR)
        direct = self.cli("--json", "watchtower", "list")
        module = self.cli("--json", "watchtower", "list", module=True)
        self.assertEqual((direct.returncode, direct.stdout, direct.stderr), (module.returncode, module.stdout, module.stderr))

    def test_json_success_is_exactly_one_value(self):
        self.seed()
        result = self.cli("--json", "work", "show", "job")
        self.assertEqual(json.loads(result.stdout)["id"], "job")
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertEqual(result.stderr, "")

    def test_home_flag_overrides_environment(self):
        other = Path(self.temp.name) / "other"
        result = self.cli("--home", str(other), "watchtower", "create", "other", "--cwd", "/x")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / "watchtowers" / "other.json").exists())
        self.assertTrue((other / "watchtowers" / "other.json").exists())

    def test_environment_home_overrides_default(self):
        result = self.cli("watchtower", "create", "main", "--cwd", "/x")
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.home / "watchtowers" / "main.json").exists())

    def test_unknown_parents_on_fresh_home_have_zero_physical_side_effects(self):
        work = self.cli("work", "create", "orphan", "--watchtower", "missing")
        self.assertEqual(work.returncode, 3)
        self.assertFalse(self.home.exists())
        turn = self.cli("turn", "create", "--work", "missing", "--agent", "pi", "--session", "s", "--cwd", "/crew")
        self.assertEqual(turn.returncode, 3)
        self.assertFalse(self.home.exists())

    def test_errors_have_stable_codes_stderr_and_no_json_stdout(self):
        invalid = self.cli("--json", "watchtower", "show", "../bad")
        missing = self.cli("--json", "watchtower", "show", "missing")
        self.seed(); conflict = self.cli("--json", "work", "create", "job", "--watchtower", "main")
        (self.home / "work" / "job.json").write_text("{")
        malformed = self.cli("--json", "work", "show", "job")
        self.assertEqual([invalid.returncode, missing.returncode, conflict.returncode, malformed.returncode], [2, 3, 4, 5])
        for result in (invalid, missing, conflict, malformed):
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr)
