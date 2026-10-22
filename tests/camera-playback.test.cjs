const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/live.js'), 'utf8');
const camera = {
  id: 'london', city: 'London', country: 'United Kingdom', country_code: 'GB',
  view: 'Abbey Road crossing', video_id: 'zMCea32gpmg', timezone: 'Europe/London',
  source_url: 'https://www.youtube.com/watch?v=zMCea32gpmg', operator: 'EarthCam',
  status: 'live', checked_at: new Date().toISOString(),
};
const france = {...camera, id: 'paris', city: 'Paris', country: 'France', country_code: 'FR',
  video_id: '-xzg3wujOVM', source_url: 'https://www.youtube.com/watch?v=-xzg3wujOVM'};

function element() {
  const children = new Map();
  const classes = new Set();
  return {
    children, classes, dataset: {}, hidden: false, innerHTML: '', textContent: '',
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      toggle: (name, yes) => yes ? classes.add(name) : classes.delete(name),
    },
    querySelector(selector) {
      if (!children.has(selector)) children.set(selector, element());
      return children.get(selector);
    },
    setAttribute() {}, matches() { return false; }, contains() { return false; },
  };
}

async function boot() {
  const nodes = new Map();
  const scripts = [];
  const timers = [];
  const wall = element();
  wall.appendChild = child => { (wall.tiles ||= []).push(child); };
  nodes.set('camera-wall', wall);
  nodes.set('monitor', {hidden: false});
  nodes.set('source-dialog', {open: false});
  const document = {
    hidden: false,
    head: {appendChild(script) { scripts.push(script); }},
    querySelector: selector => selector === '#camera-wall' ? wall : null,
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, element());
      return nodes.get(id);
    },
    createElement(type) {
      const node = element();
      if (type === 'script') node.remove = () => {};
      return node;
    },
    addEventListener() {},
  };
  const window = {addEventListener() {}};
  const context = {
    document, window, location: {origin: 'https://monitor.hamelberg-ai.com'},
    matchMedia: () => ({matches: false}),
    fetch: async () => ({ok: true, json: async () => ({cameras: [camera, france]})}),
    setTimeout(callback, delay) {
      const timer = {callback, delay, cleared: false};
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) { if (timer) timer.cleared = true; },
    setInterval() {},
    Intl, Date, Promise,
  };
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return {window, wall, scripts, timers};
}

test('cameras wait for verified playback before claiming live', async () => {
  const {window, wall, scripts} = await boot();
  assert.equal(scripts.length, 1, 'the player API loads once for both tiles');
  assert.equal(scripts[0].src, 'https://www.youtube.com/iframe_api');
  assert.ok(wall.tiles.every(tile => tile.innerHTML.includes('camera-player pending')));
  assert.ok(wall.tiles.every(tile => !tile.innerHTML.includes('<iframe')));

  const players = [];
  window.YT = {Player: class {
    constructor(_id, options) { this.options = options; players.push(this); }
    getIframe() { return {setAttribute() {}}; }
    mute() {}
    playVideo() {}
    getPlayerState() { return -1; }
  }};
  window.onYouTubeIframeAPIReady();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(players.length, 2);
  assert.ok(wall.tiles.every(tile => !tile.querySelector('.camera-state').textContent.includes('LIVE')));

  players[0].options.events.onStateChange({data: 1});
  assert.equal(wall.tiles[0].querySelector('.camera-state').textContent, '● LIVE');
  assert.equal(wall.tiles[0].querySelector('.camera-player').classes.has('pending'), false);
  assert.notEqual(wall.tiles[1].querySelector('.camera-state').textContent, '● LIVE');
});

test('a player that never starts is skipped after the playback watchdog', async () => {
  const {window, wall, timers} = await boot();
  window.YT = {Player: class {
    constructor(_id, options) { this.options = options; }
    getPlayerState() { return -1; }
    destroy() {}
  }};
  window.onYouTubeIframeAPIReady();
  await new Promise(resolve => setImmediate(resolve));
  const watchdog = timers.find(timer => timer.delay === 22000 && !timer.cleared);
  assert.ok(watchdog);
  watchdog.callback();
  assert.match(wall.tiles[0].innerHTML, /No available stream in this rotation/);
  assert.ok(!wall.tiles[0].innerHTML.includes('<iframe'));
});

test('blocked player API leaves a useful source link and retry, without a raw embed', async () => {
  const {wall, scripts} = await boot();
  scripts[0].onerror();
  await new Promise(resolve => setImmediate(resolve));
  for (const tile of wall.tiles) {
    assert.equal(tile.querySelector('.camera-state').textContent, 'PLAYER UNAVAILABLE');
    assert.equal(tile.querySelector('.camera-start').hidden, false);
    assert.match(tile.innerHTML, /youtube\.com\/watch\?v=/);
    assert.ok(!tile.innerHTML.includes('<iframe'));
  }
});
