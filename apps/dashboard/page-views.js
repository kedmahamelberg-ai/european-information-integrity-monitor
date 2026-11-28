(() => {
  'use strict';
  if (location.origin !== 'https://monitor.hamelberg-ai.com' ||
      /bot\b|spider|crawler|headless|ChatGPT-User|Claude-User/i.test(navigator.userAgent)) return;

  const path = location.pathname.replace(/\/index\.html$/, '/');
  const pages = new Set(['/', '/field-wire/', '/about.html', '/contact.html', '/research.html', '/privacy.html']);
  if (path.length > 140 || (!pages.has(path) &&
      !/^\/(?:field-wire\/\d{4}-\d{2}-\d{2}|findings\/[a-z0-9]+(?:-[a-z0-9]+)*)\/$/.test(path))) return;

  const namedSources = new Map([
    ['google', 'google'], ['google.com', 'google'],
    ['chatgpt', 'chatgpt'], ['chatgpt.com', 'chatgpt'], ['chat.openai.com', 'chatgpt'],
    ['claude', 'claude'], ['claude.ai', 'claude'], ['claude.com', 'claude']
  ]);

  function arrivalSource() {
    let host = '';
    try {
      const referrer = new URL(document.referrer);
      if (referrer.protocol === 'http:' || referrer.protocol === 'https:') host = referrer.hostname;
    } catch {}
    if (host === location.hostname) return 'internal';
    const domain = host.replace(/^www\./, '');
    if (/^google\.(?:com|[a-z]{2,3}|(?:co|com)\.[a-z]{2})$/.test(domain)) return 'google';
    const provider = namedSources.get(domain);
    if (provider) return provider;
    const tag = new URLSearchParams(location.search).get('utm_source')?.trim().toLowerCase();
    return namedSources.get(tag) || (host ? 'other_referral' : 'direct_or_unknown');
  }

  let sent = false;
  let restored = false;
  function recordVisiblePage() {
    if (sent || document.visibilityState !== 'visible') return;
    sent = true;
    const endpoint = 'https://jnzibjjejmfochertwco.supabase.co/rest/v1/rpc/';
    const options = {
      method: 'POST', credentials: 'omit', referrerPolicy: 'no-referrer', keepalive: true,
      headers: {apikey: 'sb_publishable_g2yJxXm4YqDfKTFGLar34Q_F6v8BdXE', 'Content-Type': 'application/json'}
    };
    fetch(endpoint + 'monitor_record_page_view', {
      ...options, body: JSON.stringify({p_path: path, p_source: restored ? 'direct_or_unknown' : arrivalSource()})
    }).then(async response => {
      const badge = document.querySelector('[data-finding-views]');
      if (!response.ok || !badge) return;
      const result = await fetch(endpoint + 'monitor_finding_views', {...options, body: JSON.stringify({p_path: path})});
      if (!result.ok) return;
      const count = await result.json();
      if (Number.isSafeInteger(count) && count >= 4) {
        badge.textContent = new Intl.NumberFormat().format(count) + ' page views in the last 30 days';
        badge.hidden = false;
      }
    }).catch(() => {});
  }
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    restored = true;
    sent = false;
    recordVisiblePage();
  });
  document.addEventListener('visibilitychange', recordVisiblePage);
  recordVisiblePage();
})();
