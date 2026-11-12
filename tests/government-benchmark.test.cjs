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
const labelStart = app.indexOf('const governmentCountryLabel=');
const labelEnd = app.indexOf('function getGovernmentHighlights(', labelStart);
assert.ok(labelStart >= 0 && labelEnd > labelStart);
vm.runInNewContext(app.slice(labelStart, labelEnd) + '\nthis.countryLabel=governmentCountryLabel;', scope);

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

test('the USA benchmark appears only when selected', () => {
  assert.deepEqual(Array.from(scope.selected(['all', 'none', 'none'])), ['all']);
  assert.deepEqual(Array.from(scope.selected(['NL', 'DE', 'US'])), ['NL', 'DE', 'US']);
  assert.deepEqual(Array.from(scope.selected(['US', 'none', 'none'])), ['US']);
});

test('government source and ticker labels identify the USA benchmark', () => {
  assert.equal(scope.countryLabel({country_code: 'US', country: 'United States'}), 'USA · BENCHMARK (White House)');
  assert.equal(scope.countryLabel({country_code: 'NL', country: 'Netherlands'}), 'Netherlands');
});
