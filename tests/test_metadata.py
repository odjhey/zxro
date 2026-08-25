import json
import unittest

from zxro.errors import ValidationError
from zxro.metadata import MAX_METADATA_BYTES, validate_metadata, validate_namespace


class MetadataValidationTests(unittest.TestCase):
    def test_names_and_reserved_namespace(self):
        self.assertEqual(validate_namespace("a" * 64, {"k": 1}), {"k": 1})
        for name in ("A", "-bad", "a" * 65, ".", "..", "has/slash", "zxro"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_namespace(name, {"k": 1})
        with self.assertRaises(ValidationError): validate_namespace("good", {"Bad": 1})

    def test_depth_limit_and_arrays(self):
        self.assertEqual(validate_namespace("ns", {"a": {"b": {"c": {"d": 1}}}}), {"a": {"b": {"c": {"d": 1}}}})
        with self.assertRaises(ValidationError): validate_namespace("ns", {"a": {"b": {"c": {"d": {"e": 1}}}}})
        self.assertEqual(validate_namespace("ns", {"a": ["x", 1, True]}), {"a": ["x", 1, True]})
        for value in ([{}], [[1]], [None], [1.0], None, 1.0):
            with self.subTest(value=value), self.assertRaises(ValidationError): validate_namespace("ns", {"a": value})

    def test_strings_are_normalized_then_bounded(self):
        self.assertEqual(validate_namespace("ns", {"k": "e\u0301"}), {"k": "é"})
        self.assertEqual(len(validate_namespace("ns", {"k": "x" * 2048})["k"]), 2048)
        with self.assertRaises(ValidationError): validate_namespace("ns", {"k": "x" * 2049})
        with self.assertRaises(ValidationError): validate_metadata({"ns": {"k": "e\u0301"}}, normalize=False)

    def test_total_canonical_utf8_size_limit(self):
        payload = {f"k{i}": "x" * 2048 for i in range(7)}
        value = {"n": payload}
        payload["tail"] = ""
        current = len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        payload["tail"] = "x" * (MAX_METADATA_BYTES - current)
        encoded = json.dumps(validate_metadata(value), sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(len(encoded), MAX_METADATA_BYTES)
        payload["tail"] += "x"
        with self.assertRaises(ValidationError): validate_metadata(value)
