// The toolbar panel: the switch that turns automatic capture off and on again (on from
// installation, 1.0.1), and the minimum size. Both are kept in chrome.storage.local.

import { DEFAULT_SETTINGS, parseMinMegabytes, SETTINGS_KEY } from "./capture.js";

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
