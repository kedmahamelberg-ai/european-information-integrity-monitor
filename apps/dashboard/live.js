/* Public third-party streams only. No recording or media proxying. */
"use strict";
(function () {
  function nextCamera(cameras, previous, occupied, failed, time) {
    for (let step = 1; step <= cameras.length; step++) {
      const index = (previous + step) % cameras.length;
      const camera = cameras[index];
      if (camera.status === "live" && !occupied.has(camera.country_code) &&
          (failed.get(camera.id) || 0) <= time) return index;
    }
    return -1;
  }
  if (typeof module !== "undefined") module.exports = { nextCamera };
  if (typeof document === "undefined") return;

  const wall = document.querySelector("#camera-wall");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let cameras = [], slots = [], paused = reduceMotion, hold = reduceMotion;
  const failures = new Map();
  const byId = id => document.getElementById(id);
  const safe = text => String(text ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const active = () => !document.hidden && !byId("monitor").hidden && !paused;
  function controls() {
    byId("camera-pause").textContent = paused ? "Play cameras" : "Pause cameras";
    byId("camera-pause").setAttribute("aria-pressed", String(paused));
    byId("rotation-pause").textContent = hold ? "Rotate views" : "Hold views";
    byId("rotation-pause").setAttribute("aria-pressed", String(hold));
  }
  function badge(slot, text, playing = false) {
    slot.root.querySelector(".camera-state").textContent = text;
    slot.root.querySelector(".camera-state").classList.toggle("playing", playing);
  }
  function destroy(slot) {
    clearTimeout(slot.watchdog);
    if (slot.player) { try { slot.player.destroy(); } catch {} }
    slot.player = null;
  }
  function advance(slot) {
    const occupied = new Set(slots.filter(s => s !== slot && s.index >= 0)
      .map(s => cameras[s.index].country_code));
    const index = nextCamera(cameras, slot.index, occupied, failures, Date.now());
    destroy(slot);
    slot.index = index;
    slot.elapsed = 0;
    if (index < 0) {
      slot.root.innerHTML = '<p class="camera-message">No available stream in this rotation. Retrying in one minute. Open the camera list for original sources.</p>';
      return;
    }
    mount(slot);
  }
  function mount(slot) {
    const c = cameras[slot.index];
    slot.root.innerHTML = `<div class="camera-caption"><div><strong>${safe(c.city)} / ${safe(c.country_code)}</strong><small>${safe(c.view)}</small></div><div><span class="camera-state">CONNECTING</span><div class="camera-clock"></div></div></div><div class="camera-player"><div id="camera-player-${slot.number}"></div></div><button class="camera-start" hidden>Start stream</button><div class="camera-bottom"><a href="${safe(c.source_url)}" target="_blank" rel="noopener" title="${safe(c.operator)}">${safe(c.operator)} ↗</a><button class="camera-next">Next country →</button></div><div class="camera-progress"><span></span></div>`;
    slot.root.querySelector(".camera-next").onclick = () => advance(slot);
    slot.root.querySelector(".camera-start").onclick = () => {
      paused = false; controls();
      slot.player?.mute(); slot.player?.playVideo();
    };
    if (!active()) { badge(slot, "PAUSED"); return; }
    const generation = ++slot.generation;
    slot.player = new YT.Player(`camera-player-${slot.number}`, {
      host: "https://www.youtube-nocookie.com",
      width: "100%", height: "200", videoId: c.video_id,
      playerVars: {autoplay:1, mute:1, playsinline:1, controls:1, rel:0, origin:location.origin},
      events: {
        onReady(event) {
          if (generation !== slot.generation) return;
          event.target.getIframe().setAttribute("title", `${c.city}, ${c.country}: ${c.view}`);
          event.target.getIframe().setAttribute("allow", "autoplay; encrypted-media; picture-in-picture; fullscreen");
          event.target.mute();
          if (active()) event.target.playVideo(); else event.target.pauseVideo();
        },
        onStateChange(event) {
          if (generation !== slot.generation) return;
          if (event.data === 1) {
            clearTimeout(slot.watchdog);
            badge(slot, "● LIVE", true);
            slot.root.querySelector(".camera-start").hidden = true;
          } else if (event.data === 0) fail(slot);
          else if (event.data === 2) badge(slot, "PAUSED");
          else if (event.data === 3) badge(slot, "BUFFERING");
        },
        onError() { if (generation === slot.generation) fail(slot); },
        onAutoplayBlocked() {
          if (generation !== slot.generation) return;
          clearTimeout(slot.watchdog);
          badge(slot, "PRESS START");
          slot.root.querySelector(".camera-start").hidden = false;
        }
      }
    });
    slot.watchdog = setTimeout(() => {
      if (!active() || generation !== slot.generation) return;
      if (slot.player?.getPlayerState?.() !== 1) {
        badge(slot, "PRESS START / NEXT");
        slot.root.querySelector(".camera-start").hidden = false;
      }
    }, 22000);
  }
  function fail(slot) {
    if (slot.index >= 0) failures.set(cameras[slot.index].id, Date.now() + 300000);
    slot.generation++;
    advance(slot);
  }
  function resumeVisibility() {
    for (const slot of slots) {
      if (!active()) { slot.player?.pauseVideo?.(); clearTimeout(slot.watchdog); }
      else if (!slot.player && slot.index >= 0) mount(slot);
      else slot.player?.playVideo?.();
    }
  }
  function boot() {
    wall.innerHTML = "";
    slots = [0,1].map(number => {
      const root = document.createElement("section");
      root.className = "camera-tile";
      root.setAttribute("aria-label", `Live city view ${number + 1}`);
      wall.appendChild(root);
      return {number,root,index:number===0?-1:4,player:null,elapsed:0,duration:60+number*15,generation:0};
    });
    // Only mounted cameras reserve countries, so initialization cannot reserve a phantom slot.
    slots[1].index = -1;
    advance(slots[0]);
    slots[1].index = 4;
    advance(slots[1]);
    setInterval(() => {
      for (const s of slots) {
        if (s.index >= 0) {
          const clock=s.root.querySelector(".camera-clock");
          if(clock) clock.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:cameras[s.index].timezone,hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date());
        }
        if (!active()) continue;
        if (s.index < 0) { if (++s.elapsed >= 60) advance(s); continue; }
        if (hold || s.root.matches(":hover") || s.root.contains(document.activeElement) || byId("source-dialog").open) continue;
        s.elapsed++;
        const bar=s.root.querySelector(".camera-progress span");
        if(bar)bar.style.width=`${Math.min(100,s.elapsed/s.duration*100)}%`;
        if(s.elapsed>=s.duration)advance(s);
      }
    },1000);
  }
  byId("camera-pause").onclick=()=>{paused=!paused;controls();resumeVisibility();};
  byId("rotation-pause").onclick=()=>{hold=!hold;controls();};
  byId("camera-list-open").onclick=()=>byId("camera-list-dialog").showModal();
  byId("camera-list-close").onclick=()=>byId("camera-list-dialog").close();
  document.addEventListener("visibilitychange",resumeVisibility);
  window.addEventListener("hashchange",()=>setTimeout(resumeVisibility,0));
  controls();
  fetch(`cameras.json?v=${document.documentElement.dataset.build||Date.now()}`)
    .then(r=>{if(!r.ok)throw Error("Camera catalogue unavailable");return r.json();})
    .then(catalogue=>{
      cameras=catalogue.cameras.filter(c=>c.status==='live' && /^[A-Za-z0-9_-]{11}$/.test(c.video_id) && Date.now()-Date.parse(c.checked_at)<48*3600000);
      byId("camera-directory").innerHTML=`<p class="small">Public streams, embedded from their original operators. Checked ${safe(catalogue.checked_at||catalogue.cameras[0]?.checked_at||'unknown')}. Offline streams are excluded from rotation. No footage is stored.</p><table><thead><tr><th>Country / city</th><th>View / operator</th><th>Status</th></tr></thead><tbody>${catalogue.cameras.map(c=>`<tr><td>${safe(c.country)}<br><b>${safe(c.city)}</b></td><td><a href="${safe(c.source_url)}" target="_blank" rel="noopener">${safe(c.view)} ↗</a><br>${safe(c.operator)}</td><td>${safe(c.status)}</td></tr>`).join('')}</tbody></table>`;
      if(!cameras.length){wall.innerHTML='<p class="camera-message">No recently verified live streams. Open the camera list for original sources.</p>';return;}
      if(window.YT?.Player)boot();
      else {window.onYouTubeIframeAPIReady=boot;const script=document.createElement('script');script.src='https://www.youtube.com/iframe_api';script.onerror=()=>{wall.innerHTML='<p class="camera-message">Camera player could not load. Open the camera list to watch at the source.</p>';};document.head.appendChild(script);}
    }).catch(()=>wall.innerHTML='<p class="camera-message">Camera directory unavailable. Please refresh.</p>');
})();
