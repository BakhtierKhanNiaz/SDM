// The service worker against a fake `chrome` object that records what it is asked to do.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

const OWN_ID = "abcdefghijklmnopabcdefghijklmnop"; // any valid-looking extension ID
const calls = [];
const listeners = {};
let nativeReply;
let stored;
let restartFails;

globalThis.chrome = {
  runtime: {
    id: OWN_ID,
    onInstalled: { addListener: (fn) => (listeners.installed = fn) },
    onMessage: { addListener: (fn) => (listeners.message = fn) },
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
    getTitle: async () => "SDM",
    setBadgeText: ({ text }) => calls.push(["badge", text]),
    setTitle: ({ title }) => calls.push(["title", title]),
  },
  downloads: {
    onDeterminingFilename: { addListener: (fn) => (listeners.determining = fn) },
    cancel: async (id) => calls.push(["cancel", id]),
    erase: async ({ id }) => calls.push(["erase", id]),
    download: async (options) => {
      calls.push(["chrome-download", options]);
      if (restartFails) throw new Error("Download failed");
      return 2;
    },
  },
  storage: { local: { get: async () => stored } },
  // M13: page access (optional) and the video button's registration
  permissions: {
    contains: async () => pageAccess,
    onAdded: { addListener: () => {} },
    onRemoved: { addListener: () => {} },
  },
  scripting: {
    getRegisteredContentScripts: async () => [...registered].map((id) => ({ id })),
    registerContentScripts: async (scripts) => {
      scripts.forEach((s) => registered.add(s.id));
      calls.push(["register", scripts[0]]);
    },
    unregisterContentScripts: async ({ ids }) => {
      ids.forEach((id) => registered.delete(id));
      calls.push(["unregister", ids]);
    },
  },
};
let pageAccess = false;
const registered = new Set();
console.warn = () => {}; // keep the test output quiet

const { syncVideoButton } = await import("../chrome/background.js");

