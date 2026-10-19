// The extension's logic, kept free of chrome.* calls so `node --test` can check it.
// SDM checks every message again on its side; these checks only avoid pointless handoffs.

export const HOST_NAME = "com.sdm.bridge";
export const MENU_ID = "sdm-download-link";
export const MAX_URL_LENGTH = 8192;

export function menuItem() {
  return {
    id: MENU_ID,
    title: "Download with SDM",
    contexts: ["link"],
    targetUrlPatterns: ["http://*/*", "https://*/*"],
  };
}

// The one message SDM accepts, or null when the link isn't something SDM downloads.
export function messageFor(linkUrl) {
  if (typeof linkUrl !== "string" || linkUrl.length === 0 || linkUrl.length > MAX_URL_LENGTH) {
    return null;
  }
  let parsed;
  try {
    parsed = new URL(linkUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  if (parsed.username !== "" || parsed.password !== "") return null;
  return { version: 1, type: "download", url: linkUrl };
}

const ERROR_TEXT = {
  bad_origin: "SDM refused this extension.",
  bad_request: "SDM can't download this link.",
  busy: "Too many links are waiting in SDM; finish those first.",
  not_running: "SDM didn't start. Open SDM and try again.",
  failed: "SDM couldn't take the link.",
};

export const NOT_A_LINK_TEXT = "SDM only downloads http:// and https:// links.";

// What to show after SDM replied: {ok, text}.
export function describeReply(reply) {
  if (reply !== null && typeof reply === "object" && reply.ok === true) {
    return { ok: true, text: "Sent to SDM." };
  }
  const code = reply !== null && typeof reply === "object" ? reply.error : undefined;
  return { ok: false, text: ERROR_TEXT[code] ?? ERROR_TEXT.failed };
}

// What to show when Chrome couldn't run SDM's host at all.
export function describeFailure(error) {
  const message = String(error?.message ?? error);
  if (message.includes("host not found")) {
    return {
      ok: false,
      text: "SDM's browser bridge isn't installed for this extension. If you just installed it, quit Chrome completely and open it again.",
    };
  }
  if (message.includes("Access to the specified native messaging host is forbidden")) {
    return { ok: false, text: "SDM's browser bridge is installed for a different extension ID." };
  }
  return { ok: false, text: "Couldn't reach SDM." };
}
