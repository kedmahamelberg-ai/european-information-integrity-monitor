const {test} = require('node:test');
const assert = require('node:assert/strict');
const {aggregate} = require('../apps/dashboard/map-data.js');
const video = (overrides={}) => ({id:'a',batch:'2026-W40',countries:['FR','DE'],label:{relevance:'related'},
  engagement:{views:100,likes:5}, responses:{total:4,human_reviewed:1,alignment:{supports:3,opposes:1},sentiment:{positive:2,neutral:2}},...overrides});
test('map excludes sources without classification, even with engagement counters',()=>{
  const result=aggregate([video(),video({id:'pending',label:null,engagement:{views:999999}})],'FR');
  assert.equal(result.count,1); assert.equal(result.views.value,100); assert.equal(result.responses.total,4);
});
test('all weeks use one latest snapshot per video, not cumulative lifetime counters',()=>{
  const result=aggregate([video(),video({batch:'2026-W41',engagement:{views:120,likes:6}})],'FR');
  assert.equal(result.count,1);assert.equal(result.views.value,120);assert.equal(result.responses.total,4);
  assert.equal(result.responses.alignment.supports,3);
});
test('country and selected-week inputs preserve attribution and unknown counters',()=>{
  assert.equal(aggregate([video()],'GB').count,0);
  assert.equal(aggregate([video()],'DE').responses.sentiment.neutral,2);
  assert.equal(aggregate([video({engagement:{}})]).views.value,null);
  assert.equal(aggregate([video({engagement:{views:0}})]).views.value,0);
});
