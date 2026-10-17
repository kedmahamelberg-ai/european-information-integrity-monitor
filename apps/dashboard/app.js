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
let data = {videos:[], inventory:[], batches:[], collection:{}}, governmentData={items:[]}, governmentSourceDirectory={sources:[]}, countries=[], inventory=[], zoom=1;
const hiddenTrendTopics=new Set();
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
    MonitorMap.inDateRange(v,$("#date-range").value,$("#date-from").value,$("#date-to").value,data.as_of) &&
    (!geo || $("#country").value === "all" || v.countries.includes($("#country").value)) &&
    ($("#topic").value === "all" || v.label?.topics?.includes($("#topic").value)));
}
function sum(v,k){const ns=v.map(x=>x.engagement?.[k]).filter(x=>x!=null);return {value:ns.length?ns.reduce((a,b)=>a+b,0):null,n:ns.length};}
function dateLabel(){
 const mode=$('#date-range').value;
 if(mode!=='custom')return $('#date-range').selectedOptions[0].textContent;
 const from=$('#date-from').value||'earliest',to=$('#date-to').value||'latest';
 return `${from} to ${to} UTC`;
}
function configureDateInputs(){
 const dates=inventory.map(v=>(v.published_at||'').slice(0,10)).filter(Boolean).sort();
 const min=dates[0]||'',max=(data.as_of||'').slice(0,10)||dates.at(-1)||'';
 for(const id of ['date-from','date-to']){$('#'+id).min=min;$('#'+id).max=max;}
 if(!$('#date-from').value)$('#date-from').value=min;
 if(!$('#date-to').value)$('#date-to').value=max;
}
function bar(name,n,d){return `<div class="bar-row"><span>${esc(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${d?n/d*100:0}%"></div></div><span>${n}/${d}</span></div>`;}
function state(v){return v.classification_status==="human_reviewed"?"Human validated":v.label?"AI · provisional":v.caption_state==="saved"?"Awaiting AI coding":v.caption_state==="blocked"?"Captions · access blocked":v.caption_state==="unavailable"?"English captions unavailable":"Captions · unverified";}
function thumbnail(v){return `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`;}
function render(){
 const v=MonitorMap.unique(rows()), all=MonitorMap.latest(rows(true,true)), coded=v.filter(x=>x.label), related=coded.filter(x=>x.label.relevance==="related"), c=data.collection;
 const selectedInventory=MonitorMap.latest(rows(true,true)), selectedSaved=selectedInventory.filter(x=>x.caption_state==="saved").length;
 const selectedCoverage={sampled:selectedInventory.length,classified:selectedInventory.filter(x=>x.label).length,saved:selectedSaved,reviewed:selectedInventory.filter(x=>x.classification_status==="human_reviewed").length};
 const selectedResponses=MonitorMap.responses(v);
 $("#edition").textContent=data.batches.map(b=>b.id).join(" / ") || "NO BATCH";
 $("#snapshot").textContent=`SNAPSHOT ${new Date(data.as_of).toLocaleString()}`;
 // Repeated weekly observations of one video must not inflate cumulative views.
 const uniqueRelated=[...related.reduce((m,x)=>{const old=m.get(x.id);if(!old||(x.engagement?.captured_at||'')>(old.engagement?.captured_at||''))m.set(x.id,x);return m;},new Map()).values()];
 const relevantViews=sum(uniqueRelated,"views"), relevantLikes=sum(uniqueRelated,"likes");
 $("#stats").innerHTML=`<div class="stat"><span>Security-related videos</span><b>${num(uniqueRelated.length)}</b><small>of ${num(selectedCoverage.classified)} classified sources in this selection</small></div><div class="stat stat-hero"><span>Views on security-related videos</span><b>${num(relevantViews.value)}</b><small>Lifetime views · ${relevantViews.n}/${uniqueRelated.length} counters available · not unique viewers</small></div><div class="stat"><span>Likes on related videos</span><b>${num(relevantLikes.value)}</b><small>${relevantLikes.n}/${uniqueRelated.length} counters available</small></div>`;
 const missingText=Math.max(0,selectedCoverage.sampled-selectedCoverage.saved), pendingCoding=Math.max(0,selectedCoverage.saved-selectedCoverage.classified);
 $(".coverage-details summary").textContent=`Data coverage · ${selectedCoverage.classified} of ${selectedCoverage.sampled} sampled sources classified · ${uniqueRelated.length} security-related · ${missingText} need English text · ${pendingCoding} have text and await valid classification`;
 const country=countries.find(x=>x.iso2===$("#country").value)?.country_name || "Europe";
 $("#focus-title").textContent=country;$("#map-focus").textContent=country.toUpperCase();
 const topics=Object.entries(data.topic_labels||{}).map(([k,n])=>[k,n,related.filter(x=>x.label.topics.includes(k)).length]).filter(x=>x[2]).sort((a,b)=>b[2]-a[2]);
 $("#topics").innerHTML=topics.slice(0,7).map(([k,n,count])=>`<button class="topic-button" data-topic="${esc(k)}"><span>${esc(n)}</span><b>${count}</b></button>`).join("") || '<p class="small">No coded topics for these filters.</p>';
 const lead=topics[0];
 $('#situation-brief').innerHTML=`<strong>WEEK AT A GLANCE</strong><span>${lead?`Most observed topic: <b>${esc(lead[1])}</b> · ${lead[2]} security-related sources`:'No classified topic for this selection'}</span><span><b>${selectedResponses.total}</b> comments analysed for message alignment and sentiment · ${selectedResponses.human_reviewed} human reviewed</span>`;
 renderGovernment();
 const health={saved:selectedSaved,blocked:selectedInventory.filter(x=>x.caption_state==='blocked').length,unavailable:selectedInventory.filter(x=>x.caption_state==='unavailable').length,unverified:selectedInventory.filter(x=>x.caption_state==='unverified').length}, saved=selectedSaved;
 const selectedComments=MonitorMap.latest(rows()).reduce((n,x)=>n+(x.retained_comments||0),0);
 const recovery=data.caption_recovery||[], audio=recovery.some(x=>x.audio_configured);
 const stopped=recovery.some(x=>x.audio_stopped==='audio_access_unavailable');
 const recoveryNote=stopped?'Public audio retrieval is also blocked. These sources remain unclassified until evidence can be retrieved.':audio?'Automatic audio transcription is enabled. Missing audio can be recovered in bounded Sunday runs on the configured Mac.':'Audio recovery has not run in this snapshot.';
 $("#quality").innerHTML=`<div class="pipeline-line"><span>Sources in selection</span><b>${selectedCoverage.sampled}</b></div><div class="pipeline-line"><span>English text saved</span><b>${saved}</b></div><div class="pipeline-meter"><span style="width:${selectedCoverage.sampled?saved/selectedCoverage.sampled*100:0}%"></span></div><div class="pipeline-line warn"><span>Retrieval blocked</span><b>${health.blocked||0}</b></div><div class="pipeline-line warn"><span>No English access found</span><b>${health.unavailable||0}</b></div><div class="pipeline-line"><span>Access unverified</span><b>${health.unverified||0}</b></div><p class="small">SELECTED WINDOW · ${selectedComments} comments retained.<br>Weekly collection: Sunday 00:37 Europe/Amsterdam.<br>Saved-text classification follows recovered evidence.<br>YouTube may block caption requests even when a video has subtitles.<br>${esc(recoveryNote)}<br>AI coding is automatic once English text is saved. Human review is a separate quality sample.</p>`;
 $("#roles").innerHTML=roles.map(r=>`<div class="role" style="color:${colors[r]}"><span class="icon" aria-hidden="true">${icons[r]}</span><div>${esc(data.role_labels?.[r]||human(r))}<small>Sources portraying this role</small></div><b>${related.filter(x=>x.label.roles.some(z=>z.role===r&&($("#country").value==="all"||z.entity_code===$("#country").value))).length}</b></div>`).join("");
 const ex={comparative:"Comparative",endorsement:"Expert / testimonial",entertainment:"Entertainment / storytelling",mnemonic_devices:"Mnemonic devices"};
 $("#execution").innerHTML=Object.entries(ex).map(([k,n])=>{
   const present=related.filter(x=>x.label.execution[k]==="present").length;
   const absent=related.filter(x=>x.label.execution[k]==="absent_after_watching").length;
   const notObserved=related.filter(x=>x.label.execution[k]==="not_observed_in_transcript").length;
   const unassessable=related.filter(x=>x.label.execution[k]==="not_observable").length;
   const pending=related.length-present-absent-notObserved-unassessable;
   return bar(n,present,related.length)+`<p class="execution-coverage small">${present} present · ${notObserved} not observed in text · ${unassessable} cannot assess${absent ? ` · ${absent} confirmed absent after viewing` : ""}${pending ? ` · ${pending} awaiting assessment` : ""}</p>`;
 }).join("")+`<p class="small">Bars show confirmed presence / ${related.length} security-related videos. Not observed in text does not mean absent from the video. Categories can overlap.</p>`;
 renderResponses(rows());
 $("#engagement").innerHTML=`<div class="metric-grid">${[["Views","views"],["Likes","likes"],["Total comments","total_comments"]].map(([name,k])=>{const s=sum(all,k);return `<div><b>${num(s.value)}</b><small>${name} · ${s.n}/${all.length} counters</small></div>`}).join("")}</div><p class="small">Latest saved counters · shares unavailable · views are not unique people.</p>`;
 $("#data-status").textContent=`${selectedCoverage.classified} of ${selectedCoverage.sampled} sampled sources have usable English text and valid classifications, including ${selectedCoverage.reviewed} human-reviewed video labels. Of those classified sources, ${uniqueRelated.length} are security-related and appear in the security totals above. ${missingText} still need English text; ${pendingCoding} have text but await a valid classification. ${selectedResponses.total} comments are classified, including ${selectedResponses.human_reviewed} human-reviewed comment labels. AI results publish provisionally only after evidence and classification checks pass. Human corrections take precedence. This sample does not establish country-level public opinion or a trend.`;
 renderMap();renderRanking();renderFeed();renderEvidence();
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
 const retained=MonitorMap.latest(v).reduce((n,x)=>n+(x.retained_comments||0),0);
 $('#response-count').textContent=`${num(r.total)} COMMENTS`;
 $('#responses').innerHTML=responseLegend(r)+`<p class="small">${r.human_reviewed} human-reviewed · ${r.total-r.human_reviewed} AI-only. ${Math.max(0,retained-r.total)} retained comments in this selection await classification. Latest saved comments per unique video. Praise of presentation is separate from agreement with the main message. Counts describe retained comments, not population opinion.</p>`;
}
function renderMap(){
 const all=rows(), layer=$('#metric').value, field=$('#response-metric').value;
 const points=layer==='government'?[]:countries.map(c=>({...c,...MonitorMap.aggregate(all,c.iso2)})).filter(c=>c.count&&($('#country').value==='all'||$('#country').value===c.iso2));
 const max=Math.max(1,...points.map(c=>c.views.value||0));
 const responseMax=Math.max(1,...points.flatMap(c=>MonitorMap.mapCategories[field].map(k=>c.responses[field][k]||0)));
 $('#markers').innerHTML=points.map(c=>{
   const [x,y]=project(c.longitude,c.latitude), radius=c.views.value?Math.max(3,32*Math.sqrt(c.views.value/max)):3;
   const selected=$('#country').value===c.iso2?'selected':'';
   const attrs=`data-country="${c.iso2}" tabindex="0" role="button"`;
   const video=layer==='comments'?'':`<g class="marker video-marker ${selected}" ${attrs} data-measure="views" aria-label="${esc(c.country_name)}: ${num(c.views.value)} views, ${c.count} classified videos"><title>${esc(c.country_name)} · ${num(c.views.value)} views · ${c.count} classified videos</title><circle class="orbit" r="${radius+5}"/><circle r="${radius}"/><circle class="core" r="2"/></g>`;
   const values=Object.entries(c.responses[field]).filter(([key,n])=>n>0&&MonitorMap.mapCategories[field].includes(key));
   const symbols=layer==='videos'?'':values.map(([key,n],i)=>{
     const style=responseStyles[key]||responseStyles.unclear, size=MonitorMap.markerSize(n,responseMax);
     const dx=layer==='comments'?0:radius+size+9,dy=(i-(values.length-1)/2)*40;
     return `<g class="response-marker ${selected}" ${attrs} data-count="${n}" data-size="${size}" data-measure="${field}|${key}" transform="translate(${dx},${dy})" aria-label="${esc(c.country_name)}: ${n} ${esc(human(key))} comments"><title>${esc(c.country_name)} · ${esc(human(key))} · ${n} comments</title><rect x="${-size-2}" y="${-size-2}" width="${size*2+4}" height="${size*2+4}" fill="#070c0e" fill-opacity=".8"/><text class="response-glyph" text-anchor="middle" dominant-baseline="central" style="fill:${style.color};font-size:${size*2}px">${style.shape}</text></g>`;
   }).join('');
   if(!video&&!symbols)return '';
   return `<g transform="translate(${x},${y})">${video}${symbols}<text class="country-code" x="-7" y="${radius+16}">${c.iso2}</text></g>`;
 }).join('');
 const r=MonitorMap.responses(rows());
 $('#map-key').innerHTML=(!['comments','government'].includes(layer)?'<span class="video-key">● Classified videos · size follows views</span>':'')+(!['videos','government'].includes(layer)?Object.entries(r[field]).filter(([key,n])=>n>0&&MonitorMap.mapCategories[field].includes(key)).map(([key,n])=>{const style=responseStyles[key]||responseStyles.unclear;return `<span><b style="color:${style.color}">${style.shape}</b> ${esc(human(key))} ${num(n)}</span>`}).join(''):'');
 const govVisible=layer==='both'||layer==='government';
 const govByCountry=new Map();for(const item of governmentData.items||[]){if(['provisional','human_reviewed'].includes(item.classification_status)&&item.related===true)govByCountry.set(item.country_code,(govByCountry.get(item.country_code)||0)+1);}
 const maxGov=Math.max(1,...govByCountry.values());
 $('#government-markers').innerHTML=govVisible?countries.filter(c=>govByCountry.has(c.iso2)&&($('#country').value==='all'||$('#country').value===c.iso2)).map(c=>{const [x,y]=project(c.longitude,c.latitude),n=govByCountry.get(c.iso2),size=Math.round(13+14*Math.sqrt(n/maxGov));return `<g class="government-marker" transform="translate(${x},${y})" aria-label="${esc(c.country_name)}: ${n} related government communications"><title>${esc(c.country_name)} · ${n} related government communications</title><text x="9" y="-8" style="font-size:${size}px">★</text></g>`}).join(''):'';
 if(govVisible)$('#map-key').insertAdjacentHTML('beforeend',`<span><b class="gov-star">★</b> Related government communications · size follows count · ${num([...govByCountry.values()].reduce((a,b)=>a+b,0))}</span>`);
 $('#response-metric').disabled=layer==='videos'||layer==='government';
}
function governmentTopicCodes(item){
 return [...new Set((item.topics?.length?item.topics:[item.primary_narrative,...(item.secondary_narratives||[])]).filter(Boolean))];
}
function updateTrendCountries(){
 const available=new Set((governmentData.items||[]).filter(x=>x.related===true&&['provisional','human_reviewed'].includes(x.classification_status)).map(x=>x.country_code));
 const options=countries.filter(c=>available.has(c.iso2)).sort((a,b)=>a.country_name.localeCompare(b.country_name));
 for(const id of ['trend-country-1','trend-country-2','trend-country-3']){
  const select=$('#'+id),previous=select.value,initial=id==='trend-country-1'?'<option value="all">Europe · all countries</option>':'<option value="none">No comparison</option>';
  select.innerHTML=initial+options.map(c=>`<option value="${esc(c.iso2)}">${esc(c.country_name)}</option>`).join('');
  if([...select.options].some(o=>o.value===previous))select.value=previous;
 }
}
function renderGovernmentTrends(){
 const coded=(governmentData.items||[]).filter(x=>x.related===true&&['provisional','human_reviewed'].includes(x.classification_status)&&governmentTopicCodes(x).length);
 const dated=coded.map(x=>({...x,chartDate:(x.published_date||x.published_at||'').slice(0,10)})).filter(x=>/^\d{4}-\d{2}-\d{2}$/.test(x.chartDate));
 const chartHost=$('#government-trend-charts'),legend=$('#government-trend-legend'),note=$('#government-trend-note');
 if(!dated.length){chartHost.innerHTML='<p class="empty">Narrative dynamics will appear when related government communications are classified.</p>';legend.innerHTML='';note.textContent='';return;}
 const allDates=dated.map(x=>x.chartDate).sort(),first=allDates[0],last=allDates.at(-1),range=$('#trend-range').value;
 let from=first,to=last;
 if(range==='7'||range==='30')from=new Date(Date.parse(last+'T00:00:00Z')-(Number(range)-1)*86400000).toISOString().slice(0,10);
 if(range==='custom'){from=$('#trend-from').value||first;to=$('#trend-to').value||last;}
 from=from<first?first:from;to=to>last?last:to;
 if(from>to){chartHost.innerHTML='<p class="empty">Choose a start date on or before the end date.</p>';legend.innerHTML='';note.textContent='';return;}
 const days=[];for(let d=Date.parse(from+'T00:00:00Z'),end=Date.parse(to+'T00:00:00Z');d<=end;d+=86400000)days.push(new Date(d).toISOString().slice(0,10));
 const selected=dated.filter(x=>x.chartDate>=from&&x.chartDate<=to),topics=[...new Set(selected.flatMap(governmentTopicCodes))].sort();
 const selectedCountries=[...new Set(['trend-country-1','trend-country-2','trend-country-3'].map(id=>$('#'+id).value).filter(x=>x!=='none'))];
 const colorFor=(topic)=>{const index=Object.keys(data.topic_labels||{}).sort().indexOf(topic);return `hsl(${Math.round(((index<0?topic.split('').reduce((n,c)=>n+c.charCodeAt(0),0):index)*137.508)%360)} 78% 68%)`;};
 const countryName=code=>code==='all'?'Europe · all collected countries':countries.find(c=>c.iso2===code)?.country_name||code;
 const panels=selectedCountries.map(code=>{
  const items=selected.filter(x=>code==='all'||x.country_code===code),daily=new Map(days.map(day=>[day,[]]));
  for(const item of items)daily.get(item.chartDate).push(...governmentTopicCodes(item));
  const counts=new Map(),series=new Map(topics.map(t=>[t,[]]));let total=0;
  for(const day of days){for(const topic of daily.get(day)){counts.set(topic,(counts.get(topic)||0)+1);total++;}for(const topic of topics)series.get(topic).push(total?100*(counts.get(topic)||0)/total:null);}
  const w=1000,h=270,left=54,right=24,top=22,bottom=46,plotW=w-left-right,plotH=h-top-bottom;
  const x=i=>left+(days.length===1?plotW/2:i*plotW/(days.length-1)),y=value=>top+plotH*(1-value/100);
  const grid=[0,25,50,75,100].map(v=>`<line x1="${left}" y1="${y(v)}" x2="${w-right}" y2="${y(v)}" class="trend-grid"/><text x="${left-10}" y="${y(v)+4}" text-anchor="end" class="trend-axis">${v}%</text>`).join('');
  const step=Math.max(1,Math.ceil(days.length/7)),tickIndexes=[...new Set([...days.keys()].filter(i=>i%step===0).concat(days.length-1))];
  const ticks=tickIndexes.map(i=>`<text x="${x(i)}" y="${h-13}" text-anchor="middle" class="trend-axis">${esc(days[i].slice(5))}</text>`).join('');
  const paths=topics.filter(t=>!hiddenTrendTopics.has(t)&&(counts.get(t)||0)>0).map(t=>{
   const values=series.get(t),points=values.map((v,i)=>v===null?null:[i,v]).filter(Boolean),path=points.map(([i,v],j)=>`${j?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' '),lastValue=values.at(-1);
   return `<path d="${path}" fill="none" stroke="${colorFor(t)}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity=".88"><title>${esc(countryName(code))} · ${esc(data.topic_labels?.[t]||human(t))} · ${lastValue.toFixed(1)}% (${counts.get(t)} labels)</title></path><circle cx="${x(days.length-1)}" cy="${y(lastValue)}" r="2.5" fill="${colorFor(t)}"><title>${esc(data.topic_labels?.[t]||human(t))}: ${lastValue.toFixed(1)}%</title></circle>`;
  }).join('');
  return `<div class="trend-panel"><div class="trend-panel-title"><strong>${esc(countryName(code))}</strong><span>${num(items.length)} related communications · ${num(total)} topic labels</span></div>${total?`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Daily cumulative narrative shares for ${esc(countryName(code))}, ${esc(from)} to ${esc(to)}">${grid}${ticks}${paths}</svg>`:'<p class="empty">No related communications in this period.</p>'}</div>`;
 });
 chartHost.innerHTML=panels.join('');
 legend.innerHTML=topics.map(t=>`<button type="button" data-trend-topic="${esc(t)}" aria-pressed="${!hiddenTrendTopics.has(t)}" class="${hiddenTrendTopics.has(t)?'trend-off':''}"><i style="background:${colorFor(t)}"></i>${esc(data.topic_labels?.[t]||human(t))}</button>`).join('');
 note.textContent=`${from} to ${to} · Cumulative from the start of this selected period. Daily values use publication dates; each related topic label contributes once to the denominator. Tap a narrative in the legend to show or hide it. Updated with each published collection.`;
}
function renderGovernment(){
 updateTrendCountries();renderGovernmentTrends();
 const items=(governmentData.items||[]).filter(x=>['provisional','human_reviewed'].includes(x.classification_status)), related=items.filter(x=>x.related===true);
 const pendingSources=(governmentSourceDirectory.sources||[]).filter(x=>x.collection_status==='pending');
 $('#government-pending').innerHTML=pendingSources.length?'<h2>Pending collection · '+pendingSources.length+' countries</h2><p>Official news sections are recorded, but automatic retrieval is not yet reliable. Missing communications here do not mean these governments published nothing.</p><div class="pending-country-grid">'+pendingSources.map(x=>'<a href="'+esc(x.url)+'" target="_blank" rel="noopener"><b>'+esc(x.name)+'</b><span>Pending ↗</span></a>').join('')+'</div>':'';
 const latestByCountry=new Map(); for(const item of related.slice().sort((a,b)=>(b.published_at||'').localeCompare(a.published_at||''))){if(!latestByCountry.has(item.country_code))latestByCountry.set(item.country_code,item);} const highlights=[...latestByCountry.values()];
 $('#government-ticker').innerHTML=highlights.length?'<span class="ticker-label">GOVERNMENT WATCH · '+highlights.length+' COUNTRIES</span><div class="ticker-window"><div class="ticker-track">'+[...highlights,...highlights].map(x=>'<a href="'+esc(x.url)+'" target="_blank" rel="noopener" title="'+esc(x.country)+' · '+esc(x.title)+'"><b>'+esc(x.country)+'</b> '+esc(x.ticker_message||x.english_summary||x.title)+'</a>').join('')+'</div></div>':'<span class="ticker-label">GOVERNMENT WATCH</span><span class="ticker-empty">No classified related government communications in this collection window.</span>';
 const tickerTrack=$('#government-ticker .ticker-track');if(tickerTrack)tickerTrack.style.animationDuration=Math.max(120,Math.ceil(tickerTrack.scrollWidth/2/28))+'s';
 const country=$('#government-country')?.value||'all', narrative=$('#government-narrative')?.value||'all', review=$('#government-review')?.value||'all';
 const filtered=items.filter(x=>(country==='all'||x.country_code===country)&&(narrative==='all'||[x.primary_narrative,...(x.secondary_narratives||[])].includes(narrative))&&(review==='all'||x.classification_status===review));
 if($('#government-source-list'))$('#government-source-list').innerHTML='<p class="panel-note">'+filtered.length+' communications · '+(governmentData.window_start?esc(governmentData.window_start.slice(0,10))+' to '+esc(governmentData.window_end?.slice(0,10)||''):'No collection yet')+' · routine human audit sample: 3%.</p>'+filtered.map(x=>'<article class="government-item"><div class="government-item-head"><span>'+esc(x.country)+' · '+esc(x.published_date||x.published_at?.slice(0,10)||'date unavailable')+(x.publication_precision==='day'?' · date only':'')+'</span><span class="source-state '+(x.classification_status==='human_reviewed'?'':'pending')+'">'+esc(human(x.classification_status||'unclassified'))+'</span></div><h2><a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.ticker_message||x.english_summary||x.title)+' ↗</a></h2><p>'+esc(x.english_summary||x.ticker_message||'Awaiting English translation and classification.')+'</p>'+(x.primary_narrative?'<div class="government-label"><b>'+esc(human(x.primary_narrative))+'</b>'+(x.secondary_narratives||[]).map(n=>'<span>'+esc(human(n))+'</span>').join('')+'<small>'+Math.round((x.confidence||0)*100)+'% confidence · '+esc(x.short_rationale||'')+'</small></div>':'')+'<details><summary>Classification rationale and source</summary><p>'+esc(x.short_rationale||'Translation is applied before classification; the source translation is not republished.')+'</p><p class="small">Original title: '+esc(x.title)+'<br>Official source: <a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.url)+'</a></p></details></article>').join('')||'<p class="empty">No government communications match these filters.</p>';
}
function renderRanking(){
 const alignment=$('#rank-alignment').value, sentiment=$('#rank-sentiment').value;
 const result=MonitorMap.ranking(rows(false),countries,alignment,sentiment);
 const period=`${$('#batch').selectedOptions[0].textContent} · ${dateLabel()}`,topic=$('#topic').selectedOptions[0].textContent;
 $('#ranking-total').textContent=result.available?`${num(result.total)} MATCHING COMMENTS`:'JOINT COUNTS UNAVAILABLE';
 $('#ranking-context').textContent=`${period} · ${topic}. All countries are ranked, independently of the country selector above. Both filters apply to the same comment.`;
 if(!result.available){$('#ranking-denominator').textContent='';$('#country-ranking').innerHTML='<p class="small">Combined filters need the updated public snapshot. No intersection is inferred from separate alignment and sentiment totals.</p>';return;}
 $('#ranking-denominator').textContent=result.total?`Percentage = comments linked to this country ÷ ${num(result.total)} matching comments in this window. A video may mention several countries, so shares overlap and need not sum to 100%. Country mentions are not audience locations.`:'No comments match these filters. Percentages are unavailable, not zero evidence of a response.';
 $('#country-ranking').innerHTML=result.rows.map((c,i)=>`<div class="ranking-row ${$('#country').value===c.iso2?'rank-selected':''}"><span class="rank-position">${i+1}</span><span class="rank-name">${esc(c.country_name)}</span><div class="ranking-track" aria-hidden="true"><span style="width:${c.percentage||0}%"></span></div><b>${c.percentage===null?'—':c.percentage.toFixed(1)+'%'}</b><span class="rank-count">${num(c.count)} comments</span></div>`).join('');
}
function showCountry(code,measure){
 const country=countries.find(c=>c.iso2===code);if(!country)return;
 const result=MonitorMap.aggregate(rows(false),code), r=result.responses;
 const period=`${$('#batch').selectedOptions[0].textContent} · ${dateLabel()}`, topic=$('#topic').selectedOptions[0].textContent;
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
function route(){const r=['evidence','government','methodology'].includes(location.hash.slice(1))?location.hash.slice(1):'monitor';for(const id of ['monitor','evidence','government','methodology'])$('#'+id).hidden=id!==r;document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.hash==='#'+r?'page':'false'));}
async function init(){try{
 const rev=document.documentElement.dataset.build||Date.now();const result=await Promise.all(['data.json','countries.json','assets/world.json','methodology.html','government-data.json','government-sources.json'].map(async p=>{const r=await fetch(`${p}?v=${rev}`);if(!r.ok&&p==='government-data.json')return {items:[]};if(!r.ok)throw Error('Snapshot unavailable');return p.endsWith('.html')?r.text():r.json()}));
 data=result[0];countries=result[1];governmentData=result[4];governmentSourceDirectory=result[5];countries=countries.countries||countries;
 const coded=new Map(data.videos.map(v=>[v.batch+'|'+v.id,v]));inventory=(data.inventory||data.videos).map(v=>({...v,...coded.get(v.batch+'|'+v.id)}));
 $('#methodology').innerHTML=result[3];$('#geography').innerHTML=result[2].features.map(f=>`<path d="${geometry(f.geometry)}"/>`).join('');
 $('#country').insertAdjacentHTML('beforeend',countries.map(c=>`<option value="${esc(c.iso2)}">${esc(c.country_name)}</option>`).join(''));
 $('#batch').insertAdjacentHTML('beforeend',data.batches.map(b=>`<option value="${esc(b.id)}">${esc(b.id)}</option>`).join(''));
 $('#topic').insertAdjacentHTML('beforeend',Object.entries(data.topic_labels||{}).map(([c,n])=>`<option value="${esc(c)}">${esc(n)}</option>`).join(''));
 $('#government-country').insertAdjacentHTML('beforeend',countries.map(c=>`<option value="${esc(c.iso2)}">${esc(c.country_name)}</option>`).join(''));
 const governmentLabels=[...new Set((governmentData.items||[]).flatMap(x=>[x.primary_narrative,...(x.secondary_narratives||[])].filter(Boolean)))];$('#government-narrative').insertAdjacentHTML('beforeend',governmentLabels.map(n=>`<option value="${esc(n)}">${esc(human(n))}</option>`).join(''));
 configureDateInputs();
 render();route();
 }catch(e){$('#data-status').textContent='Snapshot unavailable. Please refresh or check the publishing workflow.';console.error(e);}}
