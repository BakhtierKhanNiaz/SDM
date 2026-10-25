// Does SDM's video button (M13) behave in a real browser?
//
//   node scripts/chrome_bridge_check/video_button_check.mjs     (CHROME=... for Edge)
//
// A throwaway headless Chrome with a temporary profile opens a test page with a 640x360 video,
// runs extension/chrome/video-button.js in it (with chrome.runtime.sendMessage replaced by a
// recorder: no extension and no SDM are involved), then moves and clicks the mouse through the
// DevTools protocol, which gives real (trusted) mouse events. It checks that:
//   - the button appears at the video's top-right corner when the mouse is over the video;
//   - a real click sends {type: "sdm-video", url: <the page>};
//   - the page can't reach the button (closed shadow root) or press it with a script.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CHROME = process.env.CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = readFileSync(resolve(HERE, "..", "..", "extension", "chrome", "video-button.js"), "utf8");
const PAGE = "data:text/html," + encodeURIComponent(
  "<!doctype html><body style='margin:0'>" +
  "<video id=v style='position:absolute;left:100px;top:80px;width:640px;height:360px;" +
  "background:#000'></video></body>",
);

const profile = mkdtempSync(join(tmpdir(), "sdm-video-button-"));
const chrome = spawn(CHROME, [
  `--user-data-dir=${profile}`, "--headless=new", "--remote-debugging-pipe",
  "--no-first-run", "--no-default-browser-check", "--window-size=1280,720", "about:blank",
], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });

let buffer = "";
let nextId = 1;
const waiting = new Map();
chrome.stdio[4].on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  let end;
  while ((end = buffer.indexOf("\0")) >= 0) {
    const msg = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    waiting.get(msg.id)?.(msg);
    waiting.delete(msg.id);
  }
});
function send(method, params = {}, sessionId) {
  const id = nextId++;
  chrome.stdio[3].write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + "\0");
  return new Promise((done) => waiting.set(id, done));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = [];
function check(name, ok, detail = "") {
  results.push(ok);
  console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
}

try {
  const { result: target } = await send("Target.createTarget", { url: PAGE });
  const { result: attached } = await send("Target.attachToTarget", {
    targetId: target.targetId, flatten: true,
  });
  const session = attached.sessionId;
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, session);
    return r.result?.result?.value;
  };
  const mouse = (type, x, y, extra = {}) =>
    send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra }, session);

  await send("Emulation.setDeviceMetricsOverride", {
    width: 1280, height: 720, deviceScaleFactor: 1, mobile: false,
  }, session);
  for (let i = 0; i < 40 && (await evaluate("document.readyState")) !== "complete"; i++) await sleep(100);
  // The page's own world, with chrome.runtime.sendMessage recording instead of sending.
  await evaluate(`window.chrome = { runtime: { sendMessage: async (m) => { (window.sent ??= []).push(m); return { ok: true }; } } }; 1`);
  await evaluate(SCRIPT + "; 1");

  check("no button before the video is touched",
    await evaluate(`getComputedStyle(document.querySelector("sdm-video-button")).display`) === "none");

  await mouse("mouseMoved", 400, 250); // over the video
  await sleep(300);
  const box = await evaluate(`(() => { const r = document.querySelector("sdm-video-button")
    .getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; })()`);
  check("the button appears over the video's top-right corner",
    box && box.right <= 740 && box.right >= 700 && box.top >= 85 && box.top <= 100,
    JSON.stringify(box));

  if (process.env.SHOT) { // SHOT=path.png saves what the page looks like now
    const { writeFileSync } = await import("node:fs");
    const shot = await send("Page.captureScreenshot", { format: "png" }, session);
    writeFileSync(process.env.SHOT, Buffer.from(shot.result.data, "base64"));
  }
  check("the page can't reach the button (closed shadow root)",
    await evaluate(`document.querySelector("sdm-video-button").shadowRoot === null`));
  await evaluate(`document.querySelector("sdm-video-button").click(); 1`); // a scripted click
  await evaluate(`document.querySelector("sdm-video-button").dispatchEvent(new MouseEvent("click", {bubbles: true})); 1`);
  check("a click made by the page's script sends nothing",
    await evaluate(`(window.sent ?? []).length`) === 0);

  // A real click on the "Download" part (left end of the button).
  const x = box.left + 20;
  const y = (box.top + box.bottom) / 2;
  await mouse("mouseMoved", x, y);
  await mouse("mousePressed", x, y);
  await mouse("mouseReleased", x, y);
  await sleep(300);
  const sent = await evaluate(`JSON.stringify(window.sent ?? [])`);
  const href = await evaluate("location.href");
  check("a real click sends the page to SDM as a video",
    sent === JSON.stringify([{ type: "sdm-video", url: href }]), sent.slice(0, 80));
} catch (error) {
  check("the check ran", false, error.message);
} finally {
  chrome.kill();
  await sleep(1000);
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
const ok = results.length > 0 && results.every(Boolean);
console.log(ok ? "OK: the video button works in the browser." : "NOT OK: see above.");
process.exit(ok ? 0 : 1);
