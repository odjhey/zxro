#!/usr/bin/env python3
"""Run the deterministic, provider-free M7 orchestration simulation.

The simulation is deliberately outside the zxro package. It drives only the
public CLI, while short-lived local Python processes stand in for runtimes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ZXRO = ROOT / "bin" / "zxro"
MAX_TURNS = 4
STAGES = (
    ("coder-a", "repo-a", "Implemented the deterministic change."),
    ("reviewer-a", "repo-a", "Reviewed the deterministic change."),
    ("coder-b", "repo-b", "Applied the follow-up in the second target."),
    ("tester-b", "repo-b", "Verified the completed work."),
)

# Simulation children receive a whitelist, not a filtered copy of the parent
# environment. This blocks provider credentials and config paths even when an
# operator launches the simulation from a configured agent shell.
_SAFE_INHERITED_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT")
_PROVIDER_ENV_TOKENS = (
    "ANTHROPIC",
    "CLAUDE",
    "OPENAI",
    "AZURE_OPENAI",
    "GOOGLE_",
    "GEMINI",
    "ACPX",
    "ACP_",
    "PI_",
    "BEADS_",
    "MAIL_",
    "API_KEY",
    "API_TOKEN",
    "AUTH_TOKEN",
    "ACCESS_TOKEN",
    "SECRET_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_",
    "MISTRAL",
    "COHERE",
    "PERPLEXITY",
    "TOGETHER",
    "VERTEX",
    "BEDROCK",
    "OLLAMA",
    "API_BASE",
    "BASE_URL",
)

class SimulationContractError(RuntimeError):
    pass


def provider_like_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in _PROVIDER_ENV_TOKENS)


_FAKE_RUNTIME = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys

stage, target_label = sys.argv[1:3]
required = ("ZXRO_HOME", "ZXRO_TURN_ID", "ZXRO_WORK_ID", "ZXRO_WATCHTOWER_ID")
if any(not os.environ.get(name) for name in required):
    raise SystemExit("fake runtime received incomplete ZXRO metadata")

def provider_key(key):
    upper = key.upper()
    return any(token in upper for token in (
        "ANTHROPIC", "CLAUDE", "OPENAI", "AZURE_OPENAI", "GOOGLE_", "GEMINI",
        "ACPX", "ACP_", "PI_", "BEADS_", "MAIL_", "API_KEY", "API_TOKEN",
        "AUTH_TOKEN", "ACCESS_TOKEN", "SECRET_KEY", "GITHUB_TOKEN", "GH_TOKEN",
        "AWS_", "MISTRAL", "COHERE", "PERPLEXITY", "TOGETHER", "VERTEX",
        "BEDROCK", "OLLAMA", "API_BASE", "BASE_URL",
    ))

forbidden = sorted(key for key in os.environ if provider_key(key))
if forbidden:
    raise SystemExit("fake runtime received provider-like environment keys: " + ",".join(forbidden))
home = Path(os.environ["HOME"]).resolve()
config_home = Path(os.environ["XDG_CONFIG_HOME"]).resolve()
git_check = subprocess.run(
    ["git", "rev-parse", "--is-inside-work-tree"],
    cwd=Path.cwd(),
    env=os.environ.copy(),
    text=True,
    capture_output=True,
)
if git_check.returncode != 0 or git_check.stdout.strip() != "true":
    raise SystemExit("fake runtime target is not a Git repository")
record = {
    "runtime": "fake-runtime",
    "stage": stage,
    "target": target_label,
    "turn_id": os.environ["ZXRO_TURN_ID"],
    "work_id": os.environ["ZXRO_WORK_ID"],
    "watchtower_id": os.environ["ZXRO_WATCHTOWER_ID"],
    "forbidden_provider_keys": forbidden,
    "private_config_home": config_home.is_relative_to(home),
    "git_repository": True,
}
out = Path.cwd() / "m7-runtime-evidence" / f"{stage}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(record, sort_keys=True) + "\n")
print(json.dumps({"stage": stage, "target": target_label}, sort_keys=True))
'''


def clean_environment(home: Path, *, turn_id: str | None = None) -> dict[str, str]:
    process_home = home.parent / "process-home"
    config_home = process_home / "config"
    data_home = process_home / "data"
    cache_home = process_home / "cache"
    for directory in (process_home, config_home, data_home, cache_home):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {key: os.environ[key] for key in _SAFE_INHERITED_ENV if key in os.environ}
    environment.update(
        {
            "HOME": str(process_home),
            "USERPROFILE": str(process_home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(data_home),
            "XDG_CACHE_HOME": str(cache_home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "ZXRO_HOME": str(home),
        }
    )
    if turn_id:
        environment.update(
            {
                "ZXRO_TURN_ID": turn_id,
                "ZXRO_WORK_ID": "m7-sim-work",
                "ZXRO_WATCHTOWER_ID": "m7-sim-watchtower",
            }
        )
    leaked = sorted(key for key in environment if provider_like_key(key))
    if leaked:
        raise SimulationContractError("provider-like key entered child environment: " + ", ".join(leaked))
    return environment


def invoke(home: Path, *args: str, input_bytes: bytes | None = None, check: bool = True):
    result = subprocess.run(
        [str(ZXRO), "--json", *args],
        cwd=ROOT,
        env=clean_environment(home),
        input=input_bytes,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"zxro {' '.join(args)} failed with {result.returncode}: "
            f"{result.stderr.decode().strip()}"
        )
    value = None
    if result.stdout:
        value = json.loads(result.stdout)
    return result, value


def run_git(home: Path, target: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=target,
        env=clean_environment(home),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def required_predicates(report: dict) -> dict[str, bool]:
    turns = report.get("turns", [])
    stages = [(item.get("stage"), item.get("target")) for item in turns]
    environment = report.get("environment", {})
    stop = report.get("stop_conditions", {})
    wake = report.get("wake_and_reconciliation", [])
    repositories = report.get("repository_evidence", [])
    evidence = report.get("durable_evidence", [])
    records = [item.get("json", {}) for item in evidence]
    events = [item for item in records if item.get("type") == "turn_settled"]
    durable_turns = [item.get("json", {}) for item in evidence if item.get("path", "").startswith("turns/")]
    durable_artifacts = [item.get("json", {}) for item in evidence if item.get("path", "").startswith("artifacts/") and "json" in item]
    artifacts_by_ref = {item.get("ref"): item for item in durable_artifacts}
    durable_turn_by_id = {item.get("id"): item for item in durable_turns}
    events_by_turn = {item.get("turn_id"): item for item in events}
    public_refs = [ref for turn in turns for ref in turn.get("public_artifact_refs", [])]
    handled = [item for item in evidence if item.get("path", "").startswith("inbox-handled/")]
    mailbox = next((item for item in records if item.get("watchtower_id") == "m7-sim-watchtower" and "ack" in item), {})
    return {
        "bounded_turn_count": len(turns) == MAX_TURNS and stop.get("turn_count") == MAX_TURNS and stop.get("bounded_by") == MAX_TURNS,
        "workflow_order": stages == [(stage, target) for stage, target, _ in STAGES] and all(item.get("state") == "settled" and item.get("outcome") == "completed" for item in turns),
        "cwd_separation": environment.get("watchtower_cwd") == "watchtower" and environment.get("target_cwds") == ["repo-a", "repo-b"] and all(item.get("target_cwd_is_separate") is True for item in turns),
        "durable_turn_cwds": len(durable_turns) == MAX_TURNS and len({item.get("cwd") for item in durable_turns}) == 2 and all(any(record.get("id") == turn.get("turn_id") and record.get("cwd") == turn.get("expected_target_cwd") for record in durable_turns) for turn in turns),
        "disposable_git_repositories": len(repositories) == 2 and all(item.get("is_git_repository") is True and item.get("head") for item in repositories),
        "wake_reconciliation": len(wake) == MAX_TURNS and len(wake[0].get("dropped_wake", [])) == 2 and wake[0].get("poll_after_dropped_wake", {}).get("handled_expected_turn") is True and all(item.get("stage_released_after_handling") is True for item in wake) and all(item.get("duplicate_wake_count") == 2 for item in wake[1:]),
        "settlement_idempotency": len(events) == MAX_TURNS and len({item.get("event_id") for item in events}) == MAX_TURNS and all(item.get("retry_preserved_event_id") is True for item in turns),
        "artifact_evidence": len(durable_turns) == MAX_TURNS and len(durable_artifacts) == MAX_TURNS and len(public_refs) == MAX_TURNS and len(set(public_refs)) == MAX_TURNS and all(isinstance(turn.get("public_artifact_refs"), list) and turn["public_artifact_refs"] and durable_turn_by_id.get(turn.get("turn_id"), {}).get("artifact_refs") == turn["public_artifact_refs"] and events_by_turn.get(turn.get("turn_id"), {}).get("artifact_refs") == turn["public_artifact_refs"] and all(artifacts_by_ref.get(ref, {}).get("ref") == ref and artifacts_by_ref[ref].get("turn_id") == turn.get("turn_id") and isinstance(artifacts_by_ref[ref].get("content_hex"), str) and artifacts_by_ref[ref].get("content_hex") and isinstance(artifacts_by_ref[ref].get("bytes"), int) and artifacts_by_ref[ref]["bytes"] > 0 for ref in turn["public_artifact_refs"]) for turn in turns),
        "closed_work_stop": stop.get("final_work_state") == "closed" and stop.get("close_result") == "closed" and stop.get("repeated_close_state") == "closed" and stop.get("new_turn_after_close_rejected") is True and stop.get("terminal_retry_after_close") is True and stop.get("unread_after_close") == 0 and stop.get("pending_after_close") == 0,
        "provider_free_children": environment.get("child_environment") == "explicit-safe-whitelist" and environment.get("provider_credentials_in_children") is False and environment.get("provider_config_in_children") is False and all(item.get("runtime_evidence", {}).get("forbidden_provider_keys") == [] and item.get("runtime_evidence", {}).get("private_config_home") is True and item.get("runtime_evidence", {}).get("git_repository") is True for item in turns),
        "durable_evidence": [item.get("generation") for item in events] == list(range(1, MAX_TURNS + 1)) and len(handled) == MAX_TURNS and mailbox.get("ack") == MAX_TURNS and mailbox.get("highest") == MAX_TURNS and mailbox.get("unresolved") == [],
        "cleanup": report.get("cleanup", {}).get("fake_runtime_processes_reaped") is True and report.get("cleanup", {}).get("temporary_home_removed") is True,
    }


def validate_contract(report: dict) -> dict[str, bool]:
    predicates = required_predicates(report)
    report["contract_predicates"] = predicates
    failed = [name for name, passed in predicates.items() if passed is not True]
    if failed:
        raise SimulationContractError("required simulation predicates failed: " + ", ".join(failed))
    return predicates


def apply_fault(report: dict, fault: str | None) -> None:
    if fault == "stop-condition":
        report["stop_conditions"]["pending_after_close"] = 1
    elif fault == "provider-environment":
        report["environment"]["provider_credentials_in_children"] = True
    elif fault == "repository":
        report["repository_evidence"][0]["is_git_repository"] = False
    elif fault == "durable-cwd":
        turn_id = report["turns"][0]["turn_id"]
        for item in report["durable_evidence"]:
            if item.get("path", "").startswith("turns/") and item.get("json", {}).get("id") == turn_id:
                item["json"]["cwd"] = "/wrong/durable-target"
                break
    elif fault == "artifact-refs":
        for item in report["turns"]:
            item["artifact_count"] = 0
        for item in report["durable_evidence"]:
            if item.get("path", "").startswith(("turns/", "inbox-events/")) and "json" in item:
                item["json"]["artifact_refs"] = []
    elif fault == "swapped-refs":
        report["turns"][0]["public_artifact_refs"], report["turns"][1]["public_artifact_refs"] = report["turns"][1]["public_artifact_refs"], report["turns"][0]["public_artifact_refs"]
    elif fault == "wrong-artifact-owner":
        artifact_records = [item for item in report["durable_evidence"] if item.get("path", "").startswith("artifacts/") and "json" in item]
        artifact_records[0]["json"]["turn_id"] = report["turns"][1]["turn_id"]
    elif fault == "empty-public-refs":
        for item in report["turns"]:
            item["public_artifact_refs"] = []


def run_fake_runtime(
    script: Path,
    home: Path,
    target: Path,
    target_label: str,
    stage: str,
    turn_id: str,
    processes: list[subprocess.Popen[bytes]],
) -> bytes:
    process = subprocess.Popen(
        [sys.executable, str(script), stage, target_label],
        cwd=target,
        env=clean_environment(home, turn_id=turn_id),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(process)
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise RuntimeError(f"fake runtime timed out: {stderr.decode().strip()}")
    if process.returncode != 0:
        raise RuntimeError(f"fake runtime failed: {stderr.decode().strip()}")
    return stdout


def snapshot_home(home: Path) -> list[dict]:
    snapshot = []
    for path in sorted(item for item in home.rglob("*") if item.is_file()):
        relative = path.relative_to(home).as_posix()
        content = path.read_bytes()
        item = {
            "path": relative,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        if path.suffix == ".json":
            item["json"] = json.loads(content)
        snapshot.append(item)
    return snapshot


def reconcile(home: Path, expected_turn: str) -> dict:
    """Read, ack, and handle through the public CLI. Repeating is a no-op."""
    _, unread = invoke(home, "inbox", "unread", "--watchtower", "m7-sim-watchtower")
    acked_through = None
    if unread:
        acked_through = max(event["generation"] for event in unread)
        invoke(
            home,
            "ack",
            "--watchtower",
            "m7-sim-watchtower",
            "--through",
            str(acked_through),
        )
    _, pending = invoke(home, "inbox", "pending", "--watchtower", "m7-sim-watchtower")
    matching = [event for event in pending if event["turn_id"] == expected_turn]
    if len(matching) > 1:
        raise RuntimeError("one turn produced more than one pending event")
    handled = False
    if matching:
        event_id = matching[0]["event_id"]
        invoke(home, "inbox", "handle", event_id)
        invoke(home, "inbox", "handle", event_id)
        handled = True
    return {
        "unread_count": len(unread),
        "acked_through": acked_through,
        "pending_count": len(pending),
        "handled_expected_turn": handled,
    }


def run_simulation(fault: str | None = None) -> dict:
    processes: list[subprocess.Popen[bytes]] = []
    with tempfile.TemporaryDirectory(prefix="zxro-m7-sim-") as temporary:
        root = Path(temporary)
        home = root / "home"
        watchtower = root / "watchtower"
        target_root = root / "targets"
        target_a = target_root / "repo-a"
        target_b = target_root / "repo-b"
        for directory in (watchtower, target_a, target_b):
            directory.mkdir(parents=True)
        (watchtower / "AGENTS.md").write_text("deterministic watchtower instructions\n")
        repository_evidence = []
        for label, target, text in (
            ("repo-a", target_a, "target repo a\n"),
            ("repo-b", target_b, "target repo b\n"),
        ):
            run_git(home, target, "init", "--quiet")
            (target / "README.md").write_text(text)
            run_git(home, target, "-c", "user.name=zxro-simulation", "-c", "user.email=zxro-simulation@example.invalid", "add", "README.md")
            run_git(home, target, "-c", "user.name=zxro-simulation", "-c", "user.email=zxro-simulation@example.invalid", "commit", "--quiet", "-m", "initial disposable repository")
            repository_evidence.append(
                {
                    "label": label,
                    "cwd": label,
                    "is_git_repository": run_git(home, target, "rev-parse", "--is-inside-work-tree") == "true",
                    "head": run_git(home, target, "rev-parse", "--verify", "HEAD"),
                }
            )
        fake_runtime = root / "fake-runtime.py"
        fake_runtime.write_text(_FAKE_RUNTIME)

        invoke(
            home,
            "watchtower",
            "create",
            "m7-sim-watchtower",
            "--cwd",
            str(watchtower),
            "--agent",
            "fake-watchtower",
            "--session",
            "fake-watchtower-session",
        )
        invoke(home, "work", "create", "m7-sim-work", "--watchtower", "m7-sim-watchtower")

        turn_evidence = []
        wake_evidence = []
        for ordinal, (stage, target_label, summary) in enumerate(STAGES, start=1):
            if ordinal > MAX_TURNS:
                raise RuntimeError("bounded turn limit exceeded")
            target = {"repo-a": target_a, "repo-b": target_b}[target_label]
            _, created = invoke(
                home,
                "turn",
                "create",
                "--work",
                "m7-sim-work",
                "--agent",
                f"fake-{stage}",
                "--session",
                f"fake-session-{ordinal}",
                "--cwd",
                str(target),
            )
            turn_id = created["id"]
            runtime_output = run_fake_runtime(
                fake_runtime, home, target, target_label, stage, turn_id, processes
            )
            payload = json.dumps(
                {"stage": stage, "target": target_label, "runtime": "fake-runtime"},
                sort_keys=True,
            ).encode()
            invoke(
                home,
                "turn",
                "settle",
                turn_id,
                "--source",
                "fake-runtime",
                "--status",
                "completed",
                "--message",
                summary,
                "--stdin",
                input_bytes=payload,
            )
            _, first_delivery = invoke(home, "inbox", "unread", "--watchtower", "m7-sim-watchtower")
            if len(first_delivery) != 1:
                raise RuntimeError("first settlement did not publish exactly one event")
            first_event_id = first_delivery[0]["event_id"]
            # The retry is deliberately identical. It must not allocate an event.
            invoke(
                home,
                "turn",
                "settle",
                turn_id,
                "--source",
                "fake-runtime",
                "--status",
                "completed",
                "--message",
                summary,
            )
            _, retry_delivery = invoke(home, "inbox", "unread", "--watchtower", "m7-sim-watchtower")
            _, settled = invoke(home, "turn", "show", turn_id)
            event_id = settled["settlement"]["event_id"]
            retry_preserved_event_id = len(retry_delivery) == 1 and retry_delivery[0]["event_id"] == first_event_id == event_id

            # The first event loses both wake notifications and is recovered by
            # polling. Later events receive duplicate notifications, and both
            # reconciliations must remain no-ops after the first handles it.
            notifications = [event_id, event_id]
            if ordinal == 1:
                dropped = list(notifications)
                delivered = []
            else:
                dropped = []
                delivered = notifications
            wake_checks = []
            for notification in delivered:
                wake_checks.append(
                    {"notification": notification, "reconcile": reconcile(home, turn_id)}
                )
            poll_after_drop = reconcile(home, turn_id)
            stage_released = poll_after_drop["handled_expected_turn"] or any(
                check["reconcile"]["handled_expected_turn"] for check in wake_checks
            )
            if not stage_released:
                raise RuntimeError(f"reconciliation did not handle stage {stage}")
            wake_evidence.append(
                {
                    "turn_ordinal": ordinal,
                    "dropped_wake": dropped,
                    "duplicate_wake_count": len(delivered),
                    "wake_reconciliations": wake_checks,
                    "poll_after_dropped_wake": poll_after_drop,
                    "stage_released_after_handling": stage_released,
                }
            )
            turn_evidence.append(
                {
                    "ordinal": ordinal,
                    "stage": stage,
                    "target": target_label,
                    "expected_target_cwd": str(target),
                    "durable_cwd": settled["cwd"],
                    "target_cwd_is_separate": str(target) != str(watchtower),
                    "state": settled["state"],
                    "outcome": settled["outcome"],
                    "summary": settled["summary"],
                    "artifact_count": len(settled.get("artifact_refs", [])),
                    "artifact_refs": list(settled.get("artifact_refs", [])),
                    "public_artifact_refs": list(settled.get("artifact_refs", [])),
                    "turn_id": turn_id,
                    "event_id": event_id,
                    "retry_preserved_event_id": retry_preserved_event_id,
                    "runtime_stdout": runtime_output.decode().strip(),
                    "runtime_evidence": json.loads(
                        (target / "m7-runtime-evidence" / f"{stage}.json").read_text()
                    ),
                }
            )

        _, closed = invoke(home, "work", "close", "m7-sim-work")
        _, closed_again = invoke(home, "work", "close", "m7-sim-work")
        _, final_turn = invoke(home, "turn", "show", turn_evidence[-1]["turn_id"])
        retry_after_close, _ = invoke(
            home,
            "turn",
            "settle",
            final_turn["id"],
            "--source",
            "fake-runtime",
            "--status",
            "completed",
            "--message",
            STAGES[-1][2],
        )
        create_after_close, _ = invoke(
            home,
            "turn",
            "create",
            "--work",
            "m7-sim-work",
            "--agent",
            "fake-after-close",
            "--session",
            "fake-after-close",
            "--cwd",
            str(target_b),
            check=False,
        )
        _, unread_after_close = invoke(
            home, "inbox", "unread", "--watchtower", "m7-sim-watchtower"
        )
        _, pending_after_close = invoke(
            home, "inbox", "pending", "--watchtower", "m7-sim-watchtower"
        )
        _, work_after_close = invoke(home, "work", "show", "m7-sim-work")
        durable_snapshot = snapshot_home(home)
        all_reaped_before_cleanup = all(process.poll() is not None for process in processes)
        report = {
            "schema": "zxro-m7-provider-free-simulation/v1",
            "result": "pending",
            "claims": [
                "The local CLI can coordinate bounded automatic multi-turn work.",
                "Dropped and duplicate wake notifications do not lose or duplicate settlement work.",
                "Settlement retries are idempotent and retain one event per turn.",
                "Closing work stops new turns while allowing an idempotent terminal retry.",
                "The simulation uses only a local file provider and short-lived fake runtimes.",
            ],
            "not_proven": [
                "No live Pi or Claude integration was exercised.",
                "No acpx transport, network provider, credentials, or billable call was exercised.",
                "This is not live-provider M7 completion and does not validate native lifecycle hooks.",
            ],
            "environment": {
                "watchtower_cwd": "watchtower",
                "target_cwds": ["repo-a", "repo-b"],
                "runtime": "fake-runtime subprocess",
                "provider": "built-in local file provider",
                "network_calls": False,
                "billable_calls": False,
                "child_environment": "explicit-safe-whitelist",
                "provider_credentials_in_children": False,
                "provider_config_in_children": False,
                "max_turns": MAX_TURNS,
            },
            "repository_evidence": repository_evidence,
            "turns": turn_evidence,
            "wake_and_reconciliation": wake_evidence,
            "stop_conditions": {
                "turn_count": len(turn_evidence),
                "bounded_by": MAX_TURNS,
                "final_work_state": work_after_close["state"],
                "repeated_close_state": closed_again["state"],
                "terminal_retry_after_close": retry_after_close.returncode == 0,
                "new_turn_after_close_rejected": create_after_close.returncode == 4,
                "unread_after_close": len(unread_after_close),
                "pending_after_close": len(pending_after_close),
                "close_result": closed["state"],
            },
            "cleanup": {
                "fake_runtime_processes_reaped": all_reaped_before_cleanup,
                "temporary_home_removed": False,
            },
            "durable_evidence": durable_snapshot,
        }
    report["cleanup"]["temporary_home_removed"] = not root.exists()
    if not report["cleanup"]["fake_runtime_processes_reaped"]:
        raise RuntimeError("fake runtime process was not reaped")
    if not report["cleanup"]["temporary_home_removed"]:
        raise RuntimeError("temporary simulation home was not removed")
    apply_fault(report, fault)
    validate_contract(report)
    report["result"] = "passed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="write the complete inspectable evidence JSON to this path",
    )
    parser.add_argument(
        "--fault",
        choices=("stop-condition", "provider-environment", "repository", "durable-cwd", "artifact-refs", "swapped-refs", "wrong-artifact-owner", "empty-public-refs"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    try:
        report = run_simulation(args.fault)
    except (OSError, RuntimeError, SimulationContractError, json.JSONDecodeError) as exc:
        print(f"m7 simulation failed: {exc}", file=sys.stderr)
        return 1
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"result": report["result"], "evidence": str(args.evidence)}))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
