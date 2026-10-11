(() => {
  "use strict";

  // Shared with kedmahamelberg.com; use hostname and page path to segment ESM.
  const MEASUREMENT_ID = "G-0KJEDKBCY5";
  if (!/^G-[A-Z0-9]+$/.test(MEASUREMENT_ID) || !/^https?:$/.test(location.protocol)) return;

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag("consent", "default", {
    analytics_storage: "granted",
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied"
  });
  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: location.origin + location.pathname,
    page_referrer: ""
  });

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);

  window.MonitorAnalytics = {
    event(name, parameters = {}) {
      if (!/^[a-z][a-z0-9_]{0,39}$/.test(name)) return;
      window.gtag("event", name, {
        ...parameters,
        page_location: location.origin + location.pathname,
        page_title: document.title
      });
    }
  };
})();
