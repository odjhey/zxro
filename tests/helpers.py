import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin" / "zxro"


def run_cli(home, *args, module=False, env=None):
    command = [sys.executable, "-m", "zxro"] if module else [str(BIN)]
    environment = os.environ.copy()
    environment["ZXRO_HOME"] = str(home)
    if env:
        environment.update(env)
    return subprocess.run(command + list(args), cwd=ROOT, env=environment, text=True, capture_output=True)


class CliCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, **kwargs):
        return run_cli(self.home, *args, **kwargs)

    def ok_json(self, *args):
        result = self.cli("--json", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        value = json.loads(result.stdout)
        if isinstance(value, dict) and set(value) == {"schema_version", "data"}:
            self.assertEqual(value["schema_version"], 1)
            return value["data"]
        return value

    def seed(self):
        self.assertEqual(self.cli("watchtower", "create", "main", "--cwd", "/watchtower", "--agent", "pi", "--session", "wt").returncode, 0)
        self.assertEqual(self.cli("work", "create", "job", "--watchtower", "main").returncode, 0)
