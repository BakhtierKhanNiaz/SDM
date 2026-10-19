// Automatic capture (M8): which of Chrome's downloads go to SDM, and what SDM is told.
// Pure logic, no chrome.* calls, so `node --test` can check every rule.
//
// Capture only runs while the user has granted the optional "downloads" permission from the
// toolbar panel; that grant *is* the on switch, so there is no hidden setting to drift.

import { messageFor, webUrl } from "./handoff.js";

export const SETTINGS_KEY = "sdmCapture";
export const DEFAULT_SETTINGS = { minMegabytes: 0 };
export const MAX_MIN_MEGABYTES = 100000;

// Why a download is left to Chrome, or null when SDM should take it.
// `item` is a chrome.downloads.DownloadItem; `ownId` is this extension's ID.
export function reasonToSkip(item, { minMegabytes = 0, ownId } = {}) {
  if (item === null || typeof item !== "object") return "not a download";
  if (item.byExtensionId && item.byExtensionId === ownId) {
    return "handed back to Chrome by SDM's extension"; // never capture our own fallback
  }
  if (item.incognito) return "incognito";
  if (item.state && item.state !== "in_progress") return "not in progress";
  if (webUrl(item.url) === null) return "not an http(s) address"; // blob:, data:, file:, ...
  const size = knownSize(item);
  if (size !== null && size < minMegabytes * 1024 * 1024) return "smaller than the minimum";
  return null;
}

// What SDM is told about a captured download.
export function captureMessage(item) {
  return messageFor(item.url, {
    referrer: item.referrer,
    filename: item.filename,
    size: knownSize(item) ?? undefined,
    mime: item.mime,
    source: "capture",
  });
}

// The panel's minimum size: a whole number of megabytes from 0 to 100000, else null.
export function parseMinMegabytes(text) {
  const value = String(text ?? "").trim();
  if (!/^\d{1,6}$/.test(value)) return null;
  const number = Number(value);
  return number <= MAX_MIN_MEGABYTES ? number : null;
}

function knownSize(item) {
  for (const value of [item.totalBytes, item.fileSize]) {
    if (Number.isInteger(value) && value > 0) return value;
  }
  return null; // Chrome often doesn't know the size yet when the download starts
}
