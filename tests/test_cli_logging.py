import contextlib
import concurrent.futures
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import BIN, CliCase, ROOT, run_cli
from zxro import cli, diagnostics
from zxro.localfs import durable


class StructuredLoggingCliTests(CliCase):
    def events(self, *args, env=None):
        result = self.cli("--log-format", "jsonl", "--log-level", "debug", *args, env=env)
        self.assertTrue(result.stderr, result)
        return result, [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]

    def test_every_public_command_class_has_a_terminal_event(self):
        def invoke(*args, input=None):
            if input is None:
                result = self.cli("--log-level", "info", "--log-format", "jsonl", *args)
            else:
                result = subprocess.run(
                    [str(BIN), "--log-level", "info", "--log-format", "jsonl", *args],
                    cwd=ROOT,
                    env={**os.environ, "ZXRO_HOME": str(self.home)},
                    input=input,
                    text=True,
                    capture_output=True,
                )
            self.assertTrue(result.stderr, args)
            events = [json.loads(line) for line in result.stderr.splitlines()]
            self.assertEqual(events[-1]["event_name"], "zxro.cli.invocation.completed", args)
            self.assertEqual(events[-1]["attributes"]["process_exit_code"], result.returncode, args)
            return result

        invoke("watchtower", "create", "main", "--cwd", "/watchtower")
        invoke("watchtower", "show", "main")
        invoke("watchtower", "list")
        invoke("work", "create", "job", "--watchtower", "main")
        invoke("work", "show", "job")
        invoke("work", "list")
        invoke("work", "meta", "set", "job", "runtime", "--stdin", input='{"safe":true}')
        invoke("work", "meta", "show", "job", "runtime")
        invoke("work", "meta", "unset", "job", "runtime")
        invoke("work", "brief", "set", "job", "--stdin", input="brief evidence")
        invoke("work", "brief", "path", "job")
        invoke("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew")
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "artifact", "--cwd", "/crew").stdout.strip()
        invoke("turn", "show", turn)
        invoke("turn", "list")
        invoke("turn", "bind", turn, "--native-session-id", "native-secret", "--source", "runtime-secret")
        invoke("artifact", "put", turn, "--kind", "report", "--stdin", input="artifact evidence")
        invoke("artifact", "path", f"artifact:{turn}:report")
        invoke("turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done", "--stdin", input="evidence")
        event = self.ok_json("inbox", "unread", "--watchtower", "main")[0]
        invoke("inbox", "unread", "--watchtower", "main")
        invoke("inbox", "pending", "--watchtower", "main")
        invoke("ack", "--watchtower", "main", "--through", "1")
        invoke("inbox", "handle", event["event_id"])
        invoke("artifact", "path", event["artifact_refs"][0])
        invoke("work", "close", "job")

    def test_parser_failure_preserves_argparse_output_and_emits_terminal_event(self):
        result, events = self.events("watchtower")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(all(line.startswith("{") for line in result.stderr.splitlines()))
        self.assertIn("usage:", json.dumps(events))
        self.assertEqual(sum(event["event_name"] == "zxro.cli.invocation.completed" for event in events), 1)
        self.assertEqual(events[-1]["attributes"], {"error_code": "argparse_error", "process_exit_code": 2})
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))

    def test_parser_diagnostic_redacts_unknown_argument_values(self):
        result, events = self.events("watchtower", "--unknown", "Bearer parser-secret", "/private/parser-path")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("parser-secret", result.stderr)
        self.assertNotIn("/private/parser-path", result.stderr)
        self.assertIn("usage:", json.dumps(events))

    def test_direct_event_attributes_redact_nested_and_mixed_paths_in_both_formats(self):
        payload = {
            "path": "relative/private.txt",
            "absolute": "/private/top-level",
            "windows": r"C:\private\windows.txt",
            "plain_unc": r"\\server\share\unc-secret.txt",
            "plain_unix_colon": "prefix:/private/colon-secret.txt",
            "pathKey": "relative/camel-secret.txt",
            "output.path": "relative/dot-secret.txt",
            "nested": [
                {"cwd": Path("/private/nested"), "mixed": ["/private/list", {"file": "relative/file.txt"}]},
                {"arbitrary": ["prefix:/private/deep-colon.txt", r"\\server\share\deep-unc.txt"]},
                "Bearer nested-secret",
            ],
            "mixed": (Path("relative/tuple"), {"value": "/private/deep"}),
            "/private/key": "key-value",
        }
        outputs = {}
        for format_name in ("jsonl", "human"):
            stream = io.StringIO()
            logger = diagnostics.DiagnosticLogger(diagnostics.LogConfig("info", format_name), self.home, stream=stream)
            logger.emit("zxro.test.arbitrary.payload", attributes=payload)
            output = stream.getvalue()
            outputs[format_name] = output
            self.assertLessEqual(len(output.encode("utf-8")), diagnostics.MAX_EVENT_BYTES)
            for secret in ("/private", "relative/private.txt", "relative/file.txt", "relative/tuple", "windows.txt", "nested-secret", "unc-secret.txt", "camel-secret.txt", "dot-secret.txt", "deep-colon.txt", "deep-unc.txt"):
                self.assertNotIn(secret, output)

        json_event = json.loads(outputs["jsonl"])
        human_attributes = json.loads(outputs["human"].rstrip("\n").rsplit(" ", 1)[-1])
        self.assertEqual(human_attributes, json_event["attributes"])
        self.assertEqual(json_event["attributes"]["path"], "[PATH]")
        self.assertEqual(json_event["attributes"]["nested"][0]["cwd"], "[PATH]")

    def test_non_finite_numbers_normalize_to_strict_json_in_both_formats(self):
        payload = {"nan": float("nan"), "pos": float("inf"), "neg": float("-inf"), "safe": 1.25}
        outputs = {}
        for format_name in ("jsonl", "human"):
            stream = io.StringIO()
            logger = diagnostics.DiagnosticLogger(diagnostics.LogConfig("info", format_name), self.home, stream=stream)
            logger.emit("zxro.test.nonfinite", attributes=payload)
            output = stream.getvalue()
            outputs[format_name] = output
            if format_name == "jsonl":
                event = json.loads(output, parse_constant=lambda value: (_ for _ in ()).throw(AssertionError(value)))
            else:
                attributes = output.rstrip("\n").rsplit(" ", 1)[-1]
                event = {"attributes": json.loads(attributes, parse_constant=lambda value: (_ for _ in ()).throw(AssertionError(value)))}
            self.assertEqual(event["attributes"], {"nan": None, "neg": None, "pos": None, "safe": 1.25})
            self.assertLessEqual(len(output.encode("utf-8")), diagnostics.MAX_EVENT_BYTES)
        self.assertEqual(json.loads(outputs["jsonl"])["attributes"], json.loads(outputs["human"].rstrip("\n").rsplit(" ", 1)[-1]))

        stream = io.StringIO()
        logger = diagnostics.DiagnosticLogger(diagnostics.LogConfig("info", "jsonl"), self.home, stream=stream)
        with mock.patch.object(diagnostics, "_bounded", return_value={"bad": float("nan")}):
            logger.emit("zxro.test.nonfinite.fail-open", attributes={"ignored": True})
        self.assertEqual(stream.getvalue(), "")

    def test_unconditional_content_and_credential_policy_is_recursive_for_all_sinks(self):
        class LeakyObject:
            def __str__(self):
                return "password=stringified-secret /private/stringified-path"

        payload = {
            "prompt": "prompt-fixture-01",
            "dispatchKey": "safe-structural-value",
            "safeCollisions": {
                "nativeIdleTime": "safe-native-idle",
                "nativeIdeaCount": "safe-native-idea",
                "apiKeyboardLayout": "safe-api-keyboard",
                "apiKeynoteTheme": "safe-api-keynote",
                "clientSecretaryName": "safe-client-secretary",
                "clientSecretariatStatus": "safe-client-secretariat",
                "authHeaderlessMode": "safe-auth-headerless",
            },
            "generated": {
                "nativeIds": "native-ids-camel-fixture",
                "native_ids": "native-ids-snake-fixture",
                "native-ids": "native-ids-kebab-fixture",
                "native.ids": "native-ids-dot-fixture",
                "apikey": "apikey-joined-fixture",
                "APIKEY": "apikey-upper-fixture",
                "apiKeys": "apikey-plural-fixture",
                "authHeaders": "auth-headers-fixture",
                "AUTHHEADER": "authheader-upper-fixture",
                "clientsecret": "clientsecret-joined-fixture",
            },
            "keyVariants": {
                "APIKey": "apikey-acronym-fixture",
                "XApiKey": "xapi-acronym-fixture",
                "HTTPAuthorization": "http-auth-fixture",
                "authHeader": "auth-header-fixture",
            },
            "nested": {
                "clientSecret": "client-fixture-15",
                "headers": {
                    "Authorization": "Basic nested-fixture-16",
                    "Cookie": "nested-cookie-fixture-17",
                },
                "native.session.id": "nested-native-fixture-18",
                "api-key": "nested-key-fixture-19",
            },
            "safeText": "ordinary safe text",
            "nativeName": "safe-native-name",
            "apiStatus": "safe-api-status",
            "tokenizer": "tokenizer=ordinary-safe-value",
            "safeUrl": "https://example.test/safe",
            "summary": "summary-fixture-02",
            "stdin": "stdin-fixture-03",
            "stdout": "stdout-fixture-04",
            "environment": "env-fixture-05",
            "session": "session-fixture-06",
            "nativeSessionId": "native-fixture-07",
            "nativeId": "native-camel-fixture",
            "native_id": "native-snake-fixture",
            "native-id": "native-kebab-fixture",
            "native.id": "native-dot-fixture",
            "artifactBody": "artifact-fixture-08",
            "artifact": "artifact-fixture-08b",
            "artifactRef": "artifact-ref-safe",
            "password": "pw-fixture-09",
            "authorization": "Basic auth-fixture-10",
            "cookie": "sid=cookie-fixture-11",
            "apiKey": "key-fixture-12",
            "access_token": "token-fixture-13",
            "credential": "credential-fixture-14",
            "mixed": [LeakyObject(), {"payloadContent": "mixed-payload-fixture-20"}],
            "freeText": "token=token-eq-fixture; api key: api-space-fixture; client_secret=client-label-fixture; api.key=api-dot-label-fixture; auth header=auth-header-label-fixture; token_value=token-value-label-fixture; client_secret_value=client-secret-value-fixture; password_hash=password-hash-label-fixture",
        }
        generated_matrix = {
            "nativeIDs": "generated-nativeIDs-fixture",
            "native_id_value": "generated-native-id-value-fixture",
            "native-id-hash": "generated-native-id-hash-fixture",
            "api.keys": "generated-api-dot-fixture",
            "API_KEYS": "generated-api-keys-fixture",
            "auth.headers": "generated-auth-dot-fixture",
            "clientSecretValue": "generated-client-secret-value-fixture",
            "password_hash": "generated-password-hash-fixture",
        }
        payload["generated"].update(generated_matrix)
        fixtures = [
            "prompt-fixture-01", "summary-fixture-02", "stdin-fixture-03", "stdout-fixture-04", "env-fixture-05",
            "session-fixture-06", "native-fixture-07", "native-camel-fixture", "native-snake-fixture", "native-kebab-fixture", "native-dot-fixture", "native-ids-camel-fixture", "native-ids-snake-fixture", "native-ids-kebab-fixture", "native-ids-dot-fixture",
            "artifact-fixture-08", "pw-fixture-09", "auth-fixture-10",
            "cookie-fixture-11", "key-fixture-12", "token-fixture-13", "credential-fixture-14", "client-fixture-15",
            "nested-fixture-16", "nested-cookie-fixture-17", "nested-native-fixture-18", "nested-key-fixture-19",
            "mixed-payload-fixture-20", "artifact-fixture-08b", "token-eq-fixture", "api-space-fixture", "client-label-fixture",
            "apikey-acronym-fixture", "xapi-acronym-fixture", "http-auth-fixture", "auth-header-fixture", "apikey-joined-fixture", "apikey-upper-fixture", "apikey-plural-fixture", "auth-headers-fixture", "authheader-upper-fixture", "clientsecret-joined-fixture", "api-dot-label-fixture", "auth-header-label-fixture", "token-value-label-fixture", "client-secret-value-fixture", "password-hash-label-fixture", "stringified-secret", "/private/stringified-path",
        ] + list(generated_matrix.values())

        def attributes(format_name, output):
            if format_name == "jsonl":
                return json.loads(output)["attributes"]
            correlation_start = output.index(" correlation=")
            attributes_start = output.index(" {", correlation_start)
            return json.loads(output.rstrip("\n")[attributes_start + 1:])

        for sensitive in (False, True):
            for format_name in ("jsonl", "human"):
                with self.subTest(sensitive=sensitive, format=format_name):
                    outputs = []
                    stderr_stream = io.StringIO()
                    stderr_logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, sensitive=sensitive), self.home, stream=stderr_stream,
                    )
                    stderr_logger.emit("zxro.test.unconditional.policy", attributes=payload)
                    outputs.append(stderr_stream.getvalue())
                    log_dir = Path(self.temp.name) / f"policy-{sensitive}-{format_name}"
                    log_dir.mkdir(mode=0o700)
                    log_file = log_dir / "events.log"
                    file_logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, log_file, sensitive=sensitive), self.home,
                    )
                    file_logger.emit("zxro.test.unconditional.policy", attributes=payload)
                    outputs.append(log_file.read_text())
                    expected = attributes(format_name, outputs[0])
                    self.assertEqual(attributes(format_name, outputs[1]), expected)
                    for output in outputs:
                        for fixture in fixtures:
                            self.assertNotIn(fixture, output)
                        self.assertLessEqual(len(output.encode("utf-8")), diagnostics.MAX_EVENT_BYTES)
                    self.assertNotIn("prompt", expected)
                    self.assertNotIn("artifactBody", expected)
                    self.assertNotIn("artifact", expected)
                    for native_key in ("nativeId", "native_id", "native-id", "native.id"):
                        self.assertNotIn(native_key, expected)
                    for native_key in ("nativeIds", "native_ids", "native-ids", "native.ids"):
                        self.assertNotIn(native_key, expected["generated"])
                    for generated_key in generated_matrix:
                        if generated_key.startswith("native"):
                            self.assertNotIn(generated_key, expected["generated"])
                        else:
                            self.assertEqual(expected["generated"][generated_key], "[REDACTED]")
                    for credential_key in ("APIKey", "XApiKey", "HTTPAuthorization", "authHeader"):
                        self.assertEqual(expected["keyVariants"][credential_key], "[REDACTED]")
                    for credential_key in ("apikey", "APIKEY", "apiKeys", "authHeaders", "AUTHHEADER", "clientsecret"):
                        self.assertEqual(expected["generated"][credential_key], "[REDACTED]")
                    self.assertEqual(expected["artifactRef"], "artifact-ref-safe")
                    self.assertEqual(expected["safeCollisions"], {
                        "nativeIdleTime": "safe-native-idle",
                        "nativeIdeaCount": "safe-native-idea",
                        "apiKeyboardLayout": "safe-api-keyboard",
                        "apiKeynoteTheme": "safe-api-keynote",
                        "clientSecretaryName": "safe-client-secretary",
                        "clientSecretariatStatus": "safe-client-secretariat",
                        "authHeaderlessMode": "safe-auth-headerless",
                    })
                    self.assertEqual(expected["password"], "[REDACTED]")
                    self.assertEqual(expected["nested"]["headers"]["Authorization"], "[REDACTED]")
                    self.assertEqual(expected["safeText"], "ordinary safe text")
                    self.assertEqual(expected["nativeName"], "safe-native-name")
                    self.assertEqual(expected["apiStatus"], "safe-api-status")
                    self.assertEqual(expected["tokenizer"], "tokenizer=ordinary-safe-value")
                    self.assertEqual(expected["safeUrl"], "https://example.test/safe")
                    self.assertEqual(expected["dispatchKey"], "safe-structural-value")

    def test_held_out_security_corpus_across_format_sink_and_sensitive_modes(self):
        corpus = json.loads((ROOT / "tests" / "fixtures" / "g19-security-corpus.json").read_text())
        entries = []
        for item in corpus["held_out_prefix_cases"]:
            entries.extend(((item["key"], item["fixture"], item["oracle"]), (item["upper_key"], item["upper_fixture"], item["oracle"])))
        for group in ("position_boundary_cases", "safe_positives", "collision_controls"):
            entries.extend((item["key"], item["fixture"], item["oracle"]) for item in corpus[group])

        def decode(format_name, output):
            if format_name == "jsonl":
                return json.loads(output)["attributes"]
            start = output.index(" {", output.index(" correlation="))
            return json.loads(output.rstrip("\n")[start + 1:])

        for sensitive in (False, True):
            for format_name in ("human", "jsonl"):
                for batch_number, offset in enumerate(range(0, len(entries), 20)):
                    batch = entries[offset:offset + 20]
                    payload = {key: fixture for key, fixture, _ in batch}
                    payload["mixed"] = [b"held-out-bytes", {"safe": "nested-safe"}]
                    stream = io.StringIO()
                    logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, sensitive=sensitive), self.home, stream=stream,
                    )
                    logger.emit("zxro.test.held_out", attributes=payload)
                    directory = Path(self.temp.name) / f"held-out-{sensitive}-{format_name}-{batch_number}"
                    directory.mkdir(mode=0o700)
                    path = directory / "events.log"
                    file_logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, path, sensitive=sensitive), self.home,
                    )
                    file_logger.emit("zxro.test.held_out", attributes=payload)
                    stderr_attributes = decode(format_name, stream.getvalue())
                    file_attributes = decode(format_name, path.read_text())
                    self.assertEqual(stderr_attributes, file_attributes)
                    for key, fixture, oracle in batch:
                        if oracle == "omitted":
                            self.assertNotIn(key, stderr_attributes)
                        elif oracle == "redacted":
                            self.assertEqual(stderr_attributes.get(key), "[REDACTED]", key)
                        else:
                            self.assertEqual(stderr_attributes.get(key), fixture, key)
                        self.assertNotIn(fixture, stream.getvalue() if oracle != "preserved" else "")

    def test_generated_sensitive_grammar_matrix_and_collision_controls(self):
        roots = {
            "password": ("password",), "token": ("token",), "authorization": ("authorization",),
            "cookie": ("cookie",), "secret": ("secret",), "credential": ("credential",),
            "accessToken": ("access", "token"), "refreshToken": ("refresh", "token"),
            "apiKey": ("api", "key"), "authHeader": ("auth", "header"), "clientSecret": ("client", "secret"),
            "nativeId": ("native", "id"),
        }
        suffixes = ("", "value", "hash", "header", "values", "hashes")
        keys = set()
        for words in roots.values():
            for plural in (False, True):
                base_words = list(words)
                if plural:
                    base_words[-1] += "s"
                for suffix in suffixes:
                    parts = base_words + ([suffix] if suffix else [])
                    compact = "".join(parts).lower()
                    keys.update({compact, compact.upper()})
                    keys.add("_".join(parts).lower())
                    keys.add("-".join(parts).lower())
                    keys.add(".".join(parts).lower())
                    camel = parts[0].lower() + "".join(part[:1].upper() + part[1:] for part in parts[1:])
                    keys.update({camel, camel[:1].upper() + camel[1:]})
                    keys.add("prefix" + camel[:1].upper() + camel[1:] + "Suffix")
                    for prefix in ("x", "http", "user", "request", "session", "oauth", "prefix", "zxro"):
                        keys.add(prefix + compact)
                        keys.add(prefix.upper() + compact.upper())
        safe = {
            "nativeIdleTime": "safe-native-idle", "nativeIdeaCount": "safe-native-idea",
            "apiKeyboardLayout": "safe-api-keyboard", "apiKeynoteTheme": "safe-api-keynote",
            "clientSecretaryName": "safe-client-secretary", "clientSecretariatStatus": "safe-client-secretariat",
            "authHeaderlessMode": "safe-auth-headerless", "tokenizer": "safe-tokenizer",
            "artifactRef": "artifact-ref-safe",
        }
        generated = sorted(keys)
        for sensitive in (False, True):
            for format_name in ("jsonl", "human"):
                for batch_index in range(0, len(generated), 20):
                    batch = generated[batch_index:batch_index + 20]
                    payload = {key: f"generated-{batch_index}-{index}" for index, key in enumerate(batch)}
                    payload.update(safe)
                    payload["mixed"] = [b"credential-bytes", object()]
                    outputs = []
                    stderr_stream = io.StringIO()
                    logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, sensitive=sensitive), self.home, stream=stderr_stream,
                    )
                    logger.emit("zxro.test.generated.grammar", attributes=payload)
                    outputs.append(stderr_stream.getvalue())
                    log_dir = Path(self.temp.name) / f"grammar-{sensitive}-{format_name}-{batch_index}"
                    log_dir.mkdir(mode=0o700)
                    log_file = log_dir / "events.log"
                    file_logger = diagnostics.DiagnosticLogger(
                        diagnostics.LogConfig("info", format_name, log_file, sensitive=sensitive), self.home,
                    )
                    file_logger.emit("zxro.test.generated.grammar", attributes=payload)
                    outputs.append(log_file.read_text())
                    for output in outputs:
                        if format_name == "jsonl":
                            attributes = json.loads(output)["attributes"]
                        else:
                            correlation_start = output.index(" correlation=")
                            attributes_start = output.index(" {", correlation_start)
                            attributes = json.loads(output.rstrip("\n")[attributes_start + 1:])
                        for key in batch:
                            if key.startswith("native") or "native" in key.lower() and "id" in key.lower():
                                self.assertNotIn(key, attributes)
                            else:
                                self.assertEqual(attributes.get(key), "[REDACTED]", key)
                        for key, value in safe.items():
                            self.assertEqual(attributes.get(key), value, key)
                        self.assertLessEqual(len(output.encode("utf-8")), diagnostics.MAX_EVENT_BYTES)

    def test_human_failure_paths_are_redacted_and_one_line(self):
        parser_result = self.cli(
            "--log-level", "debug", "--log-format", "human", "watchtower", "--unknown",
            "Bearer human-parser-secret", "/private/human-parser-path",
        )
        self.assertEqual(parser_result.returncode, 2)
        self.assertNotIn("human-parser-secret", parser_result.stderr)
        self.assertNotIn("/private/human-parser-path", parser_result.stderr)
        self.assertTrue(all("\n" not in line for line in parser_result.stderr.splitlines()))

        stderr = io.StringIO()
        with mock.patch.object(cli, "_run_command", side_effect=RuntimeError("Bearer human-secret /private/internal-path")), contextlib.redirect_stderr(stderr):
            result = cli.main(["--log-level", "debug", "--log-format", "human", "watchtower", "list"])
        self.assertEqual(result, 1)
        self.assertNotIn("human-secret", stderr.getvalue())
        self.assertNotIn("/private/internal-path", stderr.getvalue())
        self.assertLessEqual(len(stderr.getvalue().splitlines()), 6)

    def test_internal_failure_emits_one_terminal_event(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_run_command", side_effect=RuntimeError("synthetic internal failure")), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = cli.main(["--log-level", "debug", "--log-format", "jsonl", "watchtower", "list"])
        self.assertEqual(result, 1)
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        terminals = [event for event in events if event["event_name"] == "zxro.cli.invocation.completed"]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0]["attributes"], {"error_code": "internal_error", "process_exit_code": 1})
        self.assertEqual(terminals[0]["sequence"], len(events))

    def test_system_exit_payloads_match_process_exit_semantics(self):
        cases = ((None, 0), (0, 0), (7, 7), (True, 1), (False, 0), ("string-code", 1), (object(), 1))
        for payload, expected_code in cases:
            with self.subTest(payload=repr(payload)):
                stderr = io.StringIO()
                with mock.patch.object(cli, "_run_command", side_effect=SystemExit(payload)), contextlib.redirect_stderr(stderr):
                    result = cli.main(["--log-level", "debug", "--log-format", "jsonl", "watchtower", "list"])
                self.assertEqual(result, expected_code)
                events = [json.loads(line) for line in stderr.getvalue().splitlines()]
                terminals = [event for event in events if event["event_name"] == "zxro.cli.invocation.completed"]
                self.assertEqual(len(terminals), 1)
                self.assertEqual(terminals[0]["attributes"]["process_exit_code"], expected_code)
                self.assertEqual("error_code" in terminals[0]["attributes"], expected_code != 0)
                self.assertEqual(terminals[0], events[-1])

    def test_interruption_emits_nonzero_terminal_event(self):
        stderr = io.StringIO()
        with mock.patch.object(cli, "_run_command", side_effect=KeyboardInterrupt()), contextlib.redirect_stderr(stderr):
            result = cli.main(["--log-level", "debug", "--log-format", "jsonl", "watchtower", "list"])
        self.assertEqual(result, 130)
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        terminal = events[-1]
        self.assertEqual(terminal["event_name"], "zxro.cli.invocation.completed")
        self.assertEqual(terminal["attributes"], {"error_code": "interrupted", "process_exit_code": 130})

    def test_event_construction_and_sink_failures_are_fail_open(self):
        failures = (
            (diagnostics, "_bounded", RuntimeError("redaction failure")),
            (diagnostics, "_timestamp", RuntimeError("timestamp failure")),
            (diagnostics.DiagnosticLogger, "_line", RuntimeError("format failure")),
            (diagnostics._FileSink, "_prune", OSError("retention failure")),
        )
        for target, name, failure in failures:
            with self.subTest(name=name):
                log_dir = Path(self.temp.name) / name
                log_dir.mkdir(mode=0o700)
                log_file = log_dir / "events.jsonl"
                baseline_home = Path(self.temp.name) / (name + "-baseline-home")
                failure_home = Path(self.temp.name) / (name + "-failure-home")
                baseline = run_cli(baseline_home, "--json", "watchtower", "create", "normal", "--cwd", "/watchtower")
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(target, name, side_effect=failure), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = cli.main([
                        "--home", str(failure_home), "--json", "--log-level", "info", "--log-format", "jsonl",
                        "--log-file", str(log_file), "watchtower", "create", "normal", "--cwd", "/watchtower",
                    ])
                self.assertEqual(result, baseline.returncode)
                self.assertEqual(stdout.getvalue(), baseline.stdout)
                self.assertEqual(stderr.getvalue(), baseline.stderr)
                baseline_files = sorted(path.relative_to(baseline_home).as_posix() for path in baseline_home.rglob("*") if path.is_file())
                failure_files = sorted(path.relative_to(failure_home).as_posix() for path in failure_home.rglob("*") if path.is_file())
                self.assertEqual(baseline_files, failure_files)
                for relative in baseline_files:
                    self.assertEqual((baseline_home / relative).read_bytes(), (failure_home / relative).read_bytes())

    def test_file_logging_preserves_baseline_stderr_for_parser_and_exit_classes(self):
        def invoke(home, args, log_file=None):
            command = [str(BIN)]
            if log_file is not None:
                command += ["--log-level", "info", "--log-format", "jsonl", "--log-file", str(log_file)]
            command += list(args)
            return subprocess.run(
                command, cwd=ROOT, env={**os.environ, "ZXRO_HOME": str(home)}, text=True, capture_output=True,
            )

        cases = [(("watchtower",), "parser")]
        for args, label in cases:
            home = Path(self.temp.name) / (label + "-home")
            log_dir = Path(self.temp.name) / (label + "-logs")
            log_dir.mkdir(mode=0o700)
            baseline = invoke(home, args)
            with_file = invoke(home, args, log_dir / "events.jsonl")
            self.assertEqual((with_file.returncode, with_file.stdout, with_file.stderr), (baseline.returncode, baseline.stdout, baseline.stderr))

        def prepare(home):
            for args in (("watchtower", "create", "main", "--cwd", "/watchtower"), ("work", "create", "job", "--watchtower", "main")):
                result = invoke(home, args)
                self.assertEqual(result.returncode, 0, result.stderr)

        error_cases = [
            (("watchtower", "show", "../bad"), "exit2"),
            (("watchtower", "show", "missing"), "exit3"),
        ]
        for args, label in error_cases:
            home = Path(self.temp.name) / (label + "-home")
            log_dir = Path(self.temp.name) / (label + "-logs")
            log_dir.mkdir(mode=0o700)
            baseline = invoke(home, args)
            with_file = invoke(home, args, log_dir / "events.jsonl")
            self.assertEqual((with_file.returncode, with_file.stdout, with_file.stderr), (baseline.returncode, baseline.stdout, baseline.stderr))

        home = Path(self.temp.name) / "exit4-home"
        prepare(home)
        baseline = invoke(home, ("work", "create", "job", "--watchtower", "main"))
        log_dir = Path(self.temp.name) / "exit4-logs"; log_dir.mkdir(mode=0o700)
        with_file = invoke(home, ("work", "create", "job", "--watchtower", "main"), log_dir / "events.jsonl")
        self.assertEqual((with_file.returncode, with_file.stdout, with_file.stderr), (baseline.returncode, baseline.stdout, baseline.stderr))

        home = Path(self.temp.name) / "exit5-home"
        prepare(home)
        (home / "work" / "job.json").write_text("{")
        baseline = invoke(home, ("work", "show", "job"))
        log_dir = Path(self.temp.name) / "exit5-logs"; log_dir.mkdir(mode=0o700)
        with_file = invoke(home, ("work", "show", "job"), log_dir / "events.jsonl")
        self.assertEqual((with_file.returncode, with_file.stdout, with_file.stderr), (baseline.returncode, baseline.stdout, baseline.stderr))

    def test_file_sink_failure_is_fail_open_without_changing_command_streams_or_state(self):
        normal = self.cli("watchtower", "create", "normal", "--cwd", "/watchtower")
        failing_home = Path(self.temp.name) / "failing-home"
        log_dir = Path(self.temp.name) / "sink"
        log_dir.mkdir(mode=0o700)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(diagnostics._FileSink, "append", side_effect=OSError("synthetic sink failure")), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = cli.main([
                "--home", str(failing_home), "--log-level", "info", "--log-format", "jsonl",
                "--log-file", str(log_dir / "events.jsonl"), "watchtower", "create", "normal", "--cwd", "/watchtower",
            ])
        self.assertEqual(result, normal.returncode)
        self.assertEqual(stdout.getvalue(), normal.stdout)
        self.assertEqual(stderr.getvalue(), normal.stderr)
        normal_files = sorted(path.relative_to(self.home).as_posix() for path in self.home.rglob("*") if path.is_file())
        failing_files = sorted(path.relative_to(failing_home).as_posix() for path in failing_home.rglob("*") if path.is_file())
        self.assertEqual(normal_files, failing_files)
        for relative in normal_files:
            self.assertEqual((self.home / relative).read_bytes(), (failing_home / relative).read_bytes())

        malformed = log_dir / "malformed.jsonl"
        malformed.write_text("not a ZXRO event\n")
        malformed.chmod(0o600)
        malformed_before = malformed.read_bytes()
        malformed_stdout, malformed_stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(malformed_stdout), contextlib.redirect_stderr(malformed_stderr):
            malformed_result = cli.main([
                "--home", str(Path(self.temp.name) / "malformed-home"), "--json", "--log-level", "info", "--log-format", "jsonl",
                "--log-file", str(malformed), "watchtower", "list",
            ])
        self.assertEqual((malformed_result, malformed_stdout.getvalue(), malformed_stderr.getvalue()), (0, '{\"data\":[],\"schema_version\":1}\n', ""))
        self.assertEqual(malformed.read_bytes(), malformed_before)

    def test_logging_is_disabled_by_default_and_preserves_stdout_stderr(self):
        result = self.cli("--json", "watchtower", "list")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '{\"data\":[],\"schema_version\":1}\n', ""))
        self.assertFalse(self.home.exists())

    def test_explicit_off_keeps_human_failure_stderr_compatible(self):
        baseline = self.cli("watchtower", "show", "missing")
        explicit = self.cli("--log-level", "off", "--log-format", "jsonl", "watchtower", "show", "missing")
        self.assertEqual((explicit.returncode, explicit.stdout, explicit.stderr), (baseline.returncode, baseline.stdout, baseline.stderr))

    def test_enabled_success_has_contiguous_sequence_and_one_terminal_event(self):
        result, events = self.events("--json", "watchtower", "list")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{\"data\":[],\"schema_version\":1}\n')
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(sum(event["event_name"] == "zxro.cli.invocation.completed" for event in events), 1)
        terminal = events[-1]
        self.assertEqual(terminal["attributes"]["process_exit_code"], result.returncode)
        self.assertEqual(terminal["attributes"]["result_code"], "success")
        self.assertTrue(all(event["invocation_id"] == terminal["invocation_id"] for event in events))
        for event in events:
            self.assertIn(event["event_name"], diagnostics.CORE_EVENT_NAMES)
            self.assertEqual(event["log_schema_version"], 1)
            self.assertIn(event["level"], {"debug", "info", "warning", "error"})
            self.assertIn("timestamp", event)
            self.assertIn("attributes", event)

    def test_core_event_schema_golden_has_required_fields(self):
        stream = io.StringIO()
        logger = diagnostics.DiagnosticLogger(diagnostics.LogConfig("debug", "jsonl"), self.home, stream=stream)
        for event_name in sorted(diagnostics.CORE_EVENT_NAMES):
            logger.emit(event_name, "info", attributes={"path": "/private/schema-path", "result_code": "success"}, terminal=event_name == "zxro.cli.invocation.completed")
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(len(events), len(diagnostics.CORE_EVENT_NAMES))
        required = {"log_schema_version", "event_name", "event_version", "timestamp", "level", "process", "invocation_id", "sequence", "correlation", "attributes"}
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        for event in events:
            self.assertTrue(required <= event.keys())
            self.assertNotIn("/private/schema-path", json.dumps(event))
            self.assertIn(event["event_name"], diagnostics.CORE_EVENT_NAMES)

    def test_human_and_jsonl_sinks_preserve_event_identity_and_timing(self):
        human_stream, json_stream = io.StringIO(), io.StringIO()
        human = diagnostics.DiagnosticLogger(diagnostics.LogConfig("info", "human"), self.home, stream=human_stream, clock=lambda: 10.0)
        structured = diagnostics.DiagnosticLogger(diagnostics.LogConfig("info", "jsonl"), self.home, stream=json_stream, clock=lambda: 10.0)
        structured.invocation_id = human.invocation_id
        structured._key = human._key
        for logger in (human, structured):
            logger.start("work.list", "job")
            logger.provider_done("work.list", False, 10.0, resource="job")
            logger.finish(0)
        json_events = [json.loads(line) for line in json_stream.getvalue().splitlines()]
        human_lines = human_stream.getvalue().splitlines()
        self.assertEqual(len(human_lines), len(json_events))
        for line, event in zip(human_lines, json_events):
            self.assertIn(event["event_name"], line)
            self.assertIn(f"schema={event['log_schema_version']}", line)
            self.assertIn(f"event_version={event['event_version']}", line)
            self.assertIn(f"process={event['process']}", line)
            self.assertIn(f"sequence={event['sequence']}", line)
            self.assertIn(f"invocation_id={event['invocation_id']}", line)
            self.assertIn(f"home={event['correlation']['home']}", line)
            if "duration_ms" in event:
                self.assertIn(f"duration_ms={event['duration_ms']}", line)
            attrs = json.loads(line.rsplit(" ", 1)[-1])
            self.assertEqual(attrs, event["attributes"])

    def test_settlement_stage_failure_is_observed_at_failed_boundary(self):
        self.cli("watchtower", "create", "main", "--cwd", "/watchtower")
        self.cli("work", "create", "job", "--watchtower", "main")
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        stderr = io.StringIO()
        with mock.patch.object(durable, "atomic_create", side_effect=OSError("synthetic event publication failure")), contextlib.redirect_stderr(stderr):
            result = cli.main([
                "--home", str(self.home), "--log-level", "debug", "--log-format", "jsonl", "turn", "settle", turn,
                "--source", "manual", "--status", "completed", "--message", "done",
            ])
        self.assertEqual(result, 5)
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        failed = next(event for event in events if event["event_name"] == "zxro.settlement.publication.stage_failed")
        self.assertEqual(failed["attributes"]["stage"], "event_commit")
        self.assertEqual(failed["attributes"]["error_code"], "os_error")
        self.assertEqual(events[-1]["attributes"]["process_exit_code"], 5)

    def test_existing_settlement_event_mismatch_fails_inside_event_validation_stage(self):
        self.cli("watchtower", "create", "main", "--cwd", "/watchtower")
        self.cli("work", "create", "job", "--watchtower", "main")
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        settled = self.cli("turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done")
        self.assertEqual(settled.returncode, 0, settled.stderr)
        event_path = self.home / "inbox-events" / "main--00000000000000000001.json"
        event = json.loads(event_path.read_text())
        event["summary"] = "parseable mismatch"
        event_path.write_text(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        result, events = self.events("turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done")
        self.assertEqual(result.returncode, 5)
        failures = [event for event in events if event["event_name"] == "zxro.settlement.publication.stage_failed" and event["attributes"].get("stage") == "event_validation"]
        completions = [event for event in events if event["event_name"] == "zxro.settlement.publication.stage_completed" and event["attributes"].get("stage") == "event_validation"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(completions, [])
        self.assertEqual(failures[0]["attributes"]["error_code"], "unsafe_state")
        self.assertGreaterEqual(failures[0]["duration_ms"], 0)
        self.assertEqual(events[-1]["event_name"], "zxro.cli.invocation.completed")
        self.assertEqual(events[-1]["attributes"]["process_exit_code"], 5)

    def test_artifact_verification_failure_is_observed_at_verification_boundary(self):
        self.cli("watchtower", "create", "main", "--cwd", "/watchtower")
        self.cli("work", "create", "job", "--watchtower", "main")
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        settle = subprocess.run(
            [str(BIN), "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done", "--stdin"],
            cwd=ROOT,
            env={**os.environ, "ZXRO_HOME": str(self.home)},
            input="evidence",
            text=True,
            capture_output=True,
        )
        self.assertEqual(settle.returncode, 0, settle.stderr)
        ref = f"artifact:{turn}:stdin"
        materialized = Path(self.cli("artifact", "path", ref).stdout.strip())
        materialized.chmod(0o600)
        materialized.write_text("tampered")
        result, events = self.events("artifact", "path", ref)
        self.assertEqual(result.returncode, 5)
        failed = next(event for event in events if event["event_name"] == "zxro.artifact.verification.failed")
        self.assertEqual(failed["attributes"]["error_code"], "unsafe_state")
        self.assertEqual(events[-1]["attributes"]["process_exit_code"], 5)

    def test_stage_events_report_observed_boundaries_and_real_lock_duration(self):
        self.cli("watchtower", "create", "main", "--cwd", "/watchtower")
        self.cli("work", "create", "job", "--watchtower", "main")
        turn = self.cli("turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
        result, events = self.events("turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done")
        self.assertEqual(result.returncode, 0)
        names = [event["event_name"] for event in events]
        self.assertIn("zxro.lock.wait.completed", names)
        self.assertEqual(
            [event["attributes"]["stage"] for event in events if event["event_name"] == "zxro.settlement.publication.stage_completed"],
            ["turn_commit", "event_commit", "index_commit", "mailbox_commit", "event_validation"],
        )
        lock = next(event for event in events if event["event_name"] == "zxro.lock.wait.completed")
        self.assertGreaterEqual(lock["duration_ms"], 0)
        self.assertLess(events.index(lock), names.index("zxro.provider.mutation.completed"))
        for event in events:
            if event["event_name"] in {"zxro.cli.invocation.started", "zxro.cli.command.dispatched", "zxro.provider.mutation.started"}:
                continue
            self.assertIn("duration_ms", event)
            self.assertEqual(sum(key in event["attributes"] for key in ("result_code", "error_code")), 1)
            self.assertNotIn("process_exit_code", event["attributes"] if event["event_name"] != "zxro.cli.invocation.completed" else {})

    def test_observe_lock_attributes_each_concurrent_lock_wait_to_its_own_observer(self):
        from zxro.localfs import ioutil

        home = Path(self.temp.name) / "shared_lock_home"
        with ioutil.mutation(home):
            pass

        def worker(index):
            captured = []

            def observer(duration_ms):
                captured.append(duration_ms)

            for _ in range(20):
                with ioutil.observe_lock(observer):
                    with ioutil.mutation(home):
                        pass
            return index, captured

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(worker, range(8)))

        for index, captured in outcomes:
            self.assertEqual(len(captured), 20, f"worker {index} lost or gained lock-wait events")
            for duration in captured:
                self.assertIsInstance(duration, float)
                self.assertGreaterEqual(duration, 0)

    def test_thresholds_filter_stage_events_but_keep_terminal(self):
        expected = {
            "error": ["zxro.cli.invocation.completed"],
            "warning": ["zxro.cli.invocation.completed"],
            "info": ["zxro.cli.invocation.started", "zxro.provider.read.completed", "zxro.cli.invocation.completed"],
            "debug": [
                "zxro.cli.invocation.started",
                "zxro.cli.command.dispatched",
                "zxro.provider.read.started",
                "zxro.provider.read.completed",
                "zxro.cli.invocation.completed",
            ],
        }
        for level, names in expected.items():
            with self.subTest(level=level):
                result = self.cli("--log-level", level, "--log-format", "jsonl", "watchtower", "list")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([json.loads(line)["event_name"] for line in result.stderr.splitlines()], names)

    def test_jsonl_failure_replaces_human_error_and_reports_exit_class(self):
        result, events = self.events("--json", "watchtower", "show", "missing")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "")
        self.assertTrue(all(line.startswith("{") for line in result.stderr.splitlines()))
        self.assertEqual(events[-1]["event_name"], "zxro.cli.invocation.completed")
        self.assertEqual(events[-1]["attributes"], {"error_code": "not_found", "process_exit_code": 3})
        self.assertEqual(events[-2]["attributes"]["error_code"], "not_found")
        self.assertNotIn("record not found", result.stderr)

    def test_environment_values_are_overridden_by_explicit_flags(self):
        result, events = self.events(
            "--log-level", "error", "--correlation-id", "explicit-id", "watchtower", "list",
            env={"ZXRO_LOG_LEVEL": "debug", "ZXRO_LOG_FORMAT": "human", "ZXRO_CORRELATION_ID": "environment-id"},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["correlation"]["correlation_id"], "explicit-id")

        directory = Path(self.temp.name) / "precedence"
        directory.mkdir(mode=0o700)
        explicit_file, environment_file = directory / "explicit.jsonl", directory / "environment.jsonl"
        environment_result = self.cli(
            "--log-level", "info", "--log-format", "jsonl", "watchtower", "list",
            env={"ZXRO_LOG_FILE": str(environment_file)},
        )
        self.assertEqual(environment_result.returncode, 0, environment_result.stderr)
        self.assertTrue(environment_file.exists())
        environment_file.unlink()
        file_result = self.cli(
            "--log-level", "info", "--log-format", "jsonl", "--log-file", str(explicit_file), "watchtower", "list",
            env={"ZXRO_LOG_LEVEL": "bad", "ZXRO_LOG_FILE": str(environment_file)},
        )
        self.assertEqual(file_result.returncode, 0, file_result.stderr)
        self.assertEqual(file_result.stderr, "")
        self.assertTrue(explicit_file.exists())
        self.assertFalse(environment_file.exists())
        disabled = self.cli("--log-level", "off", "watchtower", "list", env={"ZXRO_LOG_LEVEL": "bad"})
        self.assertEqual(disabled.returncode, 0, disabled.stderr)

    def test_sensitive_resource_correlation_requires_validated_zxro_identity(self):
        marker = "invalid-resource-secret-marker"
        invalid = (
            ("watchtower", "show", f"/private/{marker}"),
            ("turn", "create", "--work", f"/private/{marker}", "--agent", "pi", "--session", "s", "--cwd", "/crew"),
            ("artifact", "path", f"/private/{marker}"),
            ("watchtower", "show", "x" * 4096 + marker),
        )
        for argv in invalid:
            with self.subTest(argv=argv[:2]):
                result = self.cli("--log-level", "debug", "--log-format", "jsonl", "--log-sensitive", *argv)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(marker, result.stderr)
                self.assertNotIn("/private/", result.stderr)
                events = [json.loads(line) for line in result.stderr.splitlines()]
                self.assertTrue(events)
                for event in events:
                    resource = event["correlation"].get("resource")
                    self.assertTrue(resource is None or (resource.startswith("fp_") and len(resource) == 23))
        visible = self.cli("--log-level", "info", "--log-format", "jsonl", "--log-sensitive", "watchtower", "show", "safe-id")
        self.assertEqual(visible.returncode, 3)
        visible_resources = [json.loads(line)["correlation"].get("resource") for line in visible.stderr.splitlines()]
        self.assertIn("safe-id", visible_resources)
        self.assertTrue(all(resource in (None, "safe-id") for resource in visible_resources))

    def test_hardlinked_log_family_is_rejected_without_mutating_external_inode(self):
        for suffix in ("", ".1"):
            with self.subTest(suffix=suffix):
                directory = Path(self.temp.name) / ("hardlink-active" if not suffix else "hardlink-backup")
                directory.mkdir(mode=0o700)
                outside = Path(self.temp.name) / ("outside-active.log" if not suffix else "outside-backup.log")
                outside.write_bytes(b"external-bytes")
                outside.chmod(0o600)
                log_path = directory / "events.log"
                os.link(outside, Path(str(log_path) + suffix))
                diagnostics._set_owner_binding(outside, diagnostics._home_fingerprint(self.home))
                before = (outside.read_bytes(), outside.stat().st_ino, outside.stat().st_nlink)
                result = self.cli("--log-level", "info", "--log-format", "jsonl", "--log-file", str(log_path), "watchtower", "list")
                self.assertEqual(result.returncode, 2)
                self.assertEqual((outside.read_bytes(), outside.stat().st_ino, outside.stat().st_nlink), before)

    def test_redaction_omits_paths_and_raw_ids_by_default(self):
        secret = "Bearer synthetic-secret-value"
        result = self.cli(
            "--log-level", "debug", "--log-format", "jsonl", "--json", "watchtower", "create", "safe-id",
            "--cwd", "/private/project", "--agent", secret, "--session", "native-session-value",
            env={"ZXRO_TEST_SECRET": secret},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret, result.stderr)
        self.assertNotIn("/private/project", result.stderr)
        self.assertNotIn("native-session-value", result.stderr)
        self.assertNotIn("native-id-value", result.stderr)
        self.assertNotIn("safe-id", result.stderr)

        self.assertEqual(self.cli("work", "create", "safe-work", "--watchtower", "safe-id").returncode, 0)
        turn_result = self.cli("--log-level", "debug", "--log-format", "jsonl", "turn", "create", "--work", "safe-work", "--agent", "pi", "--session", "native-session-value", "--native-session-id", "native-id-value", "--cwd", "/private/crew")
        self.assertEqual(turn_result.returncode, 0, turn_result.stderr)
        for value in ("native-session-value", "native-id-value", "/private/crew"):
            self.assertNotIn(value, turn_result.stderr)
        turn = turn_result.stdout.strip()
        payload = "Bearer payload-secret /private/payload"
        settled = subprocess.run(
            [str(BIN), "--log-level", "debug", "--log-format", "jsonl", "turn", "settle", turn,
             "--source", "manual-source", "--status", "failed", "--message", payload, "--stdin"],
            cwd=ROOT,
            env={**os.environ, "ZXRO_HOME": str(self.home)},
            input=payload,
            text=True,
            capture_output=True,
        )
        self.assertEqual(settled.returncode, 0, settled.stderr)
        for value in (turn, "manual-source", payload, "payload-secret", "/private/payload"):
            self.assertNotIn(value, settled.stderr)

        sensitive = self.cli(
            "--log-level", "info", "--log-format", "jsonl", "--log-sensitive", "watchtower", "show", "safe-id"
        )
        self.assertEqual(sensitive.returncode, 0, sensitive.stderr)
        self.assertIn("safe-id", sensitive.stderr)
        self.assertNotIn("/private/project", sensitive.stderr)

    def test_emitted_home_correlation_is_process_local(self):
        first = self.cli("--log-level", "info", "--log-format", "jsonl", "watchtower", "list")
        second = self.cli("--log-level", "info", "--log-format", "jsonl", "watchtower", "list")
        first_events = [json.loads(line) for line in first.stderr.splitlines()]
        second_events = [json.loads(line) for line in second.stderr.splitlines()]
        self.assertNotEqual(first_events[0]["correlation"]["home"], second_events[0]["correlation"]["home"])
        self.assertEqual({event["correlation"]["home"] for event in first_events}, {first_events[0]["correlation"]["home"]})
        self.assertEqual({event["correlation"]["home"] for event in second_events}, {second_events[0]["correlation"]["home"]})

    def test_file_paths_use_physical_home_isolation_and_reject_shared_files(self):
        real = Path(self.temp.name) / "real"
        physical_home = real / "home"
        real.mkdir(mode=0o700)
        physical_home.mkdir(mode=0o700)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(real, target_is_directory=True)
        inside = self.cli(
            "--home", str(alias / "home"), "--log-level", "info", "--log-format", "jsonl",
            "--log-file", str(physical_home / "inside.jsonl"), "watchtower", "list",
        )
        self.assertEqual(inside.returncode, 2)
        self.assertFalse((physical_home / "inside.jsonl").exists())

        log_dir = Path(self.temp.name) / "shared-logs"
        log_dir.mkdir(mode=0o700)
        shared = log_dir / "shared.jsonl"
        first_home = Path(self.temp.name) / "home-one"
        second_home = Path(self.temp.name) / "home-two"
        first = self.cli("--home", str(first_home), "--log-level", "info", "--log-format", "jsonl", "--log-file", str(shared), "watchtower", "list")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = shared.read_bytes()
        second = self.cli("--home", str(second_home), "--log-level", "info", "--log-format", "jsonl", "--log-file", str(shared), "watchtower", "list")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(shared.read_bytes(), before)

    def test_file_sink_keeps_results_on_stdout_and_owner_only_permissions(self):
        log_dir = Path(self.temp.name) / "diagnostics"
        log_dir.mkdir(mode=0o700)
        log_file = log_dir / "zxro.jsonl"
        result = self.cli(
            "--json", "--log-level", "info", "--log-format", "jsonl", "--log-file", str(log_file), "watchtower", "list"
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '{\"data\":[],\"schema_version\":1}\n', ""))
        self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
        events = [json.loads(line) for line in log_file.read_text().splitlines()]
        self.assertEqual(events[-1]["event_name"], "zxro.cli.invocation.completed")
        self.assertEqual({candidate.name for candidate in log_dir.iterdir()}, {log_file.name})
        before = log_file.read_bytes()
        log_file.chmod(0o644)
        rejected = self.cli(
            "--json", "--log-level", "info", "--log-format", "jsonl", "--log-file", str(log_file), "watchtower", "list"
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(log_file.read_bytes(), before)

        unsafe_parent = Path(self.temp.name) / "unsafe-parent"
        unsafe_parent.mkdir(mode=0o755)
        unsafe_parent.chmod(0o755)
        parent_file = unsafe_parent / "events.jsonl"
        parent_result = self.cli(
            "--log-level", "info", "--log-format", "jsonl", "--log-file", str(parent_file), "watchtower", "list"
        )
        self.assertEqual(parent_result.returncode, 2)
        self.assertFalse(parent_file.exists())

    def test_invalid_logging_configuration_fails_before_home_access(self):
        result = self.cli("--log-level", "nope", "watchtower", "list")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.home.exists())
        self.assertIn("invalid choice", result.stderr)
        invalid_file = Path(self.temp.name) / "missing" / "events.jsonl"
        disabled = self.cli("--log-level", "off", "--log-file", str(invalid_file), "watchtower", "list")
        self.assertEqual(disabled.returncode, 2)
        self.assertFalse(self.home.exists())
        configured = self.cli("--log-level", "info", "--log-format", "jsonl", "--log-file", str(invalid_file), "watchtower", "list")
        self.assertEqual(configured.returncode, 2)
        configured_events = [json.loads(line) for line in configured.stderr.splitlines()]
        self.assertEqual(configured_events[-1]["attributes"], {"error_code": "validation_error", "process_exit_code": 2})
        self.assertEqual(sum(event["event_name"] == "zxro.cli.invocation.completed" for event in configured_events), 1)
        self.assertFalse(self.home.exists())

    def test_inactive_files_are_not_pruned_until_append_and_mixed_age_files_stay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            path = directory / "events.jsonl"
            sink = diagnostics._FileSink(path, "jsonl")
            old = json.dumps({"timestamp": "2020-01-01T00:00:00.000Z"}) + "\n"
            path.write_text(old)
            path.chmod(0o600)
            self.assertTrue(path.exists())
            sink.append((json.dumps({"timestamp": "2099-01-01T00:00:00.000Z", "fresh": True}) + "\n").encode())
            values = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(values, [{"timestamp": "2099-01-01T00:00:00.000Z", "fresh": True}])

    def test_concurrent_file_appends_are_complete_and_parseable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            path = directory / "events.jsonl"
            sink = diagnostics._FileSink(path, "jsonl")

            def append(index):
                sink.append((json.dumps({"timestamp": "2099-01-01T00:00:00.000Z", "index": index}) + "\n").encode())

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(append, range(200)))
            values = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(values), 200)
            self.assertEqual({value["index"] for value in values}, set(range(200)))

    def test_fault_exit_matrix_logs_partial_stream_without_false_terminal(self):
        for point in ("turn-commit", "before-event-commit", "event-commit", "index-commit", "mailbox-commit"):
            with self.subTest(point=point):
                home = Path(self.temp.name) / (point.replace("-", "_"))
                self.assertEqual(run_cli(home, "watchtower", "create", "main", "--cwd", "/watchtower").returncode, 0)
                self.assertEqual(run_cli(home, "work", "create", "job", "--watchtower", "main").returncode, 0)
                turn = run_cli(home, "turn", "create", "--work", "job", "--agent", "pi", "--session", "s", "--cwd", "/crew").stdout.strip()
                log_dir = Path(self.temp.name) / (point.replace("-", "_") + "_logs")
                log_dir.mkdir(mode=0o700)
                log_file = log_dir / "events.jsonl"
                crashed = run_cli(
                    home, "--log-level", "debug", "--log-format", "jsonl", "--log-file", str(log_file),
                    "turn", "settle", turn, "--source", "manual", "--status", "completed", "--message", "done",
                    env={"ZXRO_FAULT_EXIT_AFTER": point},
                )
                self.assertEqual(crashed.returncode, 86)
                events = [json.loads(line) for line in log_file.read_text().splitlines()]
                self.assertTrue(events)
                self.assertNotIn("zxro.cli.invocation.completed", [event["event_name"] for event in events])
                self.assertEqual({candidate.name for candidate in log_dir.iterdir()}, {log_file.name})

    def test_owner_bound_rotation_stays_within_five_file_family(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            path = directory / "events.jsonl"
            sink = diagnostics._FileSink(path, "jsonl", "home_binding")
            with mock.patch.object(diagnostics, "MAX_LOG_FILE_BYTES", 100):
                for index in range(30):
                    sink.append((json.dumps({"timestamp": "2099-01-01T00:00:00.000Z", "index": index}) + "\n").encode())
            family = {candidate.name for candidate in directory.iterdir()}
            self.assertEqual(family, {"events.jsonl", "events.jsonl.1", "events.jsonl.2", "events.jsonl.3", "events.jsonl.4"})
            newest_by_file = {
                candidate.name: max(json.loads(line)["index"] for line in candidate.read_text().splitlines())
                for candidate in directory.iterdir()
            }
            self.assertGreater(newest_by_file["events.jsonl"], newest_by_file["events.jsonl.1"])
            self.assertGreater(newest_by_file["events.jsonl.1"], newest_by_file["events.jsonl.2"])
            self.assertGreater(newest_by_file["events.jsonl.2"], newest_by_file["events.jsonl.3"])
            self.assertGreater(newest_by_file["events.jsonl.3"], newest_by_file["events.jsonl.4"])
            for candidate in directory.iterdir():
                self.assertLessEqual(candidate.stat().st_size, 100)
                self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), 0o600)

    def test_file_rotation_is_bounded_and_age_pruning_is_file_granular(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            path = directory / "events.jsonl"
            old = "2020-01-01T00:00:00.000Z"
            recent = "2099-01-01T00:00:00.000Z"
            path.write_text(json.dumps({"timestamp": old}) + "\n")
            Path(f"{path}.1").write_text(json.dumps({"timestamp": old}) + "\n")
            Path(f"{path}.2").write_text(json.dumps({"timestamp": old}) + "\n" + json.dumps({"timestamp": recent}) + "\n")
            for candidate in (path, Path(f"{path}.1"), Path(f"{path}.2")):
                candidate.chmod(0o600)
            with mock.patch.object(diagnostics, "MAX_LOG_FILE_BYTES", 100):
                sink = diagnostics._FileSink(path, "jsonl")
                self.assertFalse(path.exists())
                self.assertFalse(Path(f"{path}.1").exists())
                self.assertTrue(Path(f"{path}.2").exists())
                for index in range(12):
                    sink.append((json.dumps({"timestamp": recent, "n": index}) + "\n").encode())
            files = {candidate.name for candidate in directory.iterdir()}
            self.assertTrue(files <= {"events.jsonl", "events.jsonl.1", "events.jsonl.2", "events.jsonl.3", "events.jsonl.4"})
            self.assertLessEqual(len(files), 5)
            self.assertFalse((directory / "events.jsonl.5").exists())


if __name__ == "__main__":
    unittest.main()
