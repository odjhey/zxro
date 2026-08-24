import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";

export type TerminalStatus = "completed" | "failed" | "cancelled";
export type PiTerminalMessage = {
  role: "assistant";
  stopReason: string;
  errorMessage?: string;
};

const TURN_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function classifyTerminalMessage(message: unknown): TerminalStatus {
  if (!message || typeof message !== "object" || (message as PiTerminalMessage).role !== "assistant") {
    throw new Error("agent_settled has no final assistant message");
  }
  switch ((message as PiTerminalMessage).stopReason) {
    case "stop": return "completed";
    case "error": return "failed";
    case "aborted": return "cancelled";
    default:
      throw new Error(`agent_settled has ambiguous stop reason: ${String((message as PiTerminalMessage).stopReason)}`);
  }
}

export function settlementMetadata(env: NodeJS.ProcessEnv): { turnId: string; home: string; executable: string; timeoutMs: number } {
  const turnId = env.ZXRO_TURN_ID?.trim() ?? "";
  const home = env.ZXRO_HOME?.trim() ?? "";
  if (!TURN_ID.test(turnId)) throw new Error("ZXRO_TURN_ID must be a UUID");
  if (!home || !isAbsolute(home)) throw new Error("ZXRO_HOME must be an absolute path");
  const timeoutMs = Number(env.ZXRO_PI_TIMEOUT_MS ?? "10000");
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 300000) {
    throw new Error("ZXRO_PI_TIMEOUT_MS must be an integer from 1 to 300000");
  }
  return { turnId, home, executable: env.ZXRO_EXECUTABLE?.trim() || "zxro", timeoutMs };
}

const KILL_GRACE_MS = 100;

async function run(executable: string, args: string[], input: string, env: NodeJS.ProcessEnv, timeoutMs: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn(executable, args, { env, shell: false, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
    let stderr = "";
    let stdinError: Error | undefined;
    let timedOut = false;
    let finished = false;
    let killTimer: NodeJS.Timeout | undefined;
    const clearTimers = () => {
      clearTimeout(timeoutTimer);
      if (killTimer) clearTimeout(killTimer);
    };
    const timeoutTimer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      killTimer = setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
      }, KILL_GRACE_MS);
    }, timeoutMs);

    child.stdout.resume();
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => {
      if (stderr.length < 8192) stderr += String(chunk).slice(0, 8192 - stderr.length);
    });
    child.stdin.on("error", (error) => { stdinError = error; });
    child.on("error", (error) => {
      if (finished) return;
      finished = true;
      clearTimers();
      reject(error);
    });
    child.on("close", (code, signal) => {
      if (finished) return;
      finished = true;
      clearTimers();
      if (timedOut) reject(new Error(`timed out after ${timeoutMs}ms; child closed with ${signal ?? `exit ${code}`}`));
      else if (stdinError) reject(new Error(`stdin failed: ${stdinError.message}`));
      else if (code === 0 && signal === null) resolve();
      else reject(new Error(signal ? `terminated by ${signal}` : `exited ${code}: ${stderr.trim()}`));
    });
    child.stdin.end(input);
  });
}

export async function settlePiTurn(message: unknown, env: NodeJS.ProcessEnv = process.env): Promise<void> {
  const status = classifyTerminalMessage(message);
  const { turnId, home, executable, timeoutMs } = settlementMetadata(env);
  const terminal = message as PiTerminalMessage;
  const summary = status === "completed"
    ? "Pi agent settled after a completed response."
    : status === "failed"
      ? "Pi agent settled after a failed response."
      : "Pi agent settled after cancellation.";
  const payload = JSON.stringify({ event: "agent_settled", stopReason: terminal.stopReason, errorMessage: terminal.errorMessage });
  try {
    await run(executable, ["turn", "settle", turnId, "--source", "pi", "--status", status, "--message", summary, "--stdin"], payload, { ...env, ZXRO_HOME: home }, timeoutMs);
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    throw new Error(`zxro turn settle failed: ${detail}`, { cause });
  }
}
