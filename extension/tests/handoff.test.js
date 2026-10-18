import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  HOST_NAME,
  MAX_URL_LENGTH,
  describeFailure,
  describeReply,
  menuItem,
  messageFor,
} from "../chrome/handoff.js";

test("the menu appears on http and https links only", () => {
  const item = menuItem();
  assert.deepEqual(item.contexts, ["link"]);
  assert.deepEqual(item.targetUrlPatterns, ["http://*/*", "https://*/*"]);
  assert.equal(item.title, "Download with SDM");
});

test("a normal link becomes exactly the message SDM accepts", () => {
  const url = "https://example.com/files/a.zip?token=abc";
  assert.deepEqual(messageFor(url), { version: 1, type: "download", url });
});

test("links SDM doesn't download produce no message", () => {
  for (const url of [
    "javascript:alert(1)",
    "file:///C:/Windows/win.ini",
    "data:text/plain,hi",
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

test("the extension asks for no more than two permissions", () => {
  const manifest = JSON.parse(readFileSync(new URL("../chrome/manifest.json", import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual([...manifest.permissions].sort(), ["contextMenus", "nativeMessaging"]);
  for (const risky of ["host_permissions", "content_scripts", "optional_permissions",
    "externally_connectable", "web_accessible_resources"]) {
    assert.equal(manifest[risky], undefined, `${risky} must not be declared`);
  }
  assert.equal(HOST_NAME, "com.sdm.bridge");
});
