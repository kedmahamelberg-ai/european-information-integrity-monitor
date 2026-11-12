const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname, '../apps/dashboard/app.js'), 'utf8');
const start = app.indexOf('function trendCountrySeries(');
const end = app.indexOf('function renderGovernmentTrends()', start);
assert.ok(start >= 0 && end > start);
const scope = {governmentTopicCodes: item => item.topics};
vm.runInNewContext(app.slice(start, end) + '\nthis.series=trendCountrySeries;this.selected=trendSelectedCountries;', scope);

test('Europe totals exclude the USA benchmark while USA keeps its own denominator', () => {
  const items = [
    {country_code: 'NL', chartDate: '2026-10-05', topics: ['cyber']},
    {country_code: 'US', chartDate: '2026-10-05', topics: ['cyber', 'civil_protection']},
  ];
  const days = ['2026-10-05'];
  const topics = ['cyber', 'civil_protection'];
  const europe = scope.series('all', topics, items, days);
  const usa = scope.series('US', topics, items, days);
  assert.equal(europe.items, 1);
  assert.equal(europe.total, 1);
  assert.equal(europe.series.get('cyber')[0], 100);
  assert.equal(usa.items, 1);
  assert.equal(usa.total, 2);
  assert.equal(usa.series.get('cyber')[0], 50);
});

test('the USA benchmark remains selected for every European selection', () => {
  assert.deepEqual(Array.from(scope.selected(['all', 'none', 'none'])), ['all', 'US']);
  assert.deepEqual(Array.from(scope.selected(['NL', 'DE', 'US'])), ['NL', 'DE', 'US']);
  assert.deepEqual(Array.from(scope.selected(['US', 'none', 'none'])), ['all', 'US']);
});
