import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  HOST_NAME,
  MAX_URL_LENGTH,
  bareName,
  describeFailure,
  describeReply,
  menuItem,
  menuMessage,
  messageFor,
} from "../chrome/handoff.js";

const LINK = "https://example.com/files/a.zip?token=abc";
const PAGE = "https://example.com/files/";

test("the menu appears on http and https links and players only", () => {
  const item = menuItem();
  assert.deepEqual(item.contexts, ["link", "video", "audio"]);
  assert.deepEqual(item.targetUrlPatterns, ["http://*/*", "https://*/*"]);
  assert.equal(item.title, "Download with SDM");
});

test("a normal link becomes a version 2 message with its page as the referrer", () => {
  assert.deepEqual(menuMessage({ linkUrl: LINK, pageUrl: PAGE }), {
    version: 2,
    type: "download",
    url: LINK,
    referrer: PAGE,
    source: "menu",
  });
});

test("a link inside a frame uses the frame as the referrer", () => {
  const message = menuMessage({ linkUrl: LINK, pageUrl: PAGE, frameUrl: "https://cdn.example/f" });
  assert.equal(message.referrer, "https://cdn.example/f");
});

test("a right-click on a player sends the player's own address", () => {
  const video = "https://media.example/clip.mp4";
  assert.equal(menuMessage({ mediaType: "video", srcUrl: video, pageUrl: PAGE }).url, video);
  assert.equal(
    menuMessage({ mediaType: "audio", srcUrl: video, linkUrl: LINK, pageUrl: PAGE }).url,
    video,
  );
  // a streaming player has no real file address
  assert.equal(menuMessage({ mediaType: "video", srcUrl: "blob:https://x/1", pageUrl: PAGE }), null);
});

test("links SDM doesn't download produce no message", () => {
  for (const url of [
    "javascript:alert(1)",
    "file:///C:/Windows/win.ini",
    "data:text/plain,hi",
    "blob:https://example.com/123",
    "ftp://example.com/a.zip",
    "chrome://settings",
    "https://user:secret@example.com/a.zip",
    "not a url",
    "",
    "https://example.com/" + "a".repeat(MAX_URL_LENGTH),
    undefined,
    null,
    42,
  ]) {
    assert.equal(messageFor(url), null, `should refuse ${String(url).slice(0, 40)}`);
  }
});

test("hints that don't pass their check are left out, not sent", () => {
  const message = messageFor(LINK, {
    referrer: "file:///C:/page.html",
    filename: "a:b.zip",
    size: -5,
    mime: "text/plain\r\nX: 1",
    source: "page-script",
  });
  assert.deepEqual(message, { version: 2, type: "download", url: LINK, source: "menu" });
});

test("only the bare file name of Chrome's path is sent", () => {
  assert.equal(bareName("C:\\Users\\me\\Downloads\\report (1).pdf"), "report (1).pdf");
  assert.equal(bareName("/home/me/a.zip"), "a.zip");
  for (const bad of ["", "C:\\folder\\", "..", " . ", "a\u0000.zip", "x".repeat(256), null, 7]) {
    assert.equal(bareName(bad), null, `should drop ${JSON.stringify(bad)}`);
  }
});

test("replies turn into short, generic messages", () => {
  assert.deepEqual(describeReply({ ok: true }), { ok: true, text: "Sent to SDM." });
  assert.equal(describeReply({ ok: false, error: "busy" }).ok, false);
  assert.match(describeReply({ ok: false, error: "not_running" }).text, /didn't start/);
  assert.match(describeReply({ ok: false, error: "something-new" }).text, /couldn't take/);
  assert.match(describeReply(undefined).text, /couldn't take/);
  assert.match(describeReply("ok").text, /couldn't take/);
});

test("Chrome's errors say whether the bridge is installed", () => {
  assert.match(
    describeFailure(new Error("Specified native messaging host not found.")).text,
    /isn't installed/,
  );
  assert.match(
    describeFailure(new Error("Access to the specified native messaging host is forbidden.")).text,
    /different extension ID/,
  );
  assert.match(describeFailure(new Error("Native host has exited.")).text, /Couldn't reach/);
});

test("the extension asks for four permissions at install and no access to websites", () => {
  const manifest = JSON.parse(readFileSync(new URL("../chrome/manifest.json", import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual([...manifest.permissions].sort(),
    ["contextMenus", "downloads", "nativeMessaging", "storage"]);
  for (const risky of ["host_permissions", "optional_host_permissions", "optional_permissions",
    "content_scripts",
    "externally_connectable", "web_accessible_resources"]) {
    assert.equal(manifest[risky], undefined, `${risky} must not be declared`);
  }
  assert.equal(manifest.action.default_popup, "popup.html");
  assert.equal(HOST_NAME, "com.sdm.bridge");
});