beforeEach(() => {
  calls.length = 0;
  nativeReply = () => Promise.resolve({ ok: true });
  stored = {}; // as after installing: nothing saved, so capture is on
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

test("the video button runs on pages exactly while page access is allowed", async () => {
  pageAccess = false;
  await syncVideoButton();
  assert.equal(registered.size, 0);
  pageAccess = true; // the user turned it on in the panel
  await syncVideoButton();
  const [, script] = last("register");
  assert.deepEqual(script.js, ["video-button.js"]);
  assert.deepEqual(script.matches, ["http://*/*", "https://*/*"]);
  await syncVideoButton(); // already registered: not twice
  assert.equal(calls.filter((c) => c[0] === "register").length, 1);
  pageAccess = false; // taken back (panel or browser settings)
  await syncVideoButton();
  assert.deepEqual(last("unregister"), ["unregister", ["sdm-video-button"]]);
  assert.equal(registered.size, 0);
});

test("a click on the video button (a content script) sends the page as a video", async () => {
  const watch = "https://video.example.com/watch?v=1";
  const reply = await panelAsks({ type: "sdm-video", url: watch }, { id: OWN_ID, tab: { id: 3 } });
  assert.equal(reply.ok, true);
  assert.deepEqual(last("native")[2], { version: 2, type: "download", url: watch, source: "video" });
});

test("installing replaces the menu with SDM's two items", () => {
  listeners.installed();
  assert.deepEqual(calls[0], ["removeAll"]);
  assert.deepEqual(calls.slice(1).map((c) => [c[0], c[1].id]), [
    ["create", "sdm-download-link"],
    ["create", "sdm-download-video"],
  ]);
});

test("'Download this video' sends the page, marked as a video", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-video", pageUrl: page, srcUrl: "blob:x" });
  assert.deepEqual(last("native")[2], { version: 2, type: "download", url: page, source: "video" });
});

test("'Download this video' on a page SDM can't use says so", async () => {
  await listeners.clicked({ menuItemId: "sdm-download-video", pageUrl: "file:///C:/a.html" });
  assert.equal(calls.some((c) => c[0] === "native"), false);
  assert.match(last("title")[1], /video's page/);
});

// The toolbar panel's button: answered asynchronously through sendResponse.
function panelAsks(request, sender = { id: OWN_ID }) {
  return new Promise((resolve) => {
    const later = listeners.message(request, sender, resolve);
    if (later !== true) resolve(undefined);
  });
}

test("the panel's button sends the tab's page as a video", async () => {
  const reply = await panelAsks({ type: "sdm-video", url: page });
  assert.deepEqual(reply, { ok: true, text: "Sent to SDM." });
  assert.equal(last("native")[2].source, "video");
});

test("only SDM's own panel can ask, and only for web pages", async () => {
  assert.equal(await panelAsks({ type: "sdm-video", url: page }, { id: "someone-else" }), undefined);
  assert.equal(await panelAsks({ type: "other", url: page }), undefined);
  assert.equal(calls.some((c) => c[0] === "native"), false);
  const reply = await panelAsks({ type: "sdm-video", url: "chrome://settings" });
  assert.equal(reply.ok, false);
  assert.equal(calls.some((c) => c[0] === "native"), false);
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

// Runs Chrome's "determining filename" step and waits until the extension has finished with it.
async function determine(item) {
  let answers = 0;
  const done = new Promise((resolve) => {
    const keepsAnswerOpen = listeners.determining(item, () => {
      answers += 1;
      calls.push(["suggest"]);
    });
    assert.equal(keepsAnswerOpen, true);
    setTimeout(resolve, 20);
  });
  await done;
  await new Promise((r) => setTimeout(r, 20));
  return answers;
}

test("right after installing, Chrome's copy is stopped before it asks where to save", async () => {
  const answers = await determine(download({ filename: "C:\\Users\\me\\Downloads\\a.zip" }));
  assert.equal(answers, 1); // Chrome is always answered, exactly once
  const kinds = calls.map((c) => c[0]);
  assert.ok(kinds.indexOf("cancel") < kinds.indexOf("suggest"));
  assert.ok(kinds.indexOf("erase") < kinds.indexOf("native"));
  assert.deepEqual(last("native")[2], {
    version: 2, type: "download", url: link, referrer: page, filename: "a.zip", source: "capture",
  });
  assert.equal(calls.some((c) => c[0] === "chrome-download"), false);
  assert.deepEqual(last("badge"), ["badge", ""]);
});

test("with the panel's switch off nothing is touched, but Chrome is still answered", async () => {
  stored = { sdmCapture: { enabled: false, minMegabytes: 0 } };
  assert.equal(await determine(download()), 1);
  assert.deepEqual(calls, [["suggest"]]);
});

test("when SDM can't take it, Chrome downloads it once, and that restart isn't captured", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "busy" });
  await determine(download());
  assert.deepEqual(last("chrome-download"), ["chrome-download", { url: link }]);
  assert.match(last("title")[1], /Too many links .* Chrome downloaded it instead\./);

  // Chrome now starts the restarted download, *without* marking it as the extension's.
  calls.length = 0;
  assert.equal(await determine(download({ id: 8 })), 1);
  assert.deepEqual(calls, [["suggest"]]); // left alone: no cancel, no SDM, no second restart
});

test("the hand-back is remembered once: a later click on the same link is captured again", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "busy" });
  await determine(download());
  await determine(download({ id: 8 })); // the restart: skipped
  nativeReply = () => Promise.resolve({ ok: true });
  calls.length = 0;
  await determine(download({ id: 9 })); // the user clicks again later
  assert.ok(calls.some((c) => c[0] === "native"));
});

test("when SDM's host is missing, Chrome downloads it after all", async () => {
  nativeReply = () => Promise.reject(new Error("Specified native messaging host not found."));
  await determine(download({ url: "https://example.com/b.zip" }));
  assert.deepEqual(last("chrome-download"), ["chrome-download", { url: "https://example.com/b.zip" }]);
  assert.match(last("title")[1], /isn't installed/);
});

test("if Chrome can't restart it either, the tooltip says so", async () => {
  nativeReply = () => Promise.resolve({ ok: false, error: "not_running" });
  restartFails = true;
  await determine(download({ url: "https://example.com/c.zip" }));
  assert.match(last("title")[1], /Chrome couldn't download it either\./);
});

test("a download marked as the extension's own isn't captured", async () => {
  assert.equal(await determine(download({ byExtensionId: OWN_ID })), 1);
  assert.deepEqual(calls, [["suggest"]]);
});

test("the minimum size from the panel is respected", async () => {
  stored = { sdmCapture: { minMegabytes: 10 } };
  await determine(download({ url: "https://example.com/small.zip", totalBytes: 1_000_000 }));
  assert.equal(calls.some((c) => c[0] === "native"), false);
  await determine(download({ url: "https://example.com/big.zip", totalBytes: 20_000_000 }));
  assert.ok(calls.some((c) => c[0] === "native"));
});

test("incognito downloads are left alone", async () => {
  await determine(download({ incognito: true }));
  assert.deepEqual(calls, [["suggest"]]);
});

test("an unexpected error still answers Chrome, so the download never hangs", async () => {
  stored = undefined;
  globalThis.chrome.storage.local.get = async () => {
    throw new Error("storage broke");
  };
  try {
    assert.equal(await determine(download({ url: "https://example.com/d.zip" })), 1);
  } finally {
    globalThis.chrome.storage.local.get = async () => stored;
  }
});
