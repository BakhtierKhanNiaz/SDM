// The toolbar panel: "Download this video with SDM" (M12), the video button's switch (M13),
// the switch that turns automatic
// capture off and on again (on from installation, 1.0.1), and the minimum size. The two
// settings are kept in chrome.storage.local.

import { DEFAULT_SETTINGS, parseMinMegabytes, SETTINGS_KEY } from "./capture.js";
import { NOT_A_PAGE_TEXT, PAGE_ACCESS, VIDEO_REQUEST, webUrl } from "./handoff.js";

// The button over videos (M13): on while the user allows page access.
export function videoButtonEnabled(api) {
  return api.permissions.contains(PAGE_ACCESS);
}

// Must run inside the click handler: browsers only show permission prompts for a user action.
export function enableVideoButton(api) {
  return api.permissions.request(PAGE_ACCESS);
}

export function disableVideoButton(api) {
  return api.permissions.remove(PAGE_ACCESS);
}

// Right after turning it on, the open tab gets the button too, without a reload.
export async function addButtonToThisTab(api) {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined || webUrl(tab.url) === null) return false;
  await api.scripting.executeScript({
    target: { tabId: tab.id, allFrames: true },
    files: ["video-button.js"],
  });
  return true;
}

// "Download this video with SDM" (M12): the current tab's address (readable thanks to
// activeTab, only because the user clicked SDM's icon) goes to the worker, which sends it.
export async function sendThisVideo(api) {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  const url = webUrl(tab?.url);
  if (url === null) return { ok: false, text: NOT_A_PAGE_TEXT };
  const reply = await api.runtime.sendMessage({ type: VIDEO_REQUEST, url });
  return reply ?? { ok: false, text: "Couldn't reach SDM." };
}

export async function loadSettings(api) {
  if (!api.storage?.local) return { ...DEFAULT_SETTINGS };
  const stored = await api.storage.local.get(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...(stored?.[SETTINGS_KEY] ?? {}) };
}

// Changes some settings and keeps the others.
async function saveSettings(api, changes) {
  if (!api.storage?.local) return false;
  const settings = { ...(await loadSettings(api)), ...changes };
  await api.storage.local.set({ [SETTINGS_KEY]: settings });
  return true;
}

export async function captureEnabled(api) {
  return (await loadSettings(api)).enabled !== false;
}

export function setCaptureEnabled(api, enabled) {
  return saveSettings(api, { enabled: Boolean(enabled) });
}

// The last result the toolbar icon reports ("SDM: ..." after a problem), or "" when all is well.
export async function lastResult(api) {
  const title = await api.action.getTitle({});
  return title.startsWith("SDM: ") ? title.slice(5) : "";
}

export async function loadMinMegabytes(api) {
  return (await loadSettings(api)).minMegabytes;
}

// Returns false (and saves nothing) for anything but a whole number of megabytes.
export async function saveMinMegabytes(api, text) {
  const value = parseMinMegabytes(text);
  if (value === null) return false;
  return saveSettings(api, { minMegabytes: value });
}

async function setUp() {
  const box = document.getElementById("capture");
  const min = document.getElementById("min");
  const status = document.getElementById("status");
  const video = document.getElementById("video");
  const button = document.getElementById("button");
  button.checked = await videoButtonEnabled(chrome);
  button.addEventListener("change", async () => {
    if (button.checked) {
      const granted = await enableVideoButton(chrome);
      button.checked = granted;
      if (!granted) {
        status.textContent = "The browser didn't allow it.";
        return;
      }
      const added = await addButtonToThisTab(chrome).catch(() => false);
      status.textContent = added
        ? "The SDM button now appears on videos."
        : "The SDM button appears on videos from now on.";
    } else {
      await disableVideoButton(chrome);
      status.textContent = "The SDM button is off.";
    }
  });
  video.addEventListener("click", async () => {
    video.disabled = true;
    status.textContent = "Sending to SDM…";
    const result = await sendThisVideo(chrome);
    status.textContent = result.ok ? "Sent to SDM: choose the quality there." : result.text;
    video.disabled = false;
  });
  const refresh = async () => {
    box.checked = await captureEnabled(chrome);
    min.disabled = !box.checked;
    min.value = String(await loadMinMegabytes(chrome));
  };
  box.addEventListener("change", async () => {
    const saved = await setCaptureEnabled(chrome, box.checked);
    if (!saved) status.textContent = "Couldn't save the setting.";
    else status.textContent = box.checked ? "Downloads now go to SDM." : "Downloads stay in the browser.";
    await refresh();
  });
  min.addEventListener("change", async () => {
    const saved = await saveMinMegabytes(chrome, min.value);
    status.textContent = saved ? "Saved." : "Use a whole number of megabytes (0 to 100000).";
    if (!saved) min.value = String(await loadMinMegabytes(chrome));
  });
  await refresh();
  const last = await lastResult(chrome);
  if (last) status.textContent = `Last time: ${last}`;
}

if (typeof document !== "undefined") setUp();
