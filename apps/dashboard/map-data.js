/* Shared map aggregation. Repeated weekly snapshots are not new viewers/comments. */
(function (root) {
  'use strict';
  function unique(videos) {
    const selected = new Map();
    for (const video of videos.filter(v => v.label)) {
      const old = selected.get(video.id);
      const stamp = v => `${v.batch || ''}|${v.engagement?.captured_at || ''}`;
      if (!old || stamp(video) > stamp(old)) selected.set(video.id, video);
    }
    return [...selected.values()];
  }
  function responses(videos) {
    const out = {total:0, human_reviewed:0, alignment:{}, sentiment:{}, response_focus:{}};
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
  const api = {unique, responses, aggregate};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MonitorMap = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
