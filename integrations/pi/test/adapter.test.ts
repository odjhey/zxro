import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { classifyTerminalMessage, settlePiTurn, settlementMetadata } from "../adapter.ts";

const TURN = "123e4567-e89b-42d3-a456-426614174000";

async function fakeCli(body = `
const fs = require("node:fs");
const input = fs.readFileSync(0, "utf8");
fs.appendFileSync(process.env.CAPTURE, JSON.stringify({ argv: process.argv.slice(2), input, home: process.env.ZXRO_HOME }) + "\\n");
`) {
  const dir = await mkdtemp(join(tmpdir(), "zxro-pi-"));
  const executable = join(dir, "fake-zxro");
  await writeFile(executable, `#!/usr/bin/env node\n${body}`);
  await chmod(executable, 0o755);
  return { dir, executable, capture: join(dir, "calls.jsonl") };
}

function env(fake: Awaited<ReturnType<typeof fakeCli>>, extra = {}) {
  return { ...process.env, ZXRO_TURN_ID: TURN, ZXRO_HOME: fake.dir, ZXRO_EXECUTABLE: fake.executable, CAPTURE: fake.capture, ...extra };
}

async function calls(path: string) {
  return (await readFile(path, "utf8")).trim().split("\n").filter(Boolean).map(JSON.parse);
}

test("supported completion invokes exactly one addressed argv call", async () => {
  const fake = await fakeCli();
  await settlePiTurn({ role: "assistant", stopReason: "stop" }, env(fake));
  const [call] = await calls(fake.capture);
  assert.deepEqual(call.argv, ["turn", "settle", TURN, "--source", "pi", "--status", "completed", "--message", "Pi agent settled after a completed response.", "--stdin"]);
  assert.equal(call.home, fake.dir);
  assert.deepEqual(JSON.parse(call.input), { event: "agent_settled", stopReason: "stop" });
});

test("failed and cancelled results retain status", async () => {
  for (const [stopReason, status] of [["error", "failed"], ["aborted", "cancelled"]]) {
    const fake = await fakeCli();
    await settlePiTurn({ role: "assistant", stopReason, errorMessage: "diagnostic" }, env(fake));
    assert.equal((await calls(fake.capture))[0].argv[6], status);
  }
});

test("ambiguous semantics and malformed metadata never invoke zxro", async () => {
  const fake = await fakeCli();
  await assert.rejects(settlePiTurn({ role: "assistant", stopReason: "length" }, env(fake)), /ambiguous/);
  await assert.rejects(settlePiTurn({ role: "assistant", stopReason: "stop" }, { ...env(fake), ZXRO_TURN_ID: "bad" }), /UUID/);
  await assert.rejects(settlePiTurn({ role: "assistant", stopReason: "stop" }, { ...env(fake), ZXRO_HOME: "relative" }), /absolute/);
  await assert.rejects(readFile(fake.capture), /ENOENT/);
});

test("metacharacters remain argv and payload data", async () => {
  const fake = await fakeCli();
  const diagnostic = "$(touch nope); `echo bad`\n雪";
  await settlePiTurn({ role: "assistant", stopReason: "error", errorMessage: diagnostic }, env(fake));
  const [call] = await calls(fake.capture);
  assert.equal(JSON.parse(call.input).errorMessage, diagnostic);
  assert.equal(call.argv.length, 10);
});

test("large payload plus immediate nonzero exit is a visible failure", async () => {
  const fake = await fakeCli("process.exit(7)");
  const message = { role: "assistant", stopReason: "error", errorMessage: "x".repeat(2 * 1024 * 1024) };
  await assert.rejects(settlePiTurn(message, env(fake)), /turn settle failed: (stdin failed|exited 7)/);
});

test("closed stdin EPIPE is handled as a visible failure", async () => {
  const fake = await fakeCli("process.stdin.destroy(); setTimeout(() => process.exit(0), 50)");
  const message = { role: "assistant", stopReason: "error", errorMessage: "x".repeat(8 * 1024 * 1024) };
  await assert.rejects(settlePiTurn(message, env(fake)), /turn settle failed: stdin failed/);
});

