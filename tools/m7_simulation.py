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

# The simulator must not accidentally pass provider credentials to its fake
# child. The zxro CLI does not need any credential to use its local provider.
_PROVIDER_ENV_MARKERS = (
    "ANTHROPIC",
    "OPENAI",
    "GOOGLE_API",
    "AZURE_OPENAI",
    "ACPX",
    "PI_",
    "CLAUDE",
)

_FAKE_RUNTIME = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

stage, target_label = sys.argv[1:3]
required = ("ZXRO_HOME", "ZXRO_TURN_ID", "ZXRO_WORK_ID", "ZXRO_WATCHTOWER_ID")
if any(not os.environ.get(name) for name in required):
    raise SystemExit("fake runtime received incomplete ZXRO metadata")
record = {
    "runtime": "fake-runtime",
    "stage": stage,
    "target": target_label,
    "turn_id": os.environ["ZXRO_TURN_ID"],
    "work_id": os.environ["ZXRO_WORK_ID"],
    "watchtower_id": os.environ["ZXRO_WATCHTOWER_ID"],
}
out = Path.cwd() / "m7-runtime-evidence" / f"{stage}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(record, sort_keys=True) + "\n")
print(json.dumps({"stage": stage, "target": target_label}, sort_keys=True))
'''


def clean_environment(home: Path, *, turn_id: str | None = None) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in _PROVIDER_ENV_MARKERS)
    }
    environment["ZXRO_HOME"] = str(home)
    if turn_id:
        environment.update(
            {
                "ZXRO_TURN_ID": turn_id,
                "ZXRO_WORK_ID": "m7-sim-work",
                "ZXRO_WATCHTOWER_ID": "m7-sim-watchtower",
            }
        )
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


def run_simulation() -> dict:
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
        (target_a / "README.md").write_text("target repo a\n")
        (target_b / "README.md").write_text("target repo b\n")
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
            _, settled = invoke(home, "turn", "show", turn_id)
            event_id = settled["settlement"]["event_id"]

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
                    "target_cwd_is_separate": str(target) != str(watchtower),
                    "state": settled["state"],
                    "outcome": settled["outcome"],
                    "summary": settled["summary"],
                    "artifact_count": len(settled.get("artifact_refs", [])),
                    "turn_id": turn_id,
                    "event_id": event_id,
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
            "result": "passed",
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
                "network": False,
                "credentials": False,
                "billable_calls": False,
                "provider_env_filtered": True,
                "max_turns": MAX_TURNS,
            },
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
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="write the complete inspectable evidence JSON to this path",
    )
    args = parser.parse_args(argv)
    try:
        report = run_simulation()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
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
