from itertools import product
from pathlib import Path
from unittest import TestCase


def _strip_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_strip_scalar(item) for item in inner.split(",")] if inner else []
    return value


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _consume_mapping(lines, pos, indent, mapping, first_content=None):
    first = first_content is not None
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        cur_indent = _indent_of(lines[pos])
        if first:
            key, _, rest = first_content.partition(":")
            pos += 1
        else:
            if cur_indent != indent or lines[pos].lstrip().startswith("- "):
                break
            key, _, rest = lines[pos].strip().partition(":")
            pos += 1
        rest = rest.strip()
        if rest:
            mapping[key.strip()] = _strip_scalar(rest)
        else:
            nested, pos = _parse_block(lines, pos, indent + 2)
            mapping[key.strip()] = nested
        first = False
    return pos


def _parse_block(lines, pos, indent):
    while pos < len(lines) and not lines[pos].strip():
        pos += 1
    if pos >= len(lines) or _indent_of(lines[pos]) < indent:
        return None, pos

    if not lines[pos].lstrip().startswith("- "):
        mapping = {}
        pos = _consume_mapping(lines, pos, indent, mapping)
        return mapping, pos

    items = []
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        cur_indent = _indent_of(lines[pos])
        if cur_indent < indent or not lines[pos].lstrip().startswith("- "):
            break
        content = lines[pos].lstrip()[2:]
        sub_indent = cur_indent + 2
        if ":" in content and not content.lstrip().startswith(("'", '"', "[")):
            entry = {}
            pos = _consume_mapping(lines, pos, sub_indent, entry, first_content=content)
            items.append(entry)
        else:
            items.append(_strip_scalar(content))
            pos += 1
    return items, pos


def parse_yaml(text):
    """Parse the small block-YAML subset used by GitHub Actions workflows in this repo."""
    document, _ = _parse_block(text.splitlines(), 0, 0)
    return document


def expand_matrix(matrix):
    """Return the effective jobs produced by a GitHub Actions matrix."""
    dimensions = {key: values for key, values in matrix.items() if key not in {"include", "exclude"}}
    keys = list(dimensions)
    original = [dict(zip(keys, values)) for values in product(*(dimensions[key] for key in keys))]
    expanded = [entry.copy() for entry in original]

    for addition in matrix.get("include", []):
        matched = False
        for index, base in enumerate(original):
            if all(key not in base or base[key] == value for key, value in addition.items()):
                expanded[index].update(addition)
                matched = True
        if not matched:
            expanded.append(addition.copy())

    for removal in matrix.get("exclude", []):
        expanded = [
            entry
            for entry in expanded
            if not all(entry.get(key) == value for key, value in removal.items())
        ]

    return expanded


class CiWorkflowTests(TestCase):
    def setUp(self):
        workflow_text = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text()
        self.workflow = parse_yaml(workflow_text)

    def test_effective_matrix_uses_python_311_on_required_operating_systems(self):
        matrix = self.workflow["jobs"]["test"]["strategy"]["matrix"]
        jobs = expand_matrix(matrix)

        self.assertEqual(
            {(job["os"], job["python"]) for job in jobs},
            {("ubuntu-latest", "3.11"), ("macos-latest", "3.11")},
        )
        self.assertTrue(all(job["python"] == "3.11" for job in jobs))
        self.assertEqual(self.workflow["jobs"]["test"]["runs-on"], "${{ matrix.os }}")

    def test_setup_python_step_consumes_matrix_python(self):
        steps = self.workflow["jobs"]["test"]["steps"]
        setup_steps = [step for step in steps if step.get("uses", "").startswith("actions/setup-python")]

        self.assertEqual(len(setup_steps), 1)
        self.assertEqual(setup_steps[0]["with"]["python-version"], "${{ matrix.python }}")

    def test_test_job_runs_full_unittest_suite(self):
        steps = self.workflow["jobs"]["test"]["steps"]
        run_commands = [step["run"] for step in steps if "run" in step]

        self.assertIn("python3 -m unittest discover -s tests -v", run_commands)
