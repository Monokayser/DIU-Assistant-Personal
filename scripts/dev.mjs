import { spawn } from "node:child_process";
import process from "node:process";

const children = new Set();
let shuttingDown = false;
let apiMonitor = null;

const apiHost = normalizeApiHost(process.env.API_HOST || "127.0.0.1");
const apiPort = String(process.env.API_PORT || "8765").trim() || "8765";
const apiBaseUrl = `http://${apiHost}:${apiPort}`;

function start(name, command, args) {
  const child = spawn(command, args, {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
  });

  children.add(child);

  child.on("exit", (code, signal) => {
    children.delete(child);
    if (shuttingDown) return;

    shuttingDown = true;
    for (const running of children) {
      running.kill("SIGTERM");
    }

    if (signal) {
      process.kill(process.pid, signal);
      return;
    }

    process.exitCode = code ?? 0;
    console.log(`${name} stopped.`);
  });
}

function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    child.kill("SIGTERM");
  }
  process.once("beforeExit", () => process.exit(0));
  setTimeout(() => process.exit(0), 800).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

if (await apiIsRunning()) {
  console.log(`API server already running on ${apiBaseUrl}`);
  startApiMonitor();
} else {
  start("API server", "python3", ["app/main.py"]);
}
start("Vite dev server", "npm", ["--prefix", "frontend", "run", "dev"]);

async function apiIsRunning() {
  try {
    const response = await fetch(`${apiBaseUrl}/api/health`, {
      signal: AbortSignal.timeout(800),
    });
    return response.ok;
  } catch {
    return false;
  }
}

function normalizeApiHost(host) {
  const value = String(host || "").trim() || "127.0.0.1";
  return value === "0.0.0.0" ? "127.0.0.1" : value;
}

function startApiMonitor() {
  if (apiMonitor) return;
  let missedChecks = 0;
  apiMonitor = setInterval(async () => {
    if (shuttingDown) return;
    const healthy = await apiIsRunning();
    if (healthy) {
      missedChecks = 0;
      return;
    }
    missedChecks += 1;
    if (missedChecks < 2) return;
    console.error(`API server is no longer reachable at ${apiBaseUrl}. Stopping dev servers.`);
    shutdown("SIGTERM");
  }, 2500);
  apiMonitor.unref();
}
