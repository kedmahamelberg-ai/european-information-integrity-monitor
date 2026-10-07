/* Shared map aggregation. Repeated weekly snapshots are not new viewers/comments. */
(function (root) {
  'use strict';
  function latest(videos) {
    const selected = new Map();
    for (const video of videos) {
      const old = selected.get(video.id);
      const stamp = v => `${v.batch || ''}|${v.engagement?.captured_at || ''}`;
      if (!old || stamp(video) > stamp(old)) selected.set(video.id, video);
    }
    return [...selected.values()];
  }
  function unique(videos) { return latest(videos).filter(v=>v.label); }
  function markerSize(count, maximum) { return count>0&&maximum>0 ? Math.max(4,18*Math.sqrt(Math.min(count/maximum,1))) : 0; }
  function responses(videos) {
    const out = {total:0, human_reviewed:0, alignment:{supports:0,opposes:0,mixed:0,no_position:0,unrelated:0,unclear:0}, sentiment:{positive:0,negative:0,mixed:0,neutral:0,unclear:0}, response_focus:{}};
    for (const v of unique(videos)) {
      const r = v.responses || {};
      out.total += r.total || 0;
      out.human_reviewed += r.human_reviewed || 0;
      for (const field of ['alignment','sentiment','response_focus'])
        for (const [key,n] of Object.entries(r[field] || {})) out[field][key] = (out[field][key] || 0) + n;
    }
    return out;
  }
  function aggregate(videos, country) {
    const selected = unique(videos.filter(v => !country || v.countries?.includes(country)));
    const counter = key => {
      const known = selected.map(v => v.engagement?.[key]).filter(n => typeof n === 'number' && Number.isFinite(n) && n >= 0);
      return {value: known.length ? known.reduce((a,b)=>a+b,0) : null, n:known.length};
    };
    return {videos:selected, count:selected.length, related:selected.filter(v=>v.label.relevance==='related').length,
      views:counter('views'), likes:counter('likes'), responses:responses(selected)};
  }
  const mapCategories = {alignment:['supports','opposes'], sentiment:['positive','negative','neutral']};
  function matchingComments(video, alignment='all', sentiment='all') {
    const r=video.responses || {};
    if (alignment==='all' && sentiment==='all') return r.total || 0;
    if (alignment==='all') return r.sentiment?.[sentiment] || 0;
    if (sentiment==='all') return r.alignment?.[alignment] || 0;
    // Separate marginal counts cannot establish the intersection.
    if (!r.alignment_sentiment && r.total) return null;
    return r.alignment_sentiment?.[alignment]?.[sentiment] || 0;
  }
  function ranking(videos, countries, alignment='all', sentiment='all') {
    const selected=unique(videos);
    const counts=selected.map(v=>({video:v,count:matchingComments(v,alignment,sentiment)}));
    if(counts.some(x=>x.count===null)) return {available:false, rows:[], total:null};
    const total=counts.reduce((n,x)=>n+x.count,0);
    const rows=countries.map(c=>{
      const count=counts.filter(x=>x.video.countries?.includes(c.iso2)).reduce((n,x)=>n+x.count,0);
      return {...c,count,percentage:total?count/total*100:null};
    }).sort((a,b)=>b.count-a.count||a.country_name.localeCompare(b.country_name));
    return {available:true,total,rows};
  }
  const api = {latest, unique, markerSize, responses, aggregate, mapCategories, matchingComments, ranking};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MonitorMap = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
