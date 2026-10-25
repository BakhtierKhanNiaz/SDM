// The service worker as Firefox runs it: no downloads.onDeterminingFilename, so capture uses
// downloads.onCreated (M11). A fresh copy of background.js is imported with a query string.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

const calls = [];
const listeners = {};
let nativeReply;
let stateAfterCancel;

globalThis.chrome = {
  runtime: {
    id: "sdm@sdm-download-manager",
    onInstalled: { addListener: () => {} },
    onMessage: { addListener: () => {} },
    sendNativeMessage: (host, message) => {
      calls.push(["native", message]);
      return nativeReply();
    },
  },
  contextMenus: { onClicked: { addListener: () => {} }, removeAll: () => {}, create: () => {} },
  action: { setBadgeText: () => {}, setTitle: () => {}, getTitle: async () => "SDM" },
  downloads: {
    // no onDeterminingFilename, as in Firefox
    onCreated: { addListener: (fn) => (listeners.created = fn) },
    cancel: async (id) => calls.push(["cancel", id]),
    search: async ({ id }) => [{ id, state: stateAfterCancel }],
    erase: async ({ id }) => calls.push(["erase", id]),
    download: async (options) => {
      calls.push(["firefox-download", options]);
      return 2;
    },
  },
  storage: { local: { get: async () => ({}) } },
};
console.warn = () => {};

await import("../chrome/background.js?firefox");

beforeEach(() => {
  calls.length = 0;
  nativeReply = () => Promise.resolve({ ok: true });
  stateAfterCancel = "interrupted";
});

const item = (fields = {}) => ({
  id: 3, url: "https://example.com/a.zip", referrer: "https://example.com/", filename: "",
  totalBytes: 0, incognito: false, state: "in_progress", ...fields,
});

test("Firefox captures when the download is created", async () => {
  assert.equal(typeof listeners.created, "function");
  await listeners.created(item());
  assert.deepEqual(calls.map((c) => c[0]), ["cancel", "erase", "native"]);
  assert.equal(calls[2][1].source, "capture");
});

test("a download that finished before it could be stopped stays in Firefox", async () => {
  stateAfterCancel = "complete";
  await listeners.created(item({ id: 4, url: "https://example.com/b.zip" }));
  assert.deepEqual(calls.map((c) => c[0]), ["cancel"]);
});

test("when SDM can't take it, Firefox downloads it once and doesn't capture it again", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "busy" });
  await listeners.created(item({ id: 5, url: "https://example.com/c.zip" }));
  assert.deepEqual(calls.at(-1), ["firefox-download", { url: "https://example.com/c.zip" }]);
  calls.length = 0;
  await listeners.created(item({ id: 6, url: "https://example.com/c.zip" }));
  assert.equal(calls.length, 0);
});
