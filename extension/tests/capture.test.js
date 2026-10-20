import assert from "node:assert/strict";
import { test } from "node:test";

import { captureMessage, parseMinMegabytes, reasonToSkip } from "../chrome/capture.js";

const OWN_ID = "abcdefghijklmnopabcdefghijklmnop"; // any valid-looking extension ID
const item = (fields = {}) => ({
  id: 1,
  url: "https://example.com/files/a.zip",
  referrer: "https://example.com/files/",
  filename: "",
  totalBytes: 0,
  fileSize: 0,
  mime: "application/zip",
  incognito: false,
  state: "in_progress",
  ...fields,
});

test("an ordinary download is captured", () => {
  assert.equal(reasonToSkip(item(), { ownId: OWN_ID }), null);
});

test("downloads SDM's extension handed back to Chrome are never captured again", () => {
  assert.match(reasonToSkip(item({ byExtensionId: OWN_ID }), { ownId: OWN_ID }), /handed back/);
  // another extension's download is still a normal download
  assert.equal(reasonToSkip(item({ byExtensionId: "x".repeat(32) }), { ownId: OWN_ID }), null);
});

test("incognito, finished and non-web downloads stay in Chrome", () => {
  assert.equal(reasonToSkip(item({ incognito: true }), { ownId: OWN_ID }), "incognito");
  assert.equal(reasonToSkip(item({ state: "complete" }), { ownId: OWN_ID }), "not in progress");
  for (const url of ["blob:https://example.com/1", "data:text/plain,hi", "file:///C:/a.zip"]) {
    assert.equal(reasonToSkip(item({ url }), { ownId: OWN_ID }), "not an http(s) address");
  }
});

test("the minimum size applies only when Chrome already knows the size", () => {
  const small = item({ totalBytes: 500_000 });
  assert.equal(reasonToSkip(small, { minMegabytes: 1, ownId: OWN_ID }), "smaller than the minimum");
  assert.equal(reasonToSkip(small, { minMegabytes: 0, ownId: OWN_ID }), null);
  assert.equal(reasonToSkip(item({ totalBytes: 2_000_000 }), { minMegabytes: 1 }), null);
  assert.equal(reasonToSkip(item({ totalBytes: 0 }), { minMegabytes: 1 }), null); // unknown yet
});

test("SDM is told the link, its page, the name and the size", () => {
  const message = captureMessage(item({
    filename: "C:\\Users\\me\\Downloads\\a.zip",
    totalBytes: 12_673_227,
  }));
  assert.deepEqual(message, {
    version: 2,
    type: "download",
    url: "https://example.com/files/a.zip",
    referrer: "https://example.com/files/",
    filename: "a.zip",
    size: 12_673_227,
    mime: "application/zip",
    source: "capture",
  });
});

test("the minimum size field takes whole megabytes only", () => {
  assert.equal(parseMinMegabytes("0"), 0);
  assert.equal(parseMinMegabytes(" 25 "), 25);
  assert.equal(parseMinMegabytes("100000"), 100000);
  for (const bad of ["", "-1", "1.5", "1e3", "abc", "100001", "9999999", null]) {
    assert.equal(parseMinMegabytes(bad), null, `should refuse ${bad}`);
  }
});
