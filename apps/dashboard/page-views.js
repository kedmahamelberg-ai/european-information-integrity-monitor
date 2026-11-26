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
  function recordVisiblePage() {
    if (sent || document.visibilityState !== 'visible') return;
    sent = true;
    document.removeEventListener('visibilitychange', recordVisiblePage);
    fetch('https://jnzibjjejmfochertwco.supabase.co/rest/v1/rpc/monitor_record_page_view', {
      method: 'POST',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      keepalive: true,
      headers: {apikey: 'sb_publishable_g2yJxXm4YqDfKTFGLar34Q_F6v8BdXE', 'Content-Type': 'application/json'},
      body: JSON.stringify({p_path: path, p_source: arrivalSource()})
    }).catch(() => {});
  }
  document.addEventListener('visibilitychange', recordVisiblePage);
  recordVisiblePage();
})();
