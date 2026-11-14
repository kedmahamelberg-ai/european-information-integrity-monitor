(() => {
  'use strict';
  const MEASUREMENT_ID = 'G-1JQ1MNNVKR';
  const consentKey = 'esm-analytics-consent-v1';
  const lifetime = 180 * 86400000;
  const production = location.protocol === 'https:' && location.hostname === 'monitor.hamelberg-ai.com';
  let consent = null, loaded = false, banner, privacyButton;
  try {
    const saved = JSON.parse(localStorage.getItem(consentKey));
    if (saved?.version === 1 && typeof saved.analytics === 'boolean' &&
        Number.isFinite(saved.at) && saved.at <= Date.now() && Date.now() - saved.at < lifetime) consent = saved;
  } catch (_) { /* A blocked store leaves the choice unknown. */ }

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window['ga-disable-' + MEASUREMENT_ID] = true;
  window.gtag('consent', 'default', {
    analytics_storage: 'denied', ad_storage: 'denied',
    ad_user_data: 'denied', ad_personalization: 'denied'
  });
  const allowed = () => production && consent?.analytics === true;
  function clearAnalyticsStorage() {
    try {
      for (const name of document.cookie.split(';').map(x => x.trim().split('=')[0])
        .filter(x => /^_ga(?:_|$)|^_gid$|^_gat/.test(x))) {
        document.cookie = name + '=;Max-Age=0;path=/;SameSite=Lax';
        const parts = location.hostname.split('.');
        while (parts.length > 1) {
          document.cookie = name + '=;Max-Age=0;path=/;domain=.' + parts.join('.') + ';SameSite=Lax';
          parts.shift();
        }
      }
      localStorage.removeItem('esm-visit-session');
    } catch (_) { /* Storage may be unavailable. Measurement remains disabled. */ }
  }
  function loadGA() {
    if (!allowed() || loaded) return;
    loaded = true;
    window['ga-disable-' + MEASUREMENT_ID] = false;
    window.gtag('consent', 'update', {analytics_storage: 'granted'});
    window.gtag('js', new Date());
    window.gtag('config', MEASUREMENT_ID, {
      allow_google_signals: false, allow_ad_personalization_signals: false,
      page_location: location.origin + location.pathname, page_referrer: ''
    });
    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(MEASUREMENT_ID);
    document.head.appendChild(script);
  }
  function choose(analytics) {
    const wasLoaded = loaded;
    consent = {version: 1, analytics: analytics === true, at: Date.now()};
    try { localStorage.setItem(consentKey, JSON.stringify(consent)); } catch (_) {}
    if (banner) banner.hidden = true;
    if (consent.analytics) loadGA();
    else {
      window['ga-disable-' + MEASUREMENT_ID] = true;
      window.gtag('consent', 'update', {analytics_storage: 'denied'});
      clearAnalyticsStorage();
    }
    window.dispatchEvent(new CustomEvent('monitor-consent', {detail: {analytics: allowed()}}));
    privacyButton?.focus();
    // Unload an already-running tag when permission is withdrawn.
    if (!consent.analytics && wasLoaded) location.reload();
  }
  window.MonitorAnalytics = {
    allowed, choose,
    event(name, parameters = {}) {
      if (!allowed() || !loaded || !/^[a-z][a-z0-9_]{0,39}$/.test(name)) return;
      window.gtag('event', name, {...parameters,
        page_location: location.origin + location.pathname, page_title: document.title});
    }
  };
  function element(tag, text) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  }
  function renderChoice() {
    const style = element('style');
    style.textContent = '#monitor-cookie-choice{position:fixed;inset:auto 16px 16px;z-index:10000;max-width:660px;margin:auto;padding:20px;background:#fff;color:#10243c;border:1px solid #8a9ca8;border-radius:12px;box-shadow:0 4px 24px #0003;font:16px/1.5 system-ui;max-height:80vh;overflow:auto}#monitor-cookie-choice[hidden]{display:none}#monitor-cookie-choice h2{font:600 21px/1.3 system-ui;margin:0 0 10px}#monitor-cookie-choice p{margin:0 0 14px}#monitor-cookie-choice div{display:flex;gap:12px;flex-wrap:wrap}#monitor-cookie-choice button{background:#fff;color:#10243c;border:1px solid #526575;border-radius:6px;min-height:44px;padding:10px 16px;font:600 15px system-ui;cursor:pointer}#monitor-cookie-choice a{color:#12646b;text-decoration:underline}#monitor-cookie-choice button:focus-visible,#monitor-cookie-privacy:focus-visible{outline:3px solid #12646b;outline-offset:3px}';
    document.head.appendChild(style);
    banner = element('section');
    banner.id = 'monitor-cookie-choice';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', 'Analytics cookies');
    banner.hidden = consent !== null;
    banner.appendChild(element('h2', 'May we use analytics cookies?'));
    banner.appendChild(element('p', 'With your permission, Google Analytics measures visits and interactions, and our visit counter records your visit. You can read the Monitor without accepting. Your choice applies on phones, tablets and computers.'));
    const actions = element('div');
    for (const [label, value] of [['Accept analytics', true], ['Reject analytics', false]]) {
      const button = element('button', label);
      button.type = 'button';
      button.addEventListener('click', () => choose(value));
      actions.appendChild(button);
    }
    const link = element('a', 'Privacy details');
    link.href = '/privacy.html';
    banner.appendChild(actions);
    banner.appendChild(link);
    document.body.appendChild(banner);
    privacyButton = element('button', 'Analytics cookie choices');
    privacyButton.id = 'monitor-cookie-privacy';
    privacyButton.type = 'button';
    privacyButton.addEventListener('click', () => {
      banner.hidden = false;
      banner.querySelector('button')?.focus();
    });
    (document.querySelector('footer .advertising-privacy') || document.querySelector('footer') || document.body).appendChild(privacyButton);
  }
  if (!consent?.analytics) clearAnalyticsStorage();
  loadGA();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderChoice, {once: true});
  else renderChoice();
})();
