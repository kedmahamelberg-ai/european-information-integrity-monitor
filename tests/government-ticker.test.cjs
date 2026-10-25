const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/app.js'), 'utf8');
const speed = source.match(/^function updateGovernmentTickerSpeed\(\)\{[\s\S]*?^\}/m)?.[0];
const route = source.match(/^function route\(\)\{[^\n]*\}/m)?.[0];

test('returning from Government Narratives measures the visible ticker before setting speed', () => {
  assert.ok(speed && route);
  const sections = Object.fromEntries(['monitor', 'government', 'evidence', 'methodology'].map(id => [id, {hidden: id !== 'monitor'}]));
  const track = {
    style: {animationDuration: '120s'},
    get scrollWidth() { return sections.monitor.hidden ? 0 : 16800; },
  };
  const location = {hash: '#government'};
  const nav = [{hash: '#monitor', setAttribute() {}}, {hash: '#government', setAttribute() {}}];
  const context = {
    location,
    document: {querySelectorAll: () => nav},
    $: selector => selector === '#government-ticker .ticker-track' ? track : sections[selector.slice(1)],
  };
  vm.runInNewContext(`${speed}\n${route}\nthis.updateSpeed=updateGovernmentTickerSpeed;this.navigate=route;`, context);

  context.navigate();
  context.updateSpeed(); // Government data refresh while Situation Room is hidden.
  assert.equal(track.style.animationDuration, '120s');
  location.hash = '#monitor';
  context.navigate();
  assert.equal(sections.monitor.hidden, false);
  assert.equal(track.style.animationDuration, '300s'); // 8400px at 28px/s.
});
