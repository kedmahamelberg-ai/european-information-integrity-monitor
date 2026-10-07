"use strict";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const human = (s) =>
    String(s ?? "")
      .replaceAll("_", " ")
      .replace(/^./, (c) => c.toUpperCase()),
  num = (v) =>
    v == null
      ? "Unavailable"
      : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
let feedQueue=[], feedIndex=0, feedPaused=matchMedia("(prefers-reduced-motion: reduce)").matches;
let data = {videos:[], inventory:[], batches:[], collection:{}}, countries=[], inventory=[], zoom=1;
const roles=["readiness","projecting_power","under_pressure"], colors={coverage:"#b9ee74", related:"#b9ee74", readiness:"#61d7bc", projecting_power:"#efb85b", under_pressure:"#f17a69"}, icons={readiness:"🛡", projecting_power:"⚔", under_pressure:"🎯"};
function project(lon, lat) {
  const my = (v) => Math.log(Math.tan(Math.PI / 4 + (v * Math.PI) / 360));
  return [
    ((lon + 25) / 95) * 960,
    ((my(72) - my(Math.max(-85, Math.min(85, lat)))) / (my(72) - my(32))) * 650,
  ];
}
function geometry(g) {
  const ps =
    g.type === "Polygon"
      ? [g.coordinates]
      : g.type === "MultiPolygon"
        ? g.coordinates
        : [];
  return ps
    .flatMap((p) =>
      p.map(
        (r) =>
          r
            .map((v, i) => {
              const [x, y] = project(...v);
              return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join("") + "Z",
      ),
    )
    .join("");
}

function rows(geo=true, all=false) {
  return (all ? inventory : data.videos).filter(v =>
    ($("#batch").value === "all" || v.batch === $("#batch").value) &&
    (!geo || $("#country").value === "all" || v.countries.includes($("#country").value)) &&
    ($("#topic").value === "all" || v.label?.topics?.includes($("#topic").value)));
}
function sum(v,k){const ns=v.map(x=>x.engagement?.[k]).filter(x=>x!=null);return {value:ns.length?ns.reduce((a,b)=>a+b,0):null,n:ns.length};}
function bar(name,n,d){return `<div class="bar-row"><span>${esc(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${d?n/d*100:0}%"></div></div><span>${n}/${d}</span></div>`;}
function state(v){return v.classification_status==="human_reviewed"?"Human validated":v.label?"AI · provisional":v.caption_state==="saved"?"Awaiting AI coding":v.caption_state==="blocked"?"Captions · access blocked":v.caption_state==="unavailable"?"English captions unavailable":"Captions · unverified";}
function thumbnail(v){return `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`;}
function render(){
 const v=rows(), all=rows(true,true), coded=v.filter(x=>x.label), related=coded.filter(x=>x.label.relevance==="related"), reviewed=coded.filter(x=>x.classification_status==="human_reviewed"), c=data.collection;
 $("#edition").textContent=data.batches.map(b=>b.id).join(" / ") || "NO BATCH";
 $("#snapshot").textContent=`SNAPSHOT ${new Date(data.as_of).toLocaleString()}`;
 // Repeated weekly observations of one video must not inflate cumulative views.
 const uniqueRelated=[...related.reduce((m,x)=>{const old=m.get(x.id);if(!old||(x.engagement?.captured_at||'')>(old.engagement?.captured_at||''))m.set(x.id,x);return m;},new Map()).values()];
 const relevantViews=sum(uniqueRelated,"views"), relevantLikes=sum(uniqueRelated,"likes");
 $("#stats").innerHTML=`<div class="stat"><span>Security-related videos</span><b>${num(uniqueRelated.length)}</b><small>Classified content in this selection</small></div><div class="stat stat-hero"><span>Views on security-related videos</span><b>${num(relevantViews.value)}</b><small>Lifetime views · ${relevantViews.n}/${uniqueRelated.length} counters available · not unique viewers</small></div><div class="stat"><span>Likes on related videos</span><b>${num(relevantLikes.value)}</b><small>${relevantLikes.n}/${uniqueRelated.length} counters available</small></div>`;
 const missingText=c.awaiting_transcript||0, pendingCoding=Math.max(0,(c.transcript_eligible||0)-(c.classified_videos||0));
 $(".coverage-details summary").textContent=`Data coverage · ${c.classified_videos||0} of ${c.sampled_videos||0} sources classified · ${missingText} need English text · ${pendingCoding} have text and await valid classification`;
 const country=countries.find(x=>x.iso2===$("#country").value)?.country_name || "Europe";
 $("#focus-title").textContent=country;$("#map-focus").textContent=country.toUpperCase();
 const topics=Object.entries(data.topic_labels||{}).map(([k,n])=>[k,n,related.filter(x=>x.label.topics.includes(k)).length]).filter(x=>x[2]).sort((a,b)=>b[2]-a[2]);
 $("#topics").innerHTML=topics.slice(0,7).map(([k,n,count])=>`<button class="topic-button" data-topic="${esc(k)}"><span>${esc(n)}</span><b>${count}</b></button>`).join("") || '<p class="small">No coded topics for these filters.</p>';
 const lead=topics[0];
 $('#situation-brief').innerHTML=`<strong>WEEK AT A GLANCE</strong><span>${lead?`Most observed topic: <b>${esc(lead[1])}</b> · ${lead[2]} classified sources`:'No classified topic for this selection'}</span><span><b>${MonitorMap.responses(v).total}</b> comments analysed for message alignment and sentiment</span>`;
 const health=data.caption_health||{}, saved=health.saved||c.transcript_eligible||0;
 const recovery=data.caption_recovery||[], audio=recovery.some(x=>x.audio_configured);
 const stopped=recovery.some(x=>x.audio_stopped==='audio_access_unavailable');
 const recoveryNote=stopped?'Public audio retrieval is also blocked. These sources remain unclassified until evidence can be retrieved.':audio?'Automatic audio transcription is enabled. Missing audio can be recovered in bounded Sunday runs on the configured Mac.':'Audio recovery has not run in this snapshot.';
 $("#quality").innerHTML=`<div class="pipeline-line"><span>Sample frozen</span><b>${c.sampled_videos||0}</b></div><div class="pipeline-line"><span>English text saved</span><b>${saved}</b></div><div class="pipeline-meter"><span style="width:${c.sampled_videos?saved/c.sampled_videos*100:0}%"></span></div><div class="pipeline-line warn"><span>Retrieval blocked</span><b>${health.blocked||0}</b></div><div class="pipeline-line warn"><span>No English access found</span><b>${health.unavailable||0}</b></div><div class="pipeline-line"><span>Access unverified</span><b>${health.unverified||0}</b></div><p class="small">GLOBAL PIPELINE · ${c.all_retained_comments||0} comments retained.<br>Weekly collection: Sunday 05:17 UTC.<br>Saved-text classification follows recovered evidence.<br>YouTube may block caption requests even when a video has subtitles.<br>${esc(recoveryNote)}<br>AI coding is automatic once English text is saved. Human review is a separate quality sample.</p>`;
 $("#roles").innerHTML=roles.map(r=>`<div class="role" style="color:${colors[r]}"><span class="icon" aria-hidden="true">${icons[r]}</span><div>${esc(data.role_labels?.[r]||human(r))}<small>Sources portraying this role</small></div><b>${related.filter(x=>x.label.roles.some(z=>z.role===r&&($("#country").value==="all"||z.entity_code===$("#country").value))).length}</b></div>`).join("");
 const ex={comparative:"Comparative",endorsement:"Expert / testimonial",entertainment:"Entertainment / storytelling",mnemonic_devices:"Mnemonic devices"};
 $("#execution").innerHTML=Object.entries(ex).map(([k,n])=>{const assessed=related.filter(x=>["present","absent_after_watching"].includes(x.label.execution[k]));return bar(n,assessed.filter(x=>x.label.execution[k]==="present").length,assessed.length)}).join("")+`<p class="small">Present / assessed. Unknowns excluded; absence requires watching. ${related.length} security-related sources. Categories can overlap.</p>`;
 renderResponses(v);
 $("#engagement").innerHTML=`<div class="metric-grid">${[["Views","views"],["Likes","likes"],["Total comments","total_comments"]].map(([name,k])=>{const s=sum(all,k);return `<div><b>${num(s.value)}</b><small>${name} · ${s.n}/${all.length} counters</small></div>`}).join("")}</div><p class="small">Latest saved counters · shares unavailable · views are not unique people.</p>`;
 $("#data-status").textContent=`${c.classified_videos||0} of ${c.sampled_videos||0} sources classified, including ${c.reviewed_videos||0} human reviewed. ${c.transcript_eligible||0} have usable English text. ${missingText} still need text; ${pendingCoding} have text but await a valid classification. AI results publish provisionally only after evidence and classification checks pass. Human corrections take precedence. This sample does not establish country-level public opinion or a trend.`;
 renderMap();renderFeed();renderEvidence();
}
const responseStyles={
 supports:{color:'#ffee38',shape:'▲'},opposes:{color:'#ff8c32',shape:'▼'},
 positive:{color:'#3ce7ef',shape:'◆'},negative:{color:'#ff69ad',shape:'✕'},
 mixed:{color:'#c58aff',shape:'■'},neutral:{color:'#f5f5ea',shape:'◇'},
 no_position:{color:'#c4cad4',shape:'□'},unrelated:{color:'#98a8bb',shape:'+'},unclear:{color:'#a6b6b1',shape:'?'}
};
function responseLegend(r){
 return [['alignment','Alignment with main message'],['sentiment','Comment sentiment']].map(([k,title])=>`<div class="response-title">${title}</div><div class="response-legend">${Object.entries(r[k]).map(([key,n])=>{const style=responseStyles[key]||responseStyles.unclear;return `<span><span class="response-symbol" style="color:${style.color}">${style.shape}</span> ${esc(human(key))} <b>${num(n)}</b></span>`}).join('')||'No classified comments'}</div>`).join('');
}
function renderResponses(v){
 const r=MonitorMap.responses(v);
 $('#response-count').textContent=`${num(r.total)} COMMENTS`;
 $('#responses').innerHTML=responseLegend(r)+`<p class="small">${r.human_reviewed} human-reviewed · ${r.total-r.human_reviewed} AI-only. Latest saved comments per unique video. Praise of presentation is separate from agreement with the main message. Counts describe retained comments, not population opinion.</p>`;
}
function renderMap(){
 const all=rows(false), layer=$('#metric').value, field=$('#response-metric').value;
 const points=countries.map(c=>({...c,...MonitorMap.aggregate(all,c.iso2)})).filter(c=>c.count);
 const max=Math.max(1,...points.map(c=>c.views.value||0));
 $('#markers').innerHTML=points.map(c=>{
   const [x,y]=project(c.longitude,c.latitude), radius=c.views.value?Math.max(3,32*Math.sqrt(c.views.value/max)):3;
   const selected=$('#country').value===c.iso2?'selected':'';
   const attrs=`data-country="${c.iso2}" tabindex="0" role="button"`;
   const video=layer==='comments'?'':`<g class="marker video-marker ${selected}" ${attrs} data-measure="views" aria-label="${esc(c.country_name)}: ${num(c.views.value)} views, ${c.count} classified videos"><title>${esc(c.country_name)} · ${num(c.views.value)} views · ${c.count} classified videos</title><circle class="orbit" r="${radius+5}"/><circle r="${radius}"/><circle class="core" r="2"/></g>`;
   const values=Object.entries(c.responses[field]).filter(([,n])=>n>0);
   const symbols=layer==='videos'?'':values.map(([key,n],i)=>{
     const style=responseStyles[key]||responseStyles.unclear, dx=layer==='comments'?((i%3)-1)*17:radius+12+(i%3)*17,dy=layer==='comments'?Math.floor(i/3)*18-7:Math.floor(i/3)*18-9;
     return `<g class="response-marker ${selected}" ${attrs} data-measure="${field}|${key}" transform="translate(${dx},${dy})" aria-label="${esc(c.country_name)}: ${n} ${esc(human(key))} comments"><title>${esc(c.country_name)} · ${esc(human(key))} · ${n} comments</title><rect x="-8" y="-10" width="16" height="18" fill="#070c0e" fill-opacity=".85"/><text text-anchor="middle" y="5" style="fill:${style.color}">${style.shape}</text></g>`;
   }).join('');
   if(!video&&!symbols)return '';
   return `<g transform="translate(${x},${y})">${video}${symbols}<text class="country-code" x="-7" y="${radius+16}">${c.iso2}</text></g>`;
 }).join('');
 const r=MonitorMap.responses(rows());
 $('#map-key').innerHTML=(layer==='comments'?'':'<span class="video-key">● Classified videos · size follows views</span>')+(layer==='videos'?'':Object.entries(r[field]).filter(([,n])=>n>0).map(([key,n])=>{const style=responseStyles[key]||responseStyles.unclear;return `<span><b style="color:${style.color}">${style.shape}</b> ${esc(human(key))} ${num(n)}</span>`}).join(''));
 $('#response-metric').disabled=layer==='videos';
}
function showCountry(code,measure){
 const country=countries.find(c=>c.iso2===code);if(!country)return;
 const result=MonitorMap.aggregate(rows(false),code), r=result.responses;
 const period=$('#batch').selectedOptions[0].textContent, topic=$('#topic').selectedOptions[0].textContent;
 const focus=measure==='views'?`${num(result.views.value)} lifetime views`: (()=>{const [field,key]=(measure||'').split('|');return `${num(r[field]?.[key]||0)} comments · ${human(key)}`;})();
 $('#country-detail').innerHTML=`<span class="eyebrow">${esc(code)} / ${esc(period)} / ${esc(topic)}</span><h2 id="country-title">${esc(country.country_name)}</h2><p class="country-highlight">${esc(focus)}</p><div class="country-metrics"><div><b>${num(result.count)}</b><small>Unique classified videos</small></div><div><b>${num(result.related)}</b><small>Security-related videos</small></div><div><b>${num(result.views.value)}</b><small>Lifetime views · ${result.views.n}/${result.count} counters</small></div><div><b>${num(result.likes.value)}</b><small>Likes · ${result.likes.n}/${result.count} counters</small></div><div><b>${num(r.total)}</b><small>Classified comments</small></div><div><b>${num(r.human_reviewed)}</b><small>Human-reviewed comments</small></div></div>${responseLegend(r)}<p class="small">Country mentions in the selected content, not audience location. A video may mention several countries, so country totals overlap. All retained weeks use one latest snapshot per video. Lifetime views are not unique people or views gained during this window. Data are retained for 30 days.</p>`;
 $('#country-dialog').showModal();
}
function renderFeed(){const mode=$("#feed-mode").value;
 const sorted=rows(true,true).filter(x=>mode==='all'||(mode==='coded'?x.label:!x.label)).sort((a,b)=>Number(!!b.label)-Number(!!a.label)||(b.engagement?.views||0)-(a.engagement?.views||0));
 // Round-robin countries so the cycle does not stay on one country's sources.
 const buckets=new Map();for(const v of sorted){const key=v.countries[0]||'other';if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(v);}
 feedQueue=[];while([...buckets.values()].some(x=>x.length))for(const bucket of buckets.values())if(bucket.length)feedQueue.push(bucket.shift());
 feedIndex=0;drawFeed();
}
function drawFeed(){
 $('#feed-count').textContent=feedQueue.length+' SOURCES';
 $('#cycle-position').textContent=feedQueue.length?`${feedIndex+1} / ${feedQueue.length}`:'0';
 $('#feed-pause').textContent=feedPaused?'Resume cycle':'Pause cycle';$('#feed-pause').setAttribute('aria-pressed',String(feedPaused));
 const v=Array.from({length:Math.min(3,feedQueue.length)},(_,i)=>feedQueue[(feedIndex+i)%feedQueue.length]);
 $('#source-feed').innerHTML=v.map(x=>`<button class="feed-item" data-source="${esc(x.batch+'|'+x.id)}"><img src="${thumbnail(x)}" loading="lazy" alt=""><span><span class="source-state ${x.label?'':'pending'}">${esc(state(x))}</span><b>${esc(x.title)}</b><small>${esc(x.countries.join(' / '))} · ${esc(x.batch)} · ${num(x.engagement?.views)} views</small></span></button>`).join('')||'<p class="empty">No sources match these filters.</p>';
}
setInterval(()=>{const feed=$('.feed-panel');if(!feedPaused&&!document.hidden&&!$('#monitor').hidden&&!$('#source-dialog').open&&!feed.matches(':hover')&&!feed.contains(document.activeElement)&&feedQueue.length>3){feedIndex=(feedIndex+1)%feedQueue.length;drawFeed();}},8000);
function renderEvidence(){const q=$("#search").value.toLowerCase(),v=rows(true,true).filter(x=>`${x.title} ${x.channel}`.toLowerCase().includes(q));
 $("#evidence-table").innerHTML=`<p class="small">${v.length} sources · situation-room filters apply. No English text means no content classification.</p><div class="evidence-grid">${v.map(x=>`<article class="case"><img src="${thumbnail(x)}" loading="lazy" alt="Video cover"><span class="source-state ${x.label?'':'pending'}">${esc(state(x))}</span><h2>${esc(x.title)}</h2><p>${esc(x.channel)} · ${esc(x.countries.join(' / '))} · ${esc(x.batch)}</p><p>Original language: ${esc(x.original_language||'und')} · ${num(x.engagement?.views)} views</p>${x.label?`<p>${esc(human(x.label.relevance))} · ${esc(x.label.topics.map(t=>data.topic_labels?.[t]||human(t)).join(' / '))}</p>`:''}<button data-source="${esc(x.batch+'|'+x.id)}">Inspect source ↗</button></article>`).join('')}</div>`;
}
function showSource(key){const v=inventory.find(x=>x.batch+'|'+x.id===key);if(!v)return;
 $("#source-detail").innerHTML=`<span class="source-state">${esc(state(v))}</span><h2>${esc(v.title)}</h2><iframe title="${esc(v.title)}" src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(v.id)}" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe><p class="small">${esc(v.channel)} · ${esc(v.countries.join(' / '))} · original language: ${esc(v.original_language||'und')}</p>${v.transcript_method==='faster-whisper'?'<p class="small">Evidence was automatically transcribed from public audio using Whisper. Translation and speech recognition can contain errors.</p>':''}${v.label?`<p>${esc(human(v.label.relevance))} · ${esc(v.label.topics.map(t=>data.topic_labels?.[t]||human(t)).join(' / '))}</p>${v.label.roles.map(r=>`<span class="tag">${icons[r.role]||''} ${esc(r.entity)} · ${esc(data.role_labels?.[r.role]||human(r.role))}</span>`).join('')}`:'<p class="small">Content labels require a successfully saved English transcript. This source is visible as part of the sampled inventory.</p>'}<p><a href="https://www.youtube.com/watch?v=${encodeURIComponent(v.id)}" target="_blank" rel="noopener">Open original video ↗</a></p>`;
 $("#source-dialog").showModal();
}
function route(){const r=['evidence','methodology'].includes(location.hash.slice(1))?location.hash.slice(1):'monitor';for(const id of ['monitor','evidence','methodology'])$('#'+id).hidden=id!==r;document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.hash==='#'+r?'page':'false'));}
async function init(){try{
 const rev=document.documentElement.dataset.build||Date.now();const result=await Promise.all(['data.json','countries.json','assets/world.json','methodology.html'].map(async p=>{const r=await fetch(`${p}?v=${rev}`);if(!r.ok)throw Error('Snapshot unavailable');return p.endsWith('.html')?r.text():r.json()}));
 [data,countries]=result;countries=countries.countries||countries;
 const coded=new Map(data.videos.map(v=>[v.batch+'|'+v.id,v]));inventory=(data.inventory||data.videos).map(v=>({...v,...coded.get(v.batch+'|'+v.id)}));
 $('#methodology').innerHTML=result[3];$('#geography').innerHTML=result[2].features.map(f=>`<path d="${geometry(f.geometry)}"/>`).join('');
 $('#country').insertAdjacentHTML('beforeend',countries.map(c=>`<option value="${esc(c.iso2)}">${esc(c.country_name)}</option>`).join(''));
 $('#batch').insertAdjacentHTML('beforeend',data.batches.map(b=>`<option value="${esc(b.id)}">${esc(b.id)}</option>`).join(''));
 $('#topic').insertAdjacentHTML('beforeend',Object.entries(data.topic_labels||{}).map(([c,n])=>`<option value="${esc(c)}">${esc(n)}</option>`).join(''));
 render();route();
 }catch(e){$('#data-status').textContent='Snapshot unavailable. Please refresh or check the publishing workflow.';console.error(e);}}
