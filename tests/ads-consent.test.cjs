const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/ads.js'), 'utf8');

function harness(hostname = 'monitor.hamelberg-ai.com', {mobile = false, userAgent = ''} = {}) {
  const scripts = [];
  let tcf, reloads = 0;
  const window = {
    __tcfapi: (command, version, listener) => { tcf = listener; },
    matchMedia: () => ({matches: mobile}),
    navigator: {userAgent}
  };
  const location = {protocol: 'https:', hostname, reload: () => reloads++};
  const document = {createElement: () => ({}), head: {appendChild: s => scripts.push(s)}, querySelectorAll: () => []};
  vm.runInNewContext(source, {window, location, document});
  const api = window.googlefc?.callbackQueue.find(x => x.CONSENT_API_READY);
  api?.CONSENT_API_READY();
  return {window, scripts, send: data => tcf(data, true), reloads: () => reloads};
}

test('ads remain paused until a complete permitted TCF decision', () => {
  const h = harness();
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  h.send({eventStatus: 'tcloaded', gdprApplies: true, tcString: 'decision', purpose: {consents: {1: true}}});
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  h.send({eventStatus: 'useractioncomplete', gdprApplies: true, tcString: 'decision', purpose: {consents: {1: true}}, vendor: {consents: {755: true}}});
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 0);
  h.send({eventStatus: 'useractioncomplete', gdprApplies: true, tcString: 'decision'});
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  assert.equal(h.reloads(), 1);
});

test('non-applicable regions can serve; unknown or denied consent cannot enable ads', () => {
  const h = harness();
  const callback = h.window.googlefc.callbackQueue.find(x => x.CONSENT_MODE_DATA_READY).CONSENT_MODE_DATA_READY;
  h.window.googlefc.getGoogleConsentModeValues = () => ({});
  callback();
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  h.send({eventStatus: 'tcloaded', gdprApplies: false});
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 0);
  h.window.googlefc.getGoogleConsentModeValues = () => ({adStoragePurposeConsentStatus: 2});
  callback();
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  assert.equal(h.reloads(), 1);
});

test('previews do not load consent service or enable advertising', () => {
  const h = harness('localhost');
  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.adsbygoogle, undefined);
});

test('mobile screens and phones load no ad or consent scripts', () => {
  for (const options of [{mobile: true}, {userAgent: 'iPhone'}]) {
    const h = harness('monitor.hamelberg-ai.com', options);
    assert.equal(h.scripts.length, 0);
    assert.equal(h.window.adsbygoogle, undefined);
  }
});

test('mobile screens do not start analytics or the visit counter', () => {
  const window = {matchMedia: () => ({matches: true}), navigator: {userAgent: ''}};
  const analytics = fs.readFileSync(path.join(__dirname, '../apps/dashboard/analytics.js'), 'utf8');
  vm.runInNewContext(analytics, {window, location: {protocol: 'https:'}});
  assert.equal(window.gtag, undefined);
  let removed = false;
  const visitor = fs.readFileSync(path.join(__dirname, '../apps/dashboard/visitor-count.js'), 'utf8');
  vm.runInNewContext(visitor, {window, document: {querySelector: () => ({remove: () => { removed = true; }})}});
  assert.equal(removed, true);
});

test('desktop pauses before injecting AdSense; public pages expose privacy choices', () => {
  const h = harness();
  assert.equal(h.window.adsbygoogle.pauseAdRequests, 1);
  assert.equal(h.scripts.length, 2);
  assert.match(h.scripts[0].src, /fundingchoicesmessages\.google\.com/);
  assert.match(h.scripts[1].src, /pagead2\.googlesyndication\.com/);
  for (const name of ['index.html', 'research.html']) {
    const html = fs.readFileSync(path.join(__dirname, '../apps/dashboard', name), 'utf8');
    assert.doesNotMatch(html, /pagead2\.googlesyndication\.com/);
    assert.match(html, /src="ads\.js" defer/);
    const publisher = html.match(/name="google-adsense-account" content="ca-(pub-\d+)"/)?.[1];
    assert.ok(publisher);
    assert.ok(h.scripts[1].src.endsWith(`client=ca-${publisher}`));
    assert.match(html, /data-ad-privacy/);
    assert.match(html, /href="privacy.html"/);
  }
  for (const name of ['privacy.html', 'radar.html']) {
    assert.doesNotMatch(fs.readFileSync(path.join(__dirname, '../apps/dashboard', name), 'utf8'), /adsbygoogle/);
  }
});
