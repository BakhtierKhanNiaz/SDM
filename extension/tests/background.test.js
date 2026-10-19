// The service worker against a fake `chrome` object that records what it is asked to do.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

const OWN_ID = "obfaejgipbklbamklladnpjikofggica";
const calls = [];
const listeners = {};
let nativeReply;
let granted;
let stored;
let stateAfterCancel;
let restartFails;

globalThis.chrome = {
  runtime: {
    id: OWN_ID,
    onInstalled: { addListener: (fn) => (listeners.installed = fn) },
    sendNativeMessage: (host, message) => {
      calls.push(["native", host, message]);
      return nativeReply();
    },
  },
  contextMenus: {
    onClicked: { addListener: (fn) => (listeners.clicked = fn) },
    removeAll: (done) => {
      calls.push(["removeAll"]);
      done();
    },
    create: (item) => calls.push(["create", item]),
  },
  action: {
    setBadgeText: ({ text }) => calls.push(["badge", text]),
    setTitle: ({ title }) => calls.push(["title", title]),
  },
  permissions: {
    onAdded: { addListener: (fn) => (listeners.permissionAdded = fn) },
    contains: async ({ permissions }) => permissions.every((p) => granted.has(p)),
  },
  downloads: {
    onCreated: { addListener: (fn) => (listeners.downloadCreated = fn) },
    cancel: async (id) => calls.push(["cancel", id]),
    search: async ({ id }) => [{ id, state: stateAfterCancel }],
    erase: async ({ id }) => calls.push(["erase", id]),
    download: async (options) => {
      calls.push(["chrome-download", options]);
      if (restartFails) throw new Error("Download failed");
      return 2;
    },
  },
  storage: { local: { get: async () => stored } },
};
console.warn = () => {}; // keep the test output quiet

await import("../chrome/background.js");

beforeEach(() => {
  calls.length = 0;
  nativeReply = () => Promise.resolve({ ok: true });
  granted = new Set(["downloads", "storage"]);
  stored = {};
  stateAfterCancel = "interrupted";
  restartFails = false;
});

const link = "https://example.com/a.zip";
const page = "https://example.com/files/";
const last = (kind) => calls.findLast((c) => c[0] === kind);
const download = (fields = {}) => ({
  id: 7,
  url: link,
  referrer: page,
  filename: "",
  totalBytes: 0,
  incognito: false,
  state: "in_progress",
  ...fields,
});

test("installing replaces the menu with the one SDM item", () => {
  listeners.installed();
  assert.deepEqual(calls[0], ["removeAll"]);
  assert.equal(calls[1][0], "create");
  assert.equal(calls[1][1].id, "sdm-download-link");
});

test("clicking the item sends the link and its page to SDM's host", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link, pageUrl: page });
  assert.deepEqual(last("native"), [
    "native",
    "com.sdm.bridge",
    { version: 2, type: "download", url: link, referrer: page, source: "menu" },
  ]);
  assert.deepEqual(last("badge"), ["badge", ""]);
});

test("other menu items are ignored", async () => {
  await listeners.clicked({ menuItemId: "someone-else", linkUrl: link });
  assert.equal(calls.length, 0);
});

test("a link SDM can't download is never sent", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: "javascript:alert(1)" });
  assert.equal(calls.some((c) => c[0] === "native"), false);
  assert.deepEqual(last("badge"), ["badge", "!"]);
});

test("each click clears the previous status before sending", async () => {
  nativeReply = () => new Promise(() => {}); // SDM hasn't answered yet
  listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link });
  assert.deepEqual(calls[0], ["badge", ""]);
  assert.deepEqual(calls[1], ["title", "SDM"]);
});

test("a missing host is reported without the link", async () => {
  nativeReply = () => Promise.reject(new Error("Specified native messaging host not found."));
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link });
  const title = last("title")[1];
  assert.match(title, /isn't installed/);
  assert.equal(title.includes(link), false);
});

// ----- capture -----

test("with capture on, Chrome's copy is stopped and erased and SDM gets the download", async () => {
  await listeners.downloadCreated(download({ filename: "C:\\Users\\me\\Downloads\\a.zip" }));
  const kinds = calls.map((c) => c[0]);
  assert.ok(kinds.indexOf("cancel") < kinds.indexOf("erase"));
  assert.ok(kinds.indexOf("erase") < kinds.indexOf("native"));
  assert.deepEqual(last("native")[2], {
    version: 2, type: "download", url: link, referrer: page, filename: "a.zip", source: "capture",
  });
  assert.equal(calls.some((c) => c[0] === "chrome-download"), false);
  assert.deepEqual(last("badge"), ["badge", ""]);
});

test("with capture off nothing is touched", async () => {
  granted = new Set();
  await listeners.downloadCreated(download());
  assert.equal(calls.length, 0);
});

test("a download that finished before it could be stopped stays in Chrome", async () => {
  stateAfterCancel = "complete";
  await listeners.downloadCreated(download());
  assert.deepEqual(calls.map((c) => c[0]), ["cancel"]);
});

test("when SDM can't take it, Chrome downloads it after all", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "busy" });
  await listeners.downloadCreated(download());
  assert.deepEqual(last("chrome-download"), ["chrome-download", { url: link }]);
  assert.match(last("title")[1], /Too many links .* Chrome downloaded it instead\./);
});

test("when SDM's host is missing, Chrome downloads it after all", async () => {
  nativeReply = () => Promise.reject(new Error("Specified native messaging host not found."));
  await listeners.downloadCreated(download());
  assert.deepEqual(last("chrome-download"), ["chrome-download", { url: link }]);
});

test("if Chrome can't restart it either, the tooltip says so", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "not_running" });
  restartFails = true;
  await listeners.downloadCreated(download());
  assert.match(last("title")[1], /Chrome couldn't download it either\./);
});

test("the download Chrome restarts for SDM isn't captured again (no loop)", async () => {
  await listeners.downloadCreated(download({ byExtensionId: OWN_ID }));
  assert.equal(calls.length, 0);
});

test("the minimum size from the panel is respected", async () => {
  stored = { sdmCapture: { minMegabytes: 10 } };
  await listeners.downloadCreated(download({ totalBytes: 1_000_000 }));
  assert.equal(calls.length, 0);
  await listeners.downloadCreated(download({ totalBytes: 20_000_000 }));
  assert.ok(calls.some((c) => c[0] === "native"));
});

test("incognito downloads are left alone", async () => {
  await listeners.downloadCreated(download({ incognito: true }));
  assert.equal(calls.length, 0);
});
