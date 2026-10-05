const test = require('node:test');
const assert = require('node:assert/strict');
const { nextCamera } = require('../apps/dashboard/live.js');
const cams = [
  {id:'a',country_code:'GB',status:'live'},
  {id:'b',country_code:'FR',status:'live'},
  {id:'c',country_code:'NL',status:'not_live'},
  {id:'d',country_code:'GB',status:'live'},
  {id:'e',country_code:'IT',status:'live'}
];
test('rotation skips countries already playing and non-live streams',()=>{
  assert.equal(nextCamera(cams,0,new Set(['FR','GB']),new Map(),100),4);
});
test('failed cameras stay excluded until cooldown expires',()=>{
  assert.equal(nextCamera(cams,0,new Set(),new Map([['b',200]]),100),3);
  assert.equal(nextCamera(cams,0,new Set(),new Map([['b',200]]),201),1);
});
test('all-unavailable catalogue stops instead of replaying an offline camera',()=>{
  assert.equal(nextCamera(cams,-1,new Set(['GB','FR','IT']),new Map(),100),-1);
  assert.equal(nextCamera([],0,new Set(),new Map(),100),-1);
});
test('rotation wraps to the beginning',()=>{
  assert.equal(nextCamera(cams,4,new Set(),new Map(),100),0);
});
