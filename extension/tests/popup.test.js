// The panel's logic against a fake `chrome` (no page: the DOM part doesn't run under Node).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  captureEnabled,
  lastResult,
  loadMinMegabytes,
  saveMinMegabytes,
  sendThisVideo,
  setCaptureEnabled,
} from "../chrome/popup.js";

function fakeTabs(url, reply = { ok: true, text: "Sent to SDM." }) {
  const sent = [];
  return {
    sent,
    tabs: { query: async () => (url === undefined ? [] : [{ url }]) },
    runtime: {
      sendMessage: async (message) => {
        sent.push(message);
        return reply;
      },
    },
  };
}

test("'Download this video' sends the current tab's page to the worker", async () => {
  const api = fakeTabs("https://video.example.com/watch?v=abc");
  assert.deepEqual(await sendThisVideo(api), { ok: true, text: "Sent to SDM." });
  assert.deepEqual(api.sent, [{ type: "sdm-video", url: "https://video.example.com/watch?v=abc" }]);
});

test("a tab that isn't a web page isn't sent", async () => {
  for (const url of ["chrome://extensions", "about:blank", undefined]) {
    const api = fakeTabs(url);
    const result = await sendThisVideo(api);
    assert.equal(result.ok, false);
    assert.match(result.text, /video's page/);
    assert.deepEqual(api.sent, []);
  }
});

function fakeChrome({ withStorage = true } = {}) {
  const store = {};
  return {
    store,
    storage: withStorage
      ? {
          local: {
            get: async (key) => ({ [key]: store[key] }),
            set: async (values) => Object.assign(store, values),
          },
        }
      : undefined,
  };
}

test("capture is on from installation", async () => {
  assert.equal(await captureEnabled(fakeChrome()), true);
  assert.equal(await captureEnabled(fakeChrome({ withStorage: false })), true);
});

test("the switch turns capture off and on again, and it is remembered", async () => {
  const api = fakeChrome();
  assert.equal(await setCaptureEnabled(api, false), true);
  assert.equal(await captureEnabled(api), false);
  assert.equal(api.store.sdmCapture.enabled, false);
  await setCaptureEnabled(api, true);
  assert.equal(await captureEnabled(api), true);
});

test("the switch and the minimum size don't overwrite each other", async () => {
  const api = fakeChrome();
  await setCaptureEnabled(api, false);
  await saveMinMegabytes(api, "25");
  assert.deepEqual(api.store.sdmCapture, { enabled: false, minMegabytes: 25 });
  await setCaptureEnabled(api, true);
  assert.deepEqual(api.store.sdmCapture, { enabled: true, minMegabytes: 25 });
});

test("the minimum size is saved only when it is a whole number of megabytes", async () => {
  const api = fakeChrome();
  assert.equal(await loadMinMegabytes(api), 0);
  assert.equal(await saveMinMegabytes(api, "25"), true);
  assert.equal(await loadMinMegabytes(api), 25);
  assert.equal(await saveMinMegabytes(api, "-3"), false);
  assert.equal(await loadMinMegabytes(api), 25);
  assert.equal(await saveMinMegabytes(fakeChrome({ withStorage: false }), "5"), false);
});

test("the panel shows the last problem the icon reported", async () => {
  assert.equal(await lastResult({ action: { getTitle: async () => "SDM" } }), "");
  const api = { action: { getTitle: async () => "SDM: Too many links are waiting in SDM." } };
  assert.equal(await lastResult(api), "Too many links are waiting in SDM.");
});
