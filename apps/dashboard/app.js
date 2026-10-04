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
let data = { videos: [], batches: [], collection: {} },
  countries = [];
const roles = ["readiness", "projecting_power", "under_pressure"],
  colors = {
    coverage: "#6bd5d1",
    related: "#d9df9a",
    readiness: "#6bd5d1",
    projecting_power: "#eab879",
    under_pressure: "#e18885",
  },
  icons = { readiness: "🛡️", projecting_power: "⚔️", under_pressure: "🎯" };
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
function rows(geo = true) {
  return data.videos.filter(
    (v) =>
      ($("#batch").value === "all" || v.batch === $("#batch").value) &&
      (!geo ||
        $("#country").value === "all" ||
        v.countries.includes($("#country").value)) &&
      ($("#context").value === "all" ||
        v.label?.context === $("#context").value),
  );
}
function sum(v, k) {
  const known = v.map((x) => x.engagement[k]).filter((x) => x != null);
  return {
    value: known.length ? known.reduce((a, b) => a + b, 0) : null,
    n: known.length,
  };
}
function bar(name, n, d) {
  return `<div class="bar-row"><span>${esc(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${d ? (n / d) * 100 : 0}%"></div></div><span>${n}/${d}</span></div>`;
}
function render() {
  const v = rows(),
    c = data.collection,
    published = v.filter((x) => x.label),
    reviewed = v.filter((x) => x.classification_status === "human_reviewed"),
    related = published.filter((x) => x.label.relevance === "related"),
    country = $("#country").value;
  $("#edition").textContent =
    data.batches.map((b) => b.id).join(" · ") || "Awaiting retained data";
  $("#data-status").textContent =
    `${c.classified_videos || 0} videos AI-coded · ${c.reviewed_videos || 0} human-reviewed. ${c.awaiting_transcript || 0} sampled videos excluded until English transcripts are available. AI labels await completion of the random human audit before publication; published AI labels remain provisional.`;
  $("#stats").innerHTML = [
    [v.length, "Transcript-eligible videos", "Filtered evidence pool"],
    [
      reviewed.length,
      "Human-reviewed videos",
      `${related.length} published security-related`,
    ],
    [
      sum(v, "views").value,
      "Observed views",
      `${sum(v, "views").n}/${v.length} counters available`,
    ],
    [
      v.reduce((n, x) => n + x.classified_comments, 0),
      "AI-coded comments",
      "Agreement and sentiment · private review",
    ],
  ]
    .map(
      ([n, t, d]) =>
        `<div class="stat"><span>${t}</span><b>${num(n)}</b><small>${d}</small></div>`,
    )
    .join("");
  $("#focus-title").textContent =
    country === "all"
      ? "Across the retained sample"
      : countries.find((c) => c.iso2 === country)?.country_name || country;
  $("#roles").innerHTML = roles
    .map((r) => {
      const count = related.filter((x) =>
        x.label.roles.some(
          (z) =>
            z.role === r && (country === "all" || z.entity_code === country),
        ),
      ).length;
      return `<div class="role"><span class="icon" aria-hidden="true">${icons[r]}</span><div>${esc(data.role_labels?.[r] || human(r))}<small>Published portrayal · ${related.length} related videos</small></div><span class="count">${count}</span></div>`;
    })
    .join("");
  $("#quality").innerHTML =
    `<p class="small">${v.length}/${v.length} included sources have saved English text. ${v.filter((x) => x.transcript_truncated).length} AI inputs were truncated; the full saved text remains available to the reviewer.</p><p class="small">${reviewed.length} sources reviewed under the new taxonomy. This is a calibration dataset; model reliability has not been established.</p>`;
  const ex = {
    comparative: "Comparative",
    endorsement: "Expert / testimonial",
    entertainment: "Entertainment / storytelling",
    imagery_visual: "Imagery / visual",
    verbal_imagery: "Verbal imagery · study extension",
    mnemonic_devices: "Mnemonic devices",
  };
  $("#execution").innerHTML =
    Object.entries(ex)
      .map(([k, n]) => {
        const assessed = related.filter((v) =>
          [
            "present",
            "absent_after_watching",
            "not_observed_in_transcript",
          ].includes(v.label.execution[k]),
        );
        return bar(
          n,
          assessed.filter((v) => v.label.execution[k] === "present").length,
          assessed.length,
        );
      })
      .join("") +
    '<p class="small">Present / assessed. “Not observable” is excluded from each denominator.</p>';
  $("#engagement").innerHTML = `<div class="metric-grid">${[
    ["Views", "views"],
    ["Likes", "likes"],
    ["Total comments", "total_comments"],
  ]
    .map(([n, k]) => {
      const s = sum(v, k);
      return `<div><b>${num(s.value)}</b><small>${n} · ${s.n}/${v.length} available</small></div>`;
    })
    .join(
      "",
    )}</div><p class="small">Shares: unavailable through public statistics.</p><p class="small">Video totals are separate from the ${v.reduce((n, x) => n + x.retained_comments, 0)} retained comments. Comment agreement and sentiment are reviewed privately.</p>`;
  renderMap();
  renderEvidence();
}
function renderMap() {
  const all = rows(false),
    metric = $("#metric").value;
  $("#markers").innerHTML = countries
    .map((c) => {
      const relevant = all.filter((v) => v.countries.includes(c.iso2)),
        n =
          metric === "coverage"
            ? relevant.length
            : metric === "related"
              ? relevant.filter((v) => v.label?.relevance === "related").length
              : all.filter((v) =>
                  v.label?.roles.some(
                    (r) => r.entity_code === c.iso2 && r.role === metric,
                  ),
                ).length;
      const [x, y] = project(c.longitude, c.latitude),
        radius = n ? Math.sqrt(n) * 7 + 3 : 2;
      return `<circle cx="${x}" cy="${y}" r="${radius}" fill="${colors[metric]}" class="${n ? "marker" : "marker-empty"}" ${n ? 'tabindex="0" role="button"' : ""} data-country="${c.iso2}" aria-label="${esc(c.country_name)}: ${n} videos"><title>${esc(c.country_name)} · ${n} videos</title></circle>`;
    })
    .join("");
  $("#map-key").innerHTML =
    `<span style="color:${colors[metric]}">● ${esc($("#metric").selectedOptions[0].textContent)}</span><span>○ No qualifying observations</span><span>Size = video count, not threat severity</span>`;
}
function renderEvidence() {
  const q = $("#search").value.toLowerCase(),
    v = rows().filter((v) =>
      `${v.title} ${v.channel}`.toLowerCase().includes(q),
    );
  $("#evidence-table").innerHTML =
    `<p class="small">${v.length} sources · filters from the monitor apply here.</p><div class="evidence-grid">${
      v
        .map((x) => {
          const m = x.engagement;
          return `<article class="case"><span class="tag">${esc(human(x.classification_status))}</span><span class="tag">Original language: ${esc(x.original_language)}</span><h2>${esc(x.title)}</h2><p>${esc(x.channel)} · ${esc(x.batch)}</p>${x.label ? `<p>${esc(human(x.label.relevance))} · ${esc(human(x.label.context))}</p>${x.label.roles.map((r) => `<span class="tag">${icons[r.role]} ${esc(r.entity)} · ${esc(data.role_labels[r.role])}</span>`).join("")}` : "<p>Substantive labels await human review.</p>"}<div class="metric-grid"><div><b>${num(m.views)}</b><small>Views</small></div><div><b>${num(m.likes)}</b><small>Likes</small></div><div><b>${num(m.total_comments)}</b><small>Total comments</small></div></div><p>Likes / 1,000 views: ${m.likes_per_1000_views == null ? "Unavailable" : m.likes_per_1000_views.toFixed(1)} · Comments / 1,000 views: ${m.comments_per_1000_views == null ? "Unavailable" : m.comments_per_1000_views.toFixed(1)}</p><p class="small">Captured ${esc(m.captured_at || "unknown")} · ${m.age_hours_at_capture == null ? "Age unknown" : m.age_hours_at_capture.toFixed(1) + " hours since publication"} · ${x.retained_comments} comments retained · Shares unavailable.</p><a href="https://www.youtube.com/watch?v=${encodeURIComponent(x.id)}" target="_blank" rel="noopener">Watch source ↗</a></article>`;
        })
        .join("") ||
      '<p class="empty">No eligible sources match these filters.</p>'
    }</div>`;
}
function route() {
  const r = ["evidence", "methodology"].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : "monitor";
  for (const id of ["monitor", "evidence", "methodology"])
    $("#" + id).hidden = id !== r;
  document
    .querySelectorAll("nav a")
    .forEach((a) =>
      a.setAttribute("aria-current", a.hash === "#" + r ? "page" : "false"),
    );
}
async function init() {
  try {
    const rev = document.documentElement.dataset.build || Date.now();
    const results = await Promise.all(
      [
        "data.json",
        "countries.json",
        "assets/world.json",
        "methodology.html",
      ].map(async (p) => {
        const r = await fetch(`${p}?v=${rev}`);
        if (!r.ok) throw Error("Load failed");
        return p.endsWith(".html") ? r.text() : r.json();
      }),
    );
    [data, countries] = results;
    countries = countries.countries || countries;
    $("#methodology").innerHTML = results[3];
    $("#geography").innerHTML = results[2].features
      .map((f) => `<path d="${geometry(f.geometry)}"/>`)
      .join("");
    $("#country").insertAdjacentHTML(
      "beforeend",
      countries
        .map((c) => `<option value="${c.iso2}">${esc(c.country_name)}</option>`)
        .join(""),
    );
    $("#batch").insertAdjacentHTML(
      "beforeend",
      data.batches
        .map((b) => `<option value="${esc(b.id)}">${esc(b.id)}</option>`)
        .join(""),
    );
    render();
    route();
  } catch {
    $("#data-status").textContent =
      "The data snapshot could not be loaded. Please refresh or check the repository’s publishing status.";
  }
}
for (const id of ["batch", "country", "context", "metric"])
  $("#" + id).onchange = render;
$("#search").oninput = renderEvidence;
$("#reset").onclick = () => {
  for (const id of ["batch", "country", "context"]) $("#" + id).value = "all";
  $("#metric").value = "coverage";
  render();
};
$("#markers").onclick = (e) => {
  if (e.target.dataset.country) {
    $("#country").value = e.target.dataset.country;
    render();
  }
};
$("#markers").onkeydown = (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    e.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }
};
window.addEventListener("hashchange", route);
init();