for(const id of ['batch','country','topic','metric','response-metric'])$('#'+id).onchange=render;
$('#feed-pause').onclick=()=>{feedPaused=!feedPaused;drawFeed();};
$('#feed-mode').onchange=renderFeed;$('#search').oninput=renderEvidence;
$('#reset').onclick=()=>{for(const id of ['batch','country','topic'])$('#'+id).value='all';$('#metric').value='both';$('#response-metric').value='alignment';zoom=1;setZoom();render();};
$('#topics').onclick=e=>{const b=e.target.closest('[data-topic]');if(b){$('#topic').value=b.dataset.topic;render();}};
$('#markers').onclick=e=>{const el=e.target.closest('[data-country]');if(el){showCountry(el.dataset.country,el.dataset.measure);}};
$('#markers').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}};
for(const id of ['source-feed','evidence-table'])$('#'+id).onclick=e=>{const b=e.target.closest('[data-source]');if(b)showSource(b.dataset.source);};
$('#close-country').onclick=()=>$('#country-dialog').close();
$('#close-source').onclick=()=>$('#source-dialog').close();$('#source-dialog').addEventListener('close',()=>$('#source-detail').innerHTML='');
function setZoom(){const w=960/zoom,h=650/zoom;$('#map').setAttribute('viewBox',`${(960-w)/2} ${(650-h)/2} ${w} ${h}`);}
$('#zoom-in').onclick=()=>{zoom=Math.min(3,zoom+.25);setZoom();};$('#zoom-out').onclick=()=>{zoom=Math.max(1,zoom-.25);setZoom();};$('#zoom-reset').onclick=()=>{zoom=1;setZoom();};
window.addEventListener('hashchange',route);init();
// Pick up new published batches/results without requiring an unattended screen to reload.
setInterval(async()=>{
  if(document.hidden||$('#source-dialog').open||$('#country-dialog').open||$('#camera-list-dialog').open)return;
  try{
    const response=await fetch(`data.json?refresh=${Date.now()}`,{cache:'no-store'});
    if(!response.ok)return;
    const updated=await response.json();
    if(!Array.isArray(updated.videos)||!Array.isArray(updated.batches)||updated.as_of===data.as_of)return;
    data=updated;
    const coded=new Map(data.videos.map(v=>[v.batch+'|'+v.id,v]));
    inventory=(data.inventory||data.videos).map(v=>({...v,...coded.get(v.batch+'|'+v.id)}));
    const existing=new Set([...$('#batch').options].map(o=>o.value));
    for(const b of data.batches)if(!existing.has(b.id))$('#batch').insertAdjacentHTML('beforeend',`<option value="${esc(b.id)}">${esc(b.id)}</option>`);
    render();
  }catch{/* Retain the last successfully loaded snapshot during network failures. */}
},300000);

// Animate a focus reticle between actual country markers, never invented events.
let scanIndex=0;
setInterval(()=>{if(document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches||$('#monitor').hidden)return;const markers=[...document.querySelectorAll('#markers .marker')];if(!markers.length)return;markers.forEach(m=>m.classList.remove('scan-focus'));markers[scanIndex++%markers.length].classList.add('scan-focus');},2200);
