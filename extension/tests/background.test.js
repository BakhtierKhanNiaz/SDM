// The service worker against a fake `chrome` object that records what it is asked to do.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

const calls = [];
const listeners = {};
let nativeReply = () => Promise.resolve({ ok: true });

globalThis.chrome = {
  runtime: {
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
};
console.warn = () => {}; // keep the test output quiet

await import("../chrome/background.js");

beforeEach(() => {
  calls.length = 0;
  nativeReply = () => Promise.resolve({ ok: true });
});

const link = "https://example.com/a.zip";

test("installing replaces the menu with the one SDM item", () => {
  listeners.installed();
  assert.deepEqual(calls[0], ["removeAll"]);
  assert.equal(calls[1][0], "create");
  assert.equal(calls[1][1].id, "sdm-download-link");
});

test("clicking the item sends the link to SDM's host and clears the badge", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link });
  assert.deepEqual(calls[0], ["native", "com.sdm.bridge", { version: 1, type: "download", url: link }]);
  assert.deepEqual(calls.find((c) => c[0] === "badge"), ["badge", ""]);
});

test("other menu items are ignored", async () => {
  await listeners.clicked({ menuItemId: "someone-else", linkUrl: link });
  assert.equal(calls.length, 0);
});

test("a link SDM can't download is never sent", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: "javascript:alert(1)" });
  assert.equal(calls.some((c) => c[0] === "native"), false);
  assert.deepEqual(calls.find((c) => c[0] === "badge"), ["badge", "!"]);
});

test("an error reply shows a badge and a reason in the tooltip", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "busy" });
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link });
  assert.deepEqual(calls.find((c) => c[0] === "badge"), ["badge", "!"]);
  assert.match(calls.find((c) => c[0] === "title")[1], /^SDM: Too many links/);
});

test("a missing host is reported without the link", async () => {
  nativeReply = () => Promise.reject(new Error("Specified native messaging host not found."));
  await listeners.clicked({ menuItemId: "sdm-download-link", linkUrl: link });
  const title = calls.find((c) => c[0] === "title")[1];
  assert.match(title, /isn't installed/);
  assert.equal(title.includes(link), false);
});