for(const id of ['batch','country','topic','metric','response-metric'])$('#'+id).onchange=render;
 for(const id of ['government-country','government-narrative','government-review'])$('#'+id).onchange=renderGovernment;
 $('#trend-range').onchange=()=>{document.querySelectorAll('.trend-custom-date').forEach(el=>el.hidden=$('#trend-range').value!=='custom');renderGovernmentTrends();};
 for(const id of ['trend-from','trend-to','trend-country-1','trend-country-2','trend-country-3'])$('#'+id).onchange=renderGovernmentTrends;
 $('#government-trend-legend').onclick=e=>{const button=e.target.closest('[data-trend-topic]');if(!button)return;const topic=button.dataset.trendTopic;if(hiddenTrendTopics.has(topic))hiddenTrendTopics.delete(topic);else hiddenTrendTopics.add(topic);renderGovernmentTrends();};
$('#date-range').onchange=()=>{$('#custom-dates').hidden=$('#date-range').value!=='custom';if($('#date-range').value==='custom')configureDateInputs();render();};
for(const id of ['date-from','date-to'])$('#'+id).onchange=render;
for(const id of ['rank-alignment','rank-sentiment'])$('#'+id).onchange=renderRanking;
$('#rank-reset').onclick=()=>{$('#rank-alignment').value='all';$('#rank-sentiment').value='all';renderRanking();};
$('#feed-pause').onclick=()=>{feedPaused=!feedPaused;drawFeed();};
$('#feed-mode').onchange=renderFeed;$('#search').oninput=renderEvidence;
$('#reset').onclick=()=>{for(const id of ['batch','date-range','country','topic'])$('#'+id).value='all';for(const id of ['date-from','date-to'])$('#'+id).value='';$('#custom-dates').hidden=true;$('#metric').value='both';$('#response-metric').value='alignment';$('#rank-alignment').value='all';$('#rank-sentiment').value='all';zoom=1;setZoom();render();};
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
async function refreshSnapshot(){
  if(document.hidden||$('#source-dialog').open||$('#country-dialog').open||$('#camera-list-dialog').open)return;
  try{
    const governmentResponse=await fetch(`government-data.json?refresh=${Date.now()}`,{cache:'no-store'});
    if(governmentResponse.ok){const latestGovernment=await governmentResponse.json();if(latestGovernment.as_of!==governmentData.as_of){governmentData=latestGovernment;renderGovernment();renderMap();}}
    const response=await fetch(`data.json?refresh=${Date.now()}`,{cache:'no-store'});
    if(!response.ok)return;
    const updated=await response.json();
    if(!Array.isArray(updated.videos)||!Array.isArray(updated.batches)||updated.as_of<=data.as_of)return;
    data=updated;
    const coded=new Map(data.videos.map(v=>[v.batch+'|'+v.id,v]));
    inventory=(data.inventory||data.videos).map(v=>({...v,...coded.get(v.batch+'|'+v.id)}));
    const existing=new Set([...$('#batch').options].map(o=>o.value));
    for(const b of data.batches)if(!existing.has(b.id))$('#batch').insertAdjacentHTML('beforeend',`<option value="${esc(b.id)}">${esc(b.id)}</option>`);
    configureDateInputs();
    render();
  }catch{/* Retain the last successfully loaded snapshot during network failures. */}
}
setInterval(refreshSnapshot,300000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSnapshot();});
window.addEventListener('focus',refreshSnapshot);

// Animate a focus reticle between actual country markers, never invented events.
let scanIndex=0;
setInterval(()=>{if(document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches||$('#monitor').hidden)return;const markers=[...document.querySelectorAll('#markers .marker')];if(!markers.length)return;markers.forEach(m=>m.classList.remove('scan-focus'));markers[scanIndex++%markers.length].classList.add('scan-focus');},2200);
