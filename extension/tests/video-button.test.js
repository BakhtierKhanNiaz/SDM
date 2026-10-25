// Where the video button goes (M13). The page part needs a browser; its placing rules are
// checked here by running the script with a test hook instead of a page.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../chrome/video-button.js", import.meta.url), "utf8");
const sandbox = { __SDM_TEST__: {} };
sandbox.globalThis = sandbox;
vm.runInNewContext(source, sandbox);
const { bigEnough } = sandbox.__SDM_TEST__.videoButton;
// Objects made in the sandbox belong to another realm: compare them as plain data.
const buttonPlace = (...args) => {
  const place = sandbox.__SDM_TEST__.videoButton.buttonPlace(...args);
  return place === null ? null : { ...place };
};

const rect = (left, top, width, height) => ({
  left, top, width, height, right: left + width, bottom: top + height,
});

test("small videos (previews, icons, ads) get no button", () => {
  assert.equal(bigEnough(rect(0, 0, 640, 360)), true);
  assert.equal(bigEnough(rect(0, 0, 160, 90)), false);
  assert.equal(buttonPlace(rect(0, 0, 160, 90), 1280, 720), null);
});

test("the button sits at the video's top-right corner, inside the window", () => {
  assert.deepEqual(buttonPlace(rect(100, 80, 640, 360), 1280, 720), { right: 550, top: 90 });
  // a video wider than the window, or scrolled partly above it, keeps the button visible
  assert.deepEqual(buttonPlace(rect(-50, -100, 1400, 600), 1280, 720), { right: 10, top: 10 });
});

test("a video mostly off-screen gets no button", () => {
  assert.equal(buttonPlace(rect(0, -400, 640, 360), 1280, 720), null); // scrolled past
  assert.equal(buttonPlace(rect(0, 700, 640, 360), 1280, 720), null); // not reached yet
  assert.equal(buttonPlace(rect(1250, 0, 640, 360), 1280, 720), null); // off to the right
});

test("nothing is added to the page in test mode", () => {
  assert.equal(sandbox.__sdmVideoButton, undefined);
});
