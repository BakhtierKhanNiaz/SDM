// Does Chrome find and run SDM's native messaging host? (M7 setup check)
//
//   node scripts/chrome_bridge_check/check.mjs
//
// Starts a throwaway headless Chrome with its own temporary profile (your Chrome and its
// profiles are untouched), loads extension/chrome through the DevTools protocol over a pipe
// (no network port), and calls sendNativeMessage from the extension's service worker with a
// link SDM must refuse. Expected: REPLY {"ok":false,"error":"bad_request"}, which proves Chrome
// found the registered host and the host ran, without starting SDM or writing any file.
// The extension's ID comes from its folder, so it matches the ID you registered.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CHROME = process.env.CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const EXTENSION = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "extension", "chrome");
const REFUSED = { version: 1, type: "download", url: "file:///C:/must-be-refused" };

const profile = mkdtempSync(join(tmpdir(), "sdm-chrome-check-"));
const chrome = spawn(CHROME, [
  `--user-data-dir=${profile}`,
  "--headless=new",
  "--remote-debugging-pipe", // DevTools over fds 3 and 4, not a port
  "--enable-unsafe-extension-debugging", // allows Extensions.loadUnpacked
  "--no-first-run",
  "--no-default-browser-check",
  "about:blank",
], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });

const toChrome = chrome.stdio[3];
let buffer = "";
let nextId = 1;
const waiting = new Map();
chrome.stdio[4].on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  let end;
  while ((end = buffer.indexOf("\0")) >= 0) { // messages end with a NUL byte
    const msg = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    waiting.get(msg.id)?.(msg);
    waiting.delete(msg.id);
  }
});
function send(method, params = {}, sessionId) {
  const id = nextId++;
  toChrome.write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + "\0");
  return new Promise((done) => waiting.set(id, done));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let outcome = "FAILED";
try {
  const loaded = await send("Extensions.loadUnpacked", { path: EXTENSION });
  const id = loaded.result?.id;
  console.log(`extension: ${id ?? JSON.stringify(loaded.error)}`);
  let worker;
  for (let i = 0; i < 40 && id && !worker; i++) {
    await sleep(250);
    const { result } = await send("Target.getTargets");
    worker = result.targetInfos.find((t) => t.type === "service_worker" && t.url.includes(id));
  }
  if (!worker) throw new Error("the extension's service worker didn't start");
  const { result } = await send("Target.attachToTarget", { targetId: worker.targetId, flatten: true });
  // Right after loading, the worker may run before the extension APIs are set up ("chrome is
  // not defined"): ask again for a few seconds.
  for (let attempt = 0; attempt < 20; attempt++) {
    const evaluated = await send("Runtime.evaluate", {
      expression: `typeof chrome === "undefined" || !chrome.runtime ? "NOT READY" : ` +
        `chrome.runtime.sendNativeMessage("com.sdm.bridge", ${JSON.stringify(REFUSED)})` +
        `.then(r => "REPLY " + JSON.stringify(r), e => "ERROR " + e.message)`,
      awaitPromise: true,
    }, result.sessionId);
    outcome = evaluated.result?.result?.value ?? JSON.stringify(evaluated);
    if (outcome !== "NOT READY") break;
    await sleep(250);
  }
} catch (error) {
  outcome = `FAILED: ${error.message}`;
} finally {
  chrome.kill();
  await sleep(1000);
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
console.log(outcome);
const ok = outcome === 'REPLY {"ok":false,"error":"bad_request"}';
console.log(ok
  ? "OK: the browser found SDM's host, and the host ran and refused the test link."
  : "NOT OK: see the line above (\"host not found\" means the registration is missing).");
process.exit(ok ? 0 : 1);
