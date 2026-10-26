(() => {
  'use strict';
  // Only the public production site may send advertising requests.
  if (location.protocol !== 'https:' || location.hostname !== 'monitor.hamelberg-ai.com') return;
  const publisher = 'pub-5170234738371400';
  let enabled = false;
  window.adsbygoogle = window.adsbygoogle || [];
  window.adsbygoogle.pauseAdRequests = 1;
  window.googlefc = window.googlefc || {};
  window.googlefc.callbackQueue = window.googlefc.callbackQueue || [];

  function setPermission(allowed) {
    window.adsbygoogle.pauseAdRequests = allowed ? 0 : 1;
    const wasEnabled = enabled;
    enabled = allowed;
    // A fresh page removes already-rendered ads after consent withdrawal.
    if (!allowed && wasEnabled) location.reload();
  }
  window.googlefc.callbackQueue.push({CONSENT_API_READY: () => {
    if (typeof window.__tcfapi !== 'function') return;
    window.__tcfapi('addEventListener', 2, (data, success) => {
      if (!success || !data || !['tcloaded', 'useractioncomplete'].includes(data.eventStatus)) return;
      setPermission(data.gdprApplies === false || Boolean(
        data.gdprApplies === true && data.tcString &&
        data.purpose?.consents?.[1] && data.vendor?.consents?.[755]
      ));
    });
  }});
  window.googlefc.callbackQueue.push({CONSENT_MODE_DATA_READY: () => {
    if (typeof window.googlefc.getGoogleConsentModeValues !== 'function') return;
    const consent = window.googlefc.getGoogleConsentModeValues();
    const keys = ['adStoragePurposeConsentStatus', 'adUserDataPurposeConsentStatus', 'adPersonalizationPurposeConsentStatus'];
    if (keys.every(key => [1, 3].includes(consent?.[key]))) setPermission(true);
    else if (keys.some(key => consent?.[key] === 2)) setPermission(false);
  }});

  const message = document.createElement('script');
  message.async = true;
  message.src = 'https://fundingchoicesmessages.google.com/i/' + publisher + '?ers=1';
  document.head.appendChild(message);
  document.querySelectorAll('[data-ad-privacy]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      window.googlefc.callbackQueue.push(() => {
        if (typeof window.googlefc.showRevocationMessage === 'function') {
          window.googlefc.showRevocationMessage();
        }
      });
    });
  });
})();
