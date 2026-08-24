from pathlib import Path
from tests.helpers import CliCase, run_cli


class IsolationCliTests(CliCase):
    def test_homes_allow_same_ids_without_observation_or_mutation(self):
        second = Path(self.temp.name) / "second"
        for home, cwd in ((self.home, "/one"), (second, "/two")):
            run_cli(home, "watchtower", "create", "main", "--cwd", cwd)
            run_cli(home, "work", "create", "same", "--watchtower", "main")
        run_cli(self.home, "work", "close", "same")
        self.assertIn('state: closed', run_cli(self.home, "work", "show", "same").stdout)
        self.assertIn('state: open', run_cli(second, "work", "show", "same").stdout)
        self.assertIn('/one', run_cli(self.home, "watchtower", "show", "main").stdout)
        self.assertIn('/two', run_cli(second, "watchtower", "show", "main").stdout)
