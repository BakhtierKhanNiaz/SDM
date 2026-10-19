// The toolbar panel: turning capture on asks Chrome for the optional "downloads" permission
// (Chrome shows its own "Manage your downloads" prompt); turning it off gives it back.
// "storage" is requested at the same time, only to remember the minimum size.

import { DEFAULT_SETTINGS, parseMinMegabytes, SETTINGS_KEY } from "./capture.js";

const CAPTURE = { permissions: ["downloads"] };

export function captureEnabled(api) {
  return api.permissions.contains(CAPTURE);
}

// Must run inside the click handler: Chrome only shows permission prompts for a user action.
export function enableCapture(api) {
  return api.permissions.request({ permissions: ["downloads", "storage"] });
}

export function disableCapture(api) {
  return api.permissions.remove(CAPTURE);
}

// The last result the toolbar icon reports ("SDM: ..." after a problem), or "" when all is well.
export async function lastResult(api) {
  const title = await api.action.getTitle({});
  return title.startsWith("SDM: ") ? title.slice(5) : "";
}

export async function loadMinMegabytes(api) {
  if (!api.storage?.local) return DEFAULT_SETTINGS.minMegabytes;
  const stored = await api.storage.local.get(SETTINGS_KEY);
  return stored?.[SETTINGS_KEY]?.minMegabytes ?? DEFAULT_SETTINGS.minMegabytes;
}

// Returns false (and saves nothing) for anything but a whole number of megabytes.
export async function saveMinMegabytes(api, text) {
  const value = parseMinMegabytes(text);
  if (value === null || !api.storage?.local) return false;
  await api.storage.local.set({ [SETTINGS_KEY]: { minMegabytes: value } });
  return true;
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
    if (box.checked) {
      const granted = await enableCapture(chrome);
      status.textContent = granted ? "Downloads now go to SDM." : "Chrome didn't allow it.";
    } else {
      await disableCapture(chrome);
      status.textContent = "Downloads stay in Chrome.";
    }
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
