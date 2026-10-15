const test = require('node:test');
const assert = require('node:assert/strict');
const { availableCamera, nextCamera } = require('../apps/dashboard/live.js');
const checked_at = '2026-10-16T10:00:00Z';
const now = Date.parse('2026-10-16T10:01:00Z');
const cams = [
  {id:'a',country_code:'GB',status:'live',video_id:'zMCea32gpmg',checked_at},
  {id:'b',country_code:'FR',status:'live',video_id:'-xzg3wujOVM',checked_at},
  {id:'c',country_code:'NL',status:'not_live',video_id:'Gd9d4q6WvUY',checked_at},
  {id:'d',country_code:'GB',status:'live',video_id:'zMCea32gpmg',checked_at},
  {id:'e',country_code:'IT',status:'live',video_id:'mt7uE-n0YPI',checked_at}
];
test('rotation skips countries already playing and non-live streams',()=>{
  assert.equal(nextCamera(cams,0,new Set(['FR','GB']),new Map(),now),4);
});
test('failed cameras stay excluded until cooldown expires',()=>{
  assert.equal(nextCamera(cams,0,new Set(),new Map([['b',now+200]]),now),3);
  assert.equal(nextCamera(cams,0,new Set(),new Map([['b',now+200]]),now+201),1);
});
test('all-unavailable catalogue stops instead of replaying an offline camera',()=>{
  assert.equal(nextCamera(cams,-1,new Set(['GB','FR','IT']),new Map(),now),-1);
  assert.equal(nextCamera([],0,new Set(),new Map(),now),-1);
});
test('rotation wraps to the beginning',()=>{
  assert.equal(nextCamera(cams,4,new Set(),new Map(),now),0);
});
test('offline cameras return after a later verified-live catalogue update',()=>{
  assert.equal(availableCamera(cams[2],now),false);
  const recovered = cams.map(c=>c.id==='c'?{...c,status:'live',checked_at:new Date(now).toISOString()}:c);
  assert.equal(nextCamera(recovered,1,new Set(),new Map(),now),2);
});
test('stale or unverified cameras cannot enter the rotation',()=>{
  assert.equal(availableCamera({...cams[0],checked_at:'2026-10-13T00:00:00Z'},now),false);
  assert.equal(availableCamera({...cams[0],status:'unverified'},now),false);
});
