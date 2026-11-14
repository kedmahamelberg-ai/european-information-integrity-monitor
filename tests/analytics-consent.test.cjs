const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const analytics = fs.readFileSync('apps/dashboard/analytics.js', 'utf8');
const visitor = fs.readFileSync('apps/dashboard/visitor-count.js', 'utf8');
function page({saved, mobile = false, userAgent = '', blocked = false, hostname = 'monitor.hamelberg-ai.com'} = {}) {
  const nodes = [], requests = [], events = {}, store = new Map();
  if (saved) store.set('esm-analytics-consent-v1', JSON.stringify(saved));
  function node(tag) {
    return {tag, children: [], hidden: false, listeners: {},
      appendChild(n) { this.children.push(n); nodes.push(n); },
      setAttribute(k, v) { this[k] = v; },
      addEventListener(k, fn) { this.listeners[k] = fn; },
      querySelector() { return this.children.flatMap(n => [n, ...n.children]).find(n => n.tag === 'button'); },
      focus() { this.focused = true; }};
  }
  const head = node('head'), body = node('body'), footer = node('footer');
  const ids = {'visitor-message': {hidden: true}, 'visitor-number': {}};
  let reloads = 0;
  const ctx = {Date, JSON, Intl, AbortController,
    CustomEvent: function (name, opts) { this.type = name; this.detail = opts.detail; },
    location: {protocol: 'https:', hostname, origin: 'https://' + hostname, pathname: '/', reload() { reloads++; }},
    localStorage: {getItem(k) { if (blocked) throw Error('blocked'); return store.get(k) || null; },
      setItem(k, v) { if (blocked) throw Error('blocked'); store.set(k, v); }, removeItem(k) { store.delete(k); }},
    document: {title: 'Monitor', cookie: '', readyState: 'interactive', head, body,
      createElement: node, querySelector: () => footer, getElementById: k => ids[k]},
    navigator: {userAgent, userAgentData: {mobile}}, matchMedia: () => ({matches: mobile}),
    crypto: {randomUUID: () => 'be123456-1234-1234-1234-123456789012'},
    fetch: (url, options) => { requests.push({url, options}); return Promise.resolve({ok: true, json: () => Promise.resolve({number: 42})}); },
    addEventListener(k, fn) { (events[k] ||= []).push(fn); },
    dispatchEvent(e) { for (const fn of events[e.type] || []) fn(e); }
  };
  ctx.window = ctx; ctx.globalThis = ctx;
  vm.runInNewContext(analytics, ctx);
  vm.runInNewContext(visitor, ctx);
  return {ctx, nodes, ids, store, requests, reloads: () => reloads,
    ga: () => nodes.filter(n => n.src && new URL(n.src).origin === 'https://www.googletagmanager.com'),
    banner: () => nodes.find(n => n.id === 'monitor-cookie-choice')};
}
for (const [name, options] of [['phone', {mobile: true, userAgent: 'iPhone'}], ['tablet', {userAgent: 'iPad'}], ['narrow desktop', {mobile: true}], ['desktop', {}]]) {
  test(name + ': ask before Analytics or counter; accept enables both; withdrawal stops both', async () => {
    const p = page(options);
    assert.equal(p.banner().hidden, false);
    assert.equal(p.ga().length, 0); assert.equal(p.requests.length, 0);
    p.ctx.MonitorAnalytics.choose(false);
    assert.equal(p.ga().length, 0); assert.equal(p.requests.length, 0);
    p.ctx.MonitorAnalytics.choose(true);
    assert.equal(p.ga().length, 1); assert.equal(p.requests.length, 1);
    p.ctx.MonitorAnalytics.choose(true);
    assert.equal(p.ga().length, 1); assert.equal(p.requests.length, 1);
    await new Promise(setImmediate);
    assert.equal(p.ids['visitor-message'].hidden, false);
    p.ctx.MonitorAnalytics.choose(false);
    const before = p.ctx.dataLayer.length;
    p.ctx.MonitorAnalytics.event('source_open');
    assert.equal(p.ctx.dataLayer.length, before);
    assert.equal(p.ctx['ga-disable-G-1JQ1MNNVKR'], true);
    assert.equal(p.ids['visitor-message'].hidden, true);
    assert.equal(p.reloads(), 1);
  });
}
test('saved choices survive navigation; expired and invalid choices ask again', () => {
  for (const analytics of [true, false]) {
    const p = page({mobile: true, saved: {version: 1, analytics, at: Date.now()}});
    assert.equal(p.banner().hidden, true);
    assert.equal(p.ga().length, analytics ? 1 : 0);
    assert.equal(p.requests.length, analytics ? 1 : 0);
  }
  for (const saved of [{version: 1, analytics: true, at: 0}, {version: 1, analytics: true, at: Date.now() + 10000}, {version: 1, analytics: 'true', at: Date.now()}]) {
    const p = page({saved});
    assert.equal(p.banner().hidden, false); assert.equal(p.ga().length, 0);
  }
});
test('blocked storage still permits a current choice; previews never send measurement', () => {
  const p = page({blocked: true});
  assert.equal(p.ga().length, 0); p.ctx.MonitorAnalytics.choose(true);
  assert.equal(p.ga().length, 1); assert.equal(p.requests.length, 1);
  const preview = page({hostname: 'localhost'});
  preview.ctx.MonitorAnalytics.choose(true);
  assert.equal(preview.ga().length, 0); assert.equal(preview.requests.length, 0);
});
