const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync('apps/dashboard/app.js', 'utf8');
const start = app.indexOf('function batchOrder(');
const end = app.indexOf('function renderBatchOptions(', start);
assert.ok(start >= 0 && end > start);
const scope = {};
vm.runInNewContext(app.slice(start, end) + '\nthis.weeks=availableWeeks;this.span=weekSpan;', scope);

test('verified summary weeks remain selectable after source details expire', () => {
  const detail = [{id:'2026-W45'}, {id:'2026-W42'}, {id:'2026-W44'}, {id:'2026-W43'}];
  const history = [{id:'2026-W41',security_related_videos:98}, {id:'2026-W42'}, {id:'2026-W45'}];
  assert.deepEqual(Array.from(scope.weeks(detail,history), week=>week.id), ['2026-W41','2026-W42','2026-W43','2026-W44','2026-W45']);
  assert.equal(scope.weeks(detail,history)[0].security_related_videos,98);
  assert.equal(scope.span(history),'2026-W41–2026-W45');
  assert.equal(scope.span(detail),'2026-W42–2026-W45');
});
