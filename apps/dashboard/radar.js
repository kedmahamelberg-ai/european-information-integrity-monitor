"use strict";
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


const $=s=>document.querySelector(s), reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
let paused=reduced, points=[], step=0;
function tick(){if(!points.length)return;const p=points[step%points.length];$('#target').setAttribute('visibility','visible');$('#target').setAttribute('transform',`translate(${p.x},${p.y})`);document.getElementById('dot-'+p.code).setAttribute('opacity','1');$('#caption').textContent=p.name+' · '+p.n+' source mentions · weekly sample';step++;}
$('#pause').textContent=paused?'Play scan':'Pause';$('#pause').onclick=()=>{paused=!paused;$('#pause').textContent=paused?'Play scan':'Pause';};
Promise.all(['data.json','countries.json','assets/world.json'].map(p=>fetch(p).then(r=>{if(!r.ok)throw Error();return r.json()}))).then(([data,countries,world])=>{
$('#land').innerHTML=world.features.map(f=>`<path d="${geometry(f.geometry)}"/>`).join('');
const rows=data.inventory||data.videos, coded=new Set(data.videos.filter(v=>v.label).map(v=>v.id));
points=(countries.countries||countries).map(c=>{const sources=rows.filter(v=>v.countries.includes(c.iso2)),[x,y]=project(c.longitude,c.latitude);return {code:c.iso2,name:c.country_name,x,y,n:new Set(sources.map(v=>v.id)).size,ready:sources.some(v=>coded.has(v.id))}}).filter(p=>p.n);
$('#dots').innerHTML=points.map(p=>`<circle id="dot-${p.code}" class="point ${p.ready?'':'waiting'}" cx="${p.x}" cy="${p.y}" r="${4+Math.sqrt(p.n)*3}" opacity="${reduced?1:.15}"/>`).join('');tick();
}).catch(()=>{$('#caption').textContent='Weekly snapshot unavailable';});
setInterval(()=>{if(!paused&&!document.hidden)tick()},1800);
