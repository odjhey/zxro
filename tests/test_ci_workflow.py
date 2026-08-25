import re
from pathlib import Path
from unittest import TestCase


class CiWorkflowTests(TestCase):
    def test_test_matrix_uses_only_python_311(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text()
        python_matrix = re.search(r"^\s+python:\s*\[(.*)]$", workflow, re.MULTILINE)

        self.assertIsNotNone(python_matrix)
        self.assertEqual(python_matrix.group(1).strip(), "'3.11'")
        self.assertIn("python-version: ${{ matrix.python }}", workflow)
