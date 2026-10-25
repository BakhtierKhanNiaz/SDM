// SDM's video button (M13): a small SDM button at the top-right of a playing or hovered video.
// Clicking it sends this page's address to SDM, which asks the quality (like "Download this
// video with SDM"). It runs only after the user turned it on in SDM's toolbar panel and the
// browser asked for page access.
//
// It reads nothing from the page but where its videos are on screen; it sends only the page's
// address, and only on a real click. The button lives in a closed shadow root, so page scripts
// can't see, restyle or press it; a click the page fakes (isTrusted false) is ignored.
(() => {
  const MIN_WIDTH = 200; // smaller videos are icons, previews or ads
  const MIN_HEIGHT = 120;
  const MARGIN = 10;
  const HIDE_AFTER_MS = 2500; // after the mouse leaves a paused video

  function bigEnough(rect) {
    return rect.width >= MIN_WIDTH && rect.height >= MIN_HEIGHT;
  }

  // Where the button's top-right corner goes for a video at `rect` (from
  // getBoundingClientRect) in a viewport of `width` x `height`, or null when it shouldn't show.
  function buttonPlace(rect, width, height) {
    if (!bigEnough(rect)) return null;
    if (rect.bottom < MIN_HEIGHT / 2 || rect.top > height - 40) return null; // mostly off-screen
    if (rect.right < 60 || rect.left > width - 60) return null;
    return {
      right: Math.max(MARGIN, width - Math.min(rect.right, width) + MARGIN),
      top: Math.max(rect.top, 0) + MARGIN,
    };
  }

  if (globalThis.__SDM_TEST__) {
    globalThis.__SDM_TEST__.videoButton = { bigEnough, buttonPlace };
    return;
  }
  if (globalThis.__sdmVideoButton) return; // injected twice (turned on with the page open)
  globalThis.__sdmVideoButton = true;

  const LOGO =
    '<svg viewBox="0 0 256 256" width="18" height="18" aria-hidden="true"><defs>' +
    '<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4F46E5"/>' +
    '<stop offset="1" stop-color="#0EA5E9"/></linearGradient></defs>' +
    '<path d="M128 10L230 69V187L128 246L26 187V69Z" fill="url(#g)"/>' +
    '<path d="M128 64v108M80 128l48 48 48-48" fill="none" stroke="#fff" stroke-width="30" ' +
    'stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const host = document.createElement("sdm-video-button");
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; position: fixed; z-index: 2147483647; display: none; }
      .bar { display: flex; align-items: center; gap: 2px; font: 600 13px/1 "Segoe UI",
             system-ui, sans-serif; filter: drop-shadow(0 2px 6px rgba(0,0,0,.35)); }
      button { all: unset; cursor: pointer; display: flex; align-items: center; gap: 7px;
               background: #111827ee; color: #fff; border-radius: 8px; padding: 6px 10px;
               border: 1px solid #ffffff40; /* stays visible on dark videos */ }
      button:hover { background: #1f2937; }
      button:focus-visible { outline: 2px solid #60a5fa; }
      .close { padding: 7px 8px; font-weight: 400; opacity: .8; }
      .text { white-space: nowrap; }
    </style>
    <div class="bar">
      <button class="send" title="Download this video with SDM">${LOGO}
        <span class="text">Download</span></button>
      <button class="close" title="Hide on this page" aria-label="Hide">✕</button>
    </div>`;
  const send = root.querySelector(".send");
  const text = root.querySelector(".text");
  const close = root.querySelector(".close");
  (document.documentElement || document).appendChild(host);

  let video = null; // the video the button belongs to
  let hovering = false;
  let hideTimer = 0;
  let closed = false;

  function place() {
    if (closed || !video || !video.isConnected || document.fullscreenElement) {
      host.style.display = "none";
      return;
    }
    const where = buttonPlace(video.getBoundingClientRect(), innerWidth, innerHeight);
    if (!where) {
      host.style.display = "none";
      return;
    }
    host.style.right = `${where.right}px`;
    host.style.top = `${where.top}px`;
    host.style.display = "block";
  }

  function follow() {
    place();
    if (host.style.display === "block") requestAnimationFrame(follow); // scrolling, resizing
  }

  function showFor(target) {
    if (closed || !(target instanceof HTMLVideoElement)) return;
    if (!bigEnough(target.getBoundingClientRect())) return;
    clearTimeout(hideTimer);
    if (video !== target) text.textContent = "Download";
    video = target;
    follow();
  }

  function hideSoon() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (!hovering && video && video.paused) host.style.display = "none";
    }, HIDE_AFTER_MS);
  }

  document.addEventListener("play", (event) => showFor(event.target), true);
  document.addEventListener("mouseover", (event) => {
    const target = event.target;
    if (target instanceof HTMLVideoElement) showFor(target);
  }, true);
  document.addEventListener("mouseout", (event) => {
    if (event.target === video) hideSoon();
  }, true);
  host.addEventListener("mouseenter", () => { hovering = true; clearTimeout(hideTimer); });
  host.addEventListener("mouseleave", () => { hovering = false; hideSoon(); });

  send.addEventListener("click", async (event) => {
    event.stopPropagation();
    if (!event.isTrusted) return; // only a real click by the user
    text.textContent = "Sending…";
    try {
      const reply = await chrome.runtime.sendMessage({ type: "sdm-video", url: location.href });
      text.textContent = reply?.ok ? "Sent to SDM" : "SDM: " + (reply?.text ?? "not reached");
    } catch {
      text.textContent = "Reload the page"; // the extension was updated or removed meanwhile
    }
  });
  close.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!event.isTrusted) return;
    closed = true; // until the page is reloaded
    host.style.display = "none";
  });
})();
