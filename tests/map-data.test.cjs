const {test} = require('node:test');
const assert = require('node:assert/strict');
const {aggregate} = require('../apps/dashboard/map-data.js');
const {ranking,mapCategories} = require('../apps/dashboard/map-data.js');
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
test('map only exposes requested alignment and sentiment symbols',()=>{
 assert.deepEqual(mapCategories,{alignment:['supports','opposes'],sentiment:['positive','negative','neutral']});
});
const countries=[{iso2:'FR',country_name:'France'},{iso2:'DE',country_name:'Germany'},{iso2:'GB',country_name:'United Kingdom'}];
test('ranking uses a unique-comment denominator, retains zero countries and overlapping mentions',()=>{
 const a=video(), b=video({id:'b',countries:['FR'],responses:{total:6}});
 const out=ranking([a,b,video({batch:'2026-W39'})],countries);
 assert.equal(out.total,10); assert.deepEqual(out.rows.map(c=>[c.iso2,c.count,c.percentage]),[['FR',10,100],['DE',4,40],['GB',0,0]]);
});
test('combined filters use actual cross-tab counts, never marginal products or sums',()=>{
 const a=video({responses:{total:4,alignment:{supports:3,opposes:1},sentiment:{positive:2,negative:2},alignment_sentiment:{supports:{positive:1,negative:2},opposes:{positive:1}}}});
 assert.equal(ranking([a],countries,'supports','positive').total,1);
 assert.equal(ranking([a],countries,'all','positive').total,2);
 assert.equal(ranking([a],countries,'supports','all').total,3);
 assert.equal(ranking([video()],countries,'supports','positive').available,false);
 assert.equal(ranking([a],countries,'opposes','negative').rows[0].percentage,null);
});