test("timeout escalates to SIGKILL and waits for child close", async () => {
  const fake = await fakeCli(`
const fs = require("node:fs");
process.on("SIGTERM", () => fs.writeFileSync(process.env.CAPTURE, "term"));
setInterval(() => {}, 1000);
`);
  const started = Date.now();
  await assert.rejects(
    settlePiTurn({ role: "assistant", stopReason: "stop" }, env(fake, { ZXRO_PI_TIMEOUT_MS: "250" })),
    /timed out after 250ms; child closed with SIGKILL/,
  );
  assert.equal(await readFile(fake.capture, "utf8"), "term");
  assert.ok(Date.now() - started >= 300);
});

test("signal termination is a visible failure", async () => {
  const fake = await fakeCli("process.kill(process.pid, 'SIGTERM')");
  await assert.rejects(settlePiTurn({ role: "assistant", stopReason: "stop" }, env(fake)), /terminated by SIGTERM/);
});

test("timeout race cannot turn a post-deadline clean exit into success", async () => {
  const fake = await fakeCli(`
process.on("SIGTERM", () => process.exit(0));
setInterval(() => {}, 1000);
`);
  await assert.rejects(
    settlePiTurn({ role: "assistant", stopReason: "stop" }, env(fake, { ZXRO_PI_TIMEOUT_MS: "250" })),
    /timed out after 250ms; child closed with exit 0/,
  );
});

test("terminal classifier accepts only documented final reasons", () => {
  assert.equal(classifyTerminalMessage({ role: "assistant", stopReason: "stop" }), "completed");
  assert.equal(classifyTerminalMessage({ role: "assistant", stopReason: "error" }), "failed");
  assert.equal(classifyTerminalMessage({ role: "assistant", stopReason: "aborted" }), "cancelled");
  assert.throws(() => classifyTerminalMessage({ role: "assistant", stopReason: "toolUse" }));
  assert.throws(() => settlementMetadata({ ZXRO_TURN_ID: TURN, ZXRO_HOME: "/tmp", ZXRO_PI_TIMEOUT_MS: "0" }));
});

test("duplicate delivery converges through the public CLI", async () => {
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const run = promisify(execFile);
  const home = await mkdtemp(join(tmpdir(), "zxro-pi-real-cli-"));
  const zxro = join(import.meta.dirname, "..", "..", "..", "bin", "zxro");
  const cliEnv = { ...process.env, ZXRO_HOME: home };
  await run(zxro, ["watchtower", "create", "wt", "--cwd", home], { env: cliEnv });
  await run(zxro, ["work", "create", "work", "--watchtower", "wt"], { env: cliEnv });
  const created = await run(zxro, ["--json", "turn", "create", "--work", "work", "--agent", "pi", "--session", "session", "--cwd", home], { env: cliEnv });
  const turnId = JSON.parse(created.stdout).id;
  const adapterEnv = { ...cliEnv, ZXRO_TURN_ID: turnId, ZXRO_EXECUTABLE: zxro };
  await settlePiTurn({ role: "assistant", stopReason: "stop" }, adapterEnv);
  await settlePiTurn({ role: "assistant", stopReason: "stop" }, adapterEnv);
  const shown = JSON.parse((await run(zxro, ["--json", "turn", "show", turnId], { env: cliEnv })).stdout);
  const unread = JSON.parse((await run(zxro, ["--json", "inbox", "unread", "--watchtower", "wt"], { env: cliEnv })).stdout);
  assert.equal(shown.state, "settled");
  assert.equal(shown.settlement.outcome, "completed");
  assert.equal(unread.length, 1);
  assert.equal(unread[0].generation, 1);
  assert.equal(unread[0].event_id, shown.settlement.event_id);
  assert.equal(unread[0].summary.includes("agent_settled"), false);
  assert.equal(unread[0].artifact_refs.length, 1);
});
