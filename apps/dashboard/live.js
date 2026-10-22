/* Public third-party streams only. No recording or media proxying. */
"use strict";
(function () {
  function availableCamera(camera, time) {
    const checked = Date.parse(camera?.checked_at || "");
    return camera?.status === "live" && /^[A-Za-z0-9_-]{11}$/.test(camera.video_id) &&
      Number.isFinite(checked) && time - checked < 48 * 3600000;
  }
  function nextCamera(cameras, previous, occupied, failed, time) {
    for (let step = 1; step <= cameras.length; step++) {
      const index = (previous + step) % cameras.length;
      const camera = cameras[index];
      if (availableCamera(camera, time) && !occupied.has(camera.country_code) &&
          (failed.get(camera.id) || 0) <= time) return index;
    }
    return -1;
  }
  if (typeof module !== "undefined") module.exports = { availableCamera, nextCamera };
  if (typeof document === "undefined") return;

  const wall = document.querySelector("#camera-wall");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let cameras = [], slots = [], paused = reduceMotion, hold = reduceMotion, booted = false;
  let playerApiPromise = null, playerApiRetryAfter = 0;
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
  function loadPlayerApi() {
    if (window.YT?.Player) return Promise.resolve();
    if (playerApiPromise) return playerApiPromise;
    if (Date.now() < playerApiRetryAfter) return Promise.reject(new Error("Player API cooling down"));
    playerApiPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const previousReady = window.onYouTubeIframeAPIReady;
      let settled = false;
      const finish = error => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        window.onYouTubeIframeAPIReady = previousReady;
        if (error) {
          script.remove();
          playerApiRetryAfter = Date.now() + 300000;
          playerApiPromise = null;
          reject(error);
        } else resolve();
      };
      window.onYouTubeIframeAPIReady = () => {
        if (typeof previousReady === "function") previousReady();
        finish(window.YT?.Player ? null : new Error("Player API unavailable"));
      };
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      script.onerror = () => finish(new Error("Player API failed to load"));
      const timeout = setTimeout(() => finish(new Error("Player API timed out")), 12000);
      document.head.appendChild(script);
    });
    return playerApiPromise;
  }
  function destroy(slot) {
    clearTimeout(slot.watchdog);
    if (slot.player) { try { slot.player.destroy(); } catch {} }
    slot.player = null;
    slot.apiUnavailable = false;
  }
  function armWatchdog(slot, generation) {
    clearTimeout(slot.watchdog);
    slot.watchdog = setTimeout(() => {
      if (!active() || generation !== slot.generation || slot.autoplayBlocked) return;
      if (slot.player?.getPlayerState?.() !== 1) fail(slot);
    }, 22000);
  }
  function advance(slot) {
    const now = Date.now();
    const occupied = new Set(slots.filter(s => s !== slot && s.index >= 0)
      .filter(s => availableCamera(cameras[s.index], now))
      .map(s => cameras[s.index].country_code));
    const index = nextCamera(cameras, slot.index, occupied, failures, now);
    slot.generation++;
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
    const generation = ++slot.generation;
    slot.autoplayBlocked = false;
    slot.apiUnavailable = false;
    slot.root.innerHTML = `<div class="camera-caption"><div><strong>${safe(c.city)} / ${safe(c.country_code)}</strong><small>${safe(c.view)}</small></div><div><span class="camera-state">CONNECTING</span><div class="camera-clock"></div></div></div><div class="camera-player pending" data-message="Checking live stream…"><div id="camera-player-${slot.number}"></div></div><button class="camera-start" hidden>Start stream</button><div class="camera-bottom"><a href="${safe(c.source_url)}" target="_blank" rel="noopener" title="${safe(c.operator)}">${safe(c.operator)} ↗</a><button class="camera-next">Next country →</button></div><div class="camera-progress"><span></span></div>`;
    slot.root.querySelector(".camera-next").onclick = () => advance(slot);
    slot.root.querySelector(".camera-start").onclick = () => {
      if (slot.apiUnavailable) { playerApiRetryAfter = 0; mount(slot); return; }
      paused = false; controls();
      slot.autoplayBlocked = false;
      slot.root.querySelector(".camera-player").dataset.message = "Checking live stream…";
      armWatchdog(slot, slot.generation);
      slot.player?.mute(); slot.player?.playVideo();
    };
    if (!active()) { badge(slot, "PAUSED"); return; }
    loadPlayerApi().then(() => {
      if (generation !== slot.generation || !active()) return;
      slot.player = new window.YT.Player(`camera-player-${slot.number}`, {
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
            slot.root.querySelector(".camera-player").classList.remove("pending");
            badge(slot, "● LIVE", true);
            slot.root.querySelector(".camera-start").hidden = true;
          } else if (event.data === 0) fail(slot);
          else if (event.data === 2) badge(slot, "PAUSED");
          else if (event.data === 3) { slot.root.querySelector(".camera-player").classList.add("pending"); slot.root.querySelector(".camera-player").dataset.message = "Reconnecting live stream…"; badge(slot, "BUFFERING"); armWatchdog(slot, generation); }
        },
        onError() { if (generation === slot.generation) fail(slot); },
        onAutoplayBlocked() {
          if (generation !== slot.generation) return;
          clearTimeout(slot.watchdog);
          slot.autoplayBlocked = true;
          badge(slot, "PRESS START");
          slot.root.querySelector(".camera-player").dataset.message = "Autoplay blocked. Press Start stream.";
          slot.root.querySelector(".camera-start").hidden = false;
        }
      }
      });
      armWatchdog(slot, generation);
    }).catch(() => {
      if (generation !== slot.generation) return;
      playerApiRetryAfter = Math.max(playerApiRetryAfter, Date.now() + 300000);
      slot.apiUnavailable = true;
      slot.root.querySelector(".camera-player").classList.remove("pending");
      slot.root.querySelector(".camera-player").innerHTML = '<p class="camera-message">Live player unavailable in this browser. Open the operator source below, or retry here.</p>';
      badge(slot, "PLAYER UNAVAILABLE");
      const retry = slot.root.querySelector(".camera-start");
      retry.textContent = "Retry live player";
      retry.hidden = false;
    });
  }
  function fail(slot) {
    if (slot.index >= 0) failures.set(cameras[slot.index].id, Date.now() + 300000);
    advance(slot);
  }
  function resumeVisibility() {
    for (const slot of slots) {
      if (!active()) {
        slot.player?.pauseVideo?.(); clearTimeout(slot.watchdog);
      }
      else if (slot.apiUnavailable) { if (Date.now() >= playerApiRetryAfter) mount(slot); }
      else if (!slot.player && slot.index >= 0) mount(slot);
      else { slot.player?.playVideo?.(); if (!slot.autoplayBlocked) armWatchdog(slot, slot.generation); }
    }
  }
  function boot() {
    if (booted) return;
    booted = true;
    wall.innerHTML = "";
    slots = [0,1].map(number => {
      const root = document.createElement("section");
      root.className = "camera-tile";
      root.setAttribute("aria-label", `Live city view ${number + 1}`);
      wall.appendChild(root);
      return {number,root,index:-1,player:null,apiUnavailable:false,elapsed:0,duration:60+number*15,generation:0,autoplayBlocked:false};
    });
    // Only mounted cameras reserve countries, so initialization cannot reserve a phantom slot.
    slots[1].index = -1;
    advance(slots[0]);
    slots[1].index = Math.max(-1, Math.floor(cameras.length / 2) - 1);
    advance(slots[1]);
    setInterval(() => {
      for (const s of slots) {
        if (s.index >= 0) {
          const clock=s.root.querySelector(".camera-clock");
          if(clock) clock.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:cameras[s.index].timezone,hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date());
        }
        if (!active()) continue;
        if (s.index < 0) { if (++s.elapsed >= 60) advance(s); continue; }
        if (s.apiUnavailable) { if (Date.now() >= playerApiRetryAfter) mount(s); continue; }
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
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)loadCatalogue();});
  window.addEventListener("hashchange",()=>setTimeout(resumeVisibility,0));
  window.addEventListener("focus",loadCatalogue);
  controls();
  function showDirectory(catalogue) {
    byId("camera-directory").innerHTML=`<p class="small">Public streams, embedded from their original operators. Checked ${safe(catalogue.checked_at||catalogue.cameras[0]?.checked_at||'unknown')}. Offline streams are excluded from rotation. No footage is stored.</p><table><thead><tr><th>Country / city</th><th>View / operator</th><th>Status</th></tr></thead><tbody>${catalogue.cameras.map(c=>`<tr><td>${safe(c.country)}<br><b>${safe(c.city)}</b></td><td><a href="${safe(c.source_url)}" target="_blank" rel="noopener">${safe(c.view)} ↗</a><br>${safe(c.operator)}</td><td>${safe(c.status)}</td></tr>`).join('')}</tbody></table>`;
  }
  function loadCatalogue() {
    if (document.hidden) return;
    fetch(`cameras.json?refresh=${Date.now()}`, {cache:"no-store"})
    .then(r=>{if(!r.ok)throw Error("Camera catalogue unavailable");return r.json();})
    .then(catalogue=>{
      if (!Array.isArray(catalogue.cameras)) throw Error("Invalid camera catalogue");
      showDirectory(catalogue);
      const previous = slots.map(slot=>({slot,camera:cameras[slot.index]}));
      cameras = catalogue.cameras;
      if (!booted) {
        boot();
        return;
      }
      for (const {slot,camera} of previous)
        slot.index = camera ? cameras.findIndex(c=>c.id===camera.id) : -1;
      for (const {slot,camera} of previous) {
        if (!camera) { if (active()) advance(slot); continue; }
        const current = cameras[slot.index];
        if (!current || !availableCamera(current,Date.now())) { slot.generation++; advance(slot); }
        else if (current.video_id!==camera.video_id) { slot.generation++; destroy(slot); mount(slot); }
      }
    }).catch(()=>{if(!booted)wall.innerHTML='<p class="camera-message">Camera directory unavailable. Please refresh.</p>';});
  }
  loadCatalogue();
  setInterval(loadCatalogue,300000);
})();
