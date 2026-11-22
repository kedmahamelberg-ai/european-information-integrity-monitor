(() => {
  const endpoint = "https://jnzibjjejmfochertwco.supabase.co/functions/v1/field-wire";
  const labels = {like:"👍 Like", dislike:"👎 Dislike", love:"❤️ Love", thinking:"🤔 Thinking"};
  const groups = new Map();
  let reader = crypto.randomUUID();
  try {
    reader = localStorage.getItem("esm-wire-reader") || reader;
    localStorage.setItem("esm-wire-reader", reader);
  } catch { /* Keep an in-memory identity when storage is unavailable. */ }

  function button(label) {
    const el = document.createElement("button");
    el.type = "button";
    el.textContent = label;
    return el;
  }

  function paint(group, data) {
    group.data = data;
    for (const ui of group.cards) {
      ui.views.textContent = data.views > 3 ? data.views + " views" : "";
      for (const [key, el] of Object.entries(ui.reactions)) {
        el.setAttribute("aria-pressed", String(data.mine === key));
        el.textContent = labels[key] + (data.reactions[key] ? " " + data.reactions[key] : "");
      }
      ui.comments.replaceChildren(...data.comments.map(value => {
        const p = document.createElement("p");
        p.textContent = value;
        return p;
      }));
    }
  }

  function send(group, action, fields = {}) {
    // Serialize both copies of a dispatch, including automatic view requests.
    const next = group.queue.then(async () => {
      const res = await fetch(endpoint, {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({item_key:group.key, reader, action, ...fields})});
      if (!res.ok) throw Error(res.status === 429 ? "Please wait before commenting again." : "Could not connect. Please retry.");
      paint(group, await res.json());
    });
    group.queue = next.catch(() => {});
    return next;
  }

  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const group = groups.get(entry.target.closest("article").dataset.wire);
      if (group.viewed) continue;
      group.viewed = true;
      send(group,"view").catch(() => { group.viewed = false; });
    }
  }, {threshold:0.5});

  for (const article of document.querySelectorAll("article[data-wire]")) {
    const key = article.dataset.wire;
    if (!groups.has(key)) groups.set(key,{key,cards:[],queue:Promise.resolve()});
    const group = groups.get(key);
    const box = document.createElement("div");
    box.className = "wire-actions";
    const status = document.createElement("small");
    status.setAttribute("role","status");
    const views = document.createElement("small");
    const reactions = {};
    for (const [kind,label] of Object.entries(labels)) {
      const el = button(label);
      el.setAttribute("aria-pressed","false");
      el.onclick = async () => {
        el.disabled = true;
        try { await send(group,"react",{value:group.data?.mine === kind ? "" : kind}); status.textContent = ""; }
        catch(e) { status.textContent = e.message; }
        finally { el.disabled = false; }
      };
      box.append(el);
      reactions[kind] = el;
    }
    const share = button("Share");
    share.onclick = async () => {
      const url = new URL(location.pathname,location.origin);
      url.hash = key;
      url.searchParams.set("source", article.querySelector(".copy a").getAttribute("href"));
      try {
        if (navigator.share) await navigator.share({url:url.href,title:article.querySelector("h2,h3").textContent});
        else { await navigator.clipboard.writeText(url.href); status.textContent = "Link copied."; }
      } catch(e) { if (e.name !== "AbortError") window.prompt("Copy dispatch link",url.href); }
    };
    const toggle = button("Comment");
    const panel = document.createElement("div");
    panel.className = "wire-discussion";
    panel.hidden = true;
    panel.innerHTML = '<form><label>Public comment<textarea required maxlength="500" rows="2"></textarea></label><button>Post comment</button></form><div class="thread"></div>';
    toggle.setAttribute("aria-expanded","false");
    toggle.onclick = () => {
      panel.hidden = !panel.hidden;
      toggle.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) {
        panel.querySelector("textarea").focus();
        send(group,"read").catch(e => { status.textContent = e.message; });
      }
    };
    let pending;
    panel.querySelector("form").onsubmit = async event => {
      event.preventDefault();
      const field = panel.querySelector("textarea"), submit = panel.querySelector("button");
      const value = field.value.trim();
      if (!value || submit.disabled) return;
      if (pending?.value !== value) pending = {value,request_id:crypto.randomUUID()};
      submit.disabled = true;
      try { await send(group,"comment",pending); field.value = ""; pending = null; status.textContent = "Posted."; }
      catch(e) { status.textContent = e.message; }
      finally { submit.disabled = false; }
    };
    box.append(share,toggle,views,status,panel);
    article.querySelector(".copy").append(box);
    group.cards.push({views,reactions,comments:panel.querySelector(".thread")});
    observer.observe(article.querySelector("h2,h3"));
  }

  // A shared dispatch can outlast the rolling bulletin. Keep its source reachable.
  if (location.hash && !document.getElementById(location.hash.slice(1))) {
    const source = new URLSearchParams(location.search).get("source");
    if (source && /^\.\.\/\?record=[A-Za-z0-9_-]+(?:&week=\d{4}-W\d{2})?#(?:government|evidence)$/.test(source)) {
      const link = document.createElement("a");
      link.href = source;
      link.textContent = "This dispatch has left the bulletin. Open its Monitor source ↗";
      document.querySelector(".mast").after(link);
    }
  }
})();
