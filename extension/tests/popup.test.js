// The panel's logic against a fake `chrome` (no page: the DOM part doesn't run under Node).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  captureEnabled,
  disableCapture,
  enableCapture,
  loadMinMegabytes,
  saveMinMegabytes,
} from "../chrome/popup.js";

function fakeChrome({ allow = true, withStorage = true } = {}) {
  const granted = new Set();
  const store = {};
  const requests = [];
  return {
    requests,
    store,
    permissions: {
      contains: async ({ permissions }) => permissions.every((p) => granted.has(p)),
      request: async ({ permissions }) => {
        requests.push(["request", permissions]);
        if (allow) permissions.forEach((p) => granted.add(p));
        return allow;
      },
      remove: async ({ permissions }) => {
        requests.push(["remove", permissions]);
        permissions.forEach((p) => granted.delete(p));
        return true;
      },
    },
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

test("capture is off until the user turns it on", async () => {
  const api = fakeChrome();
  assert.equal(await captureEnabled(api), false);
  assert.equal(api.requests.length, 0); // nothing is asked for on its own
});

test("turning it on asks Chrome for downloads (and storage for the minimum size)", async () => {
  const api = fakeChrome();
  assert.equal(await enableCapture(api), true);
  assert.deepEqual(api.requests, [["request", ["downloads", "storage"]]]);
  assert.equal(await captureEnabled(api), true);
});

test("if the user says no in Chrome's prompt, capture stays off", async () => {
  const api = fakeChrome({ allow: false });
  assert.equal(await enableCapture(api), false);
  assert.equal(await captureEnabled(api), false);
});

test("turning it off gives the downloads permission back", async () => {
  const api = fakeChrome();
  await enableCapture(api);
  await disableCapture(api);
  assert.deepEqual(api.requests.at(-1), ["remove", ["downloads"]]);
  assert.equal(await captureEnabled(api), false);
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
