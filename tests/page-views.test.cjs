const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('apps/dashboard/page-views.js', 'utf8');

function page({path = '/field-wire/2026-11-26/', search = '', referrer = '', visible = true,
  host = 'monitor.hamelberg-ai.com', userAgent = 'Mozilla/5.0'} = {}) {
  const requests = [];
  const listeners = new Set();
  const document = {
    referrer, visibilityState: visible ? 'visible' : 'hidden',
    addEventListener: (_event, callback) => listeners.add(callback),
    removeEventListener: (_event, callback) => listeners.delete(callback)
  };
  vm.runInNewContext(script, {
    URL, URLSearchParams, document, navigator: {userAgent},
    location: {origin: 'https://' + host, hostname: host, pathname: path, search},
    fetch: (url, init) => { requests.push({url, ...init}); return Promise.resolve({ok: true}); }
  });
  return {requests, show() {
    document.visibilityState = 'visible';
    for (const listener of listeners) listener();
  }};
}

for (const [name, referrer, search] of [
  ['google', 'https://www.google.nl/search?q=private', '?secret=private'],
  ['chatgpt', '', '?utm_source=chatgpt.com&utm_campaign=private'],
  ['claude', 'https://claude.ai/chat/private', ''],
  ['claude', '', '?utm_source=claude.ai'],
  ['internal', 'https://monitor.hamelberg-ai.com/field-wire/?record=private', '?utm_source=google'],
  ['other_referral', 'https://chatgpt.com.example.org/private', ''],
  ['direct_or_unknown', '', '?utm_source=private']
]) {
  test('records only the public path and allowed source ' + name, () => {
    const p = page({referrer, search, visible: false, path: '/field-wire/2026-11-26/index.html'});
    assert.equal(p.requests.length, 0);
    p.show(); p.show();
    assert.equal(p.requests.length, 1);
    const [request] = p.requests;
    assert.match(request.url, /\/monitor_record_page_view$/);
    assert.deepEqual(JSON.parse(request.body), {p_path: '/field-wire/2026-11-26/', p_source: name});
    assert.equal(request.referrerPolicy, 'no-referrer');
    assert.equal(request.credentials, 'omit');
    assert.equal(request.headers.Authorization, undefined);
    assert.ok(!JSON.stringify(request).includes('private'));
  });
}

test('excludes previews, crawlers and paths outside public report routes', () => {
  for (const context of [{host: 'localhost'}, {userAgent: 'Claude-User'},
    {userAgent: 'Googlebot'}, {path: '/field-wire/other-user@private/'}, {path: '/private/'}]) {
    assert.equal(page(context).requests.length, 0);
  }
});
