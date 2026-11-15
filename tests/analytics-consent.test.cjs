const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const analytics = fs.readFileSync('apps/dashboard/analytics.js', 'utf8');
const visitor = fs.readFileSync('apps/dashboard/visitor-count.js', 'utf8');
function page({mobile = false, userAgent = '', blocked = false, hostname = 'monitor.hamelberg-ai.com'} = {}) {
  const nodes = [], requests = [], store = new Map();
  const head = {appendChild(node) { nodes.push(node); }};
  const ids = {'visitor-message': {hidden: true}, 'visitor-number': {}};
  const ctx = {Date, JSON, Intl, AbortController,
    location: {protocol: 'https:', hostname, origin: 'https://' + hostname, pathname: '/'},
    localStorage: {getItem(k) { if (blocked) throw Error('blocked'); return store.get(k) || null; },
      setItem(k, v) { if (blocked) throw Error('blocked'); store.set(k, v); },
      removeItem(k) { if (blocked) throw Error('blocked'); store.delete(k); }},
    document: {title: 'Monitor', cookie: '', head, body: {appendChild(node) { nodes.push(node); }},
      createElement: tag => ({tag}), getElementById: k => ids[k]},
    navigator: {userAgent, userAgentData: {mobile}}, matchMedia: () => ({matches: mobile}),
    crypto: {randomUUID: () => 'be123456-1234-1234-1234-123456789012'},
    fetch: (url, options) => { requests.push({url, options}); return Promise.resolve({ok: true, json: () => Promise.resolve({number: 42})}); },
    addEventListener() {}
  };
  ctx.window = ctx; ctx.globalThis = ctx;
  vm.runInNewContext(analytics, ctx);
  vm.runInNewContext(visitor, ctx);
  return {ctx, nodes, ids, store, requests,
    ga: () => nodes.filter(n => n.src && new URL(n.src).origin === 'https://www.googletagmanager.com')};
}
for (const [name, options] of [['phone', {mobile: true, userAgent: 'iPhone'}], ['tablet', {userAgent: 'iPad'}], ['narrow desktop', {mobile: true}], ['desktop', {}]]) {
  test(name + ': no prompt, cookieless Analytics and visit counter start automatically', async () => {
    const p = page(options);
    assert.equal(p.ga().length, 1);
    assert.equal(p.requests.length, 1);
    assert.equal(p.nodes.some(node => node.id === 'monitor-cookie-choice'), false);
    assert.equal(p.ctx['ga-disable-G-1JQ1MNNVKR'], false);
    const defaultConsent = p.ctx.dataLayer.find(x => x[0] === 'consent' && x[1] === 'default');
    assert.equal(defaultConsent[2].analytics_storage, 'denied');
    assert.equal(defaultConsent[2].ad_storage, 'denied');
    assert.equal(p.ctx.dataLayer.some(x => x[0] === 'consent' && x[2]?.analytics_storage === 'granted'), false);
    await new Promise(setImmediate);
    assert.equal(p.ids['visitor-message'].hidden, false);
    p.ctx.MonitorAnalytics.event('source_open', {kind: 'official'});
    assert.equal(p.ctx.dataLayer.some(x => x[0] === 'event' && x[1] === 'source_open'), true);
  });
}
test('blocked storage still measures; local preview sends nothing', () => {
  const p = page({blocked: true});
  assert.equal(p.ga().length, 1); assert.equal(p.requests.length, 1);
  const preview = page({hostname: 'localhost'});
  assert.equal(preview.ga().length, 0); assert.equal(preview.requests.length, 0);
});
