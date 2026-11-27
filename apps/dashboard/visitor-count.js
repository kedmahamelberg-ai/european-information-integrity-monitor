(() => {
  "use strict";

  const message = document.getElementById("visitor-message");
  const number = document.getElementById("visitor-number");
  if (!globalThis.crypto?.randomUUID ||
      /bot\b|spider|crawler|headless|ChatGPT-User|Claude-User/i.test(navigator.userAgent)) return;

  let started = false, controller;
  function countVisit() {
    if (started || document.visibilityState === 'hidden' || !window.MonitorAnalytics?.allowed()) return;
    started = true;
    controller = new AbortController();
    const storageKey = "esm-visit-session";
    const idleLimitMs = 30 * 60 * 1000;
    const now = Date.now();
    let token;

    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (saved && typeof saved.token === "string" && Number.isFinite(saved.lastSeen)
          && now - saved.lastSeen >= 0 && now - saved.lastSeen < idleLimitMs) {
        token = saved.token;
      }
    } catch (_) {
      // A blocked storage API should not stop a visit from being counted.
    }

    token ||= crypto.randomUUID();
    try {
      localStorage.setItem(storageKey, JSON.stringify({ token, lastSeen: now }));
    } catch (_) {
      // Private browsing may block storage; the request remains valid.
    }

    fetch("https://jnzibjjejmfochertwco.supabase.co/functions/v1/monitor-visit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      cache: "no-store", keepalive: true,
      signal: controller.signal
    }).then((response) => {
      if (!response.ok) throw new Error("Visit counter unavailable");
      return response.json();
    }).then((data) => {
      if (!message || !number || !window.MonitorAnalytics?.allowed() || !Number.isSafeInteger(data.number) || data.number < 1) return;
      number.textContent = `#${new Intl.NumberFormat("en").format(data.number)}`;
      message.hidden = false;
    }).catch(() => {
      // Keep the thank-you visible if the counter cannot be reached.
    });
  }
  window.addEventListener('monitor-consent', () => {
    if (window.MonitorAnalytics?.allowed()) countVisit();
    else { controller?.abort(); if (message) message.hidden = true; }
  });
  document.addEventListener('visibilitychange', countVisit);
  countVisit();
})();
