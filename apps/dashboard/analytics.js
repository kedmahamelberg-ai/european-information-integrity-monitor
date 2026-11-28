(() => {
  'use strict';
  const MEASUREMENT_ID = 'G-1JQ1MNNVKR';
  const production = location.protocol === 'https:' && location.hostname === 'monitor.hamelberg-ai.com';

  // Measure on every device without placing Google Analytics cookies.
  // Prior analytics choices no longer gate basic cookieless measurement.
  try {
    localStorage.removeItem('esm-analytics-consent-v1');
    for (const name of document.cookie.split(';').map(part => part.trim().split('=')[0])
      .filter(name => /^_ga(?:_|$)|^_gid$|^_gat/.test(name))) {
      document.cookie = name + '=;Max-Age=0;path=/;SameSite=Lax';
      const parts = location.hostname.split('.');
      while (parts.length > 1) {
        document.cookie = name + '=;Max-Age=0;path=/;domain=.' + parts.join('.') + ';SameSite=Lax';
        parts.shift();
      }
    }
  } catch (_) { /* Blocked storage does not block cookieless measurement. */ }

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window['ga-disable-' + MEASUREMENT_ID] = !production;
  window.gtag('consent', 'default', {
    analytics_storage: 'denied', ad_storage: 'denied',
    ad_user_data: 'denied', ad_personalization: 'denied'
  });
  window.gtag('set', 'ads_data_redaction', true);
  window.MonitorAnalytics = {
    allowed: () => production,
    event(name, parameters = {}) {
      if (!production || !/^[a-z][a-z0-9_]{0,39}$/.test(name)) return;
      const safe = {};
      for (const key of ['kind', 'channel', 'placement']) {
        if (typeof parameters[key] === 'string') safe[key] = parameters[key].slice(0, 80);
      }
      window.gtag('event', name, {...safe,
        page_location: location.origin + location.pathname, page_referrer: '', page_title: document.title});
    }
  };
  if (!production) return;
  window.gtag('js', new Date());
  window.gtag('config', MEASUREMENT_ID, {
    allow_google_signals: false, allow_ad_personalization_signals: false,
    page_location: location.origin + location.pathname, page_referrer: ''
  });
  let restoredViewPending = false;
  function recordRestoredView() {
    if (!restoredViewPending || document.visibilityState !== 'visible') return;
    restoredViewPending = false;
    window.MonitorAnalytics.event('page_view');
  }
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    restoredViewPending = true;
    recordRestoredView();
  });
  document.addEventListener('visibilitychange', recordRestoredView);
  const script = document.createElement('script');
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);
})();
