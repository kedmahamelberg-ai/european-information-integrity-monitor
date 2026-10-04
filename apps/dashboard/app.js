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
let countries = [],
  world = {},
  live = {},
  data = {},
  demo = false,
  selected = new Set(),
  focus = null;
const mean = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : null),
  fmt = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d)),
  human = (s) =>
    String(s)
      .replaceAll("_", " ")
      .replace(/^./, (x) => x.toUpperCase());
const sum = (a, f) => a.reduce((s, x) => s + f(x), 0),
  unique = (a) => new Set(a).size;
const percent = (n, d) => (d ? `${((100 * n) / d).toFixed(1)}%` : "—");
function project(lon, lat) {
  const x = ((lon + 25) / 95) * 960;
  const my = (v) => Math.log(Math.tan(Math.PI / 4 + (v * Math.PI) / 360));
  return [
    x,
    ((my(72) - my(Math.max(-85, Math.min(85, lat)))) / (my(72) - my(32))) * 650,
  ];
}
function pathGeometry(g) {
  let ps =
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
function filters(v, geo = true, batches = data.batches) {
  const tier = $("#tier").value;
  if (tier !== "all" && v.tier !== tier) return false;
  if (geo && selected.size && !v.countries.some((c) => selected.has(c)))
    return false;
  const p = $("#period").value;
  if (p === "custom") {
    const b = batches.find((x) => x.id === v.batch);
    return (
      b &&
      (!$("#from").value || b.window_end.slice(0, 10) >= $("#from").value) &&
      (!$("#through").value ||
        b.window_start.slice(0, 10) <= $("#through").value)
    );
  }
  const ids = new Set(
    [...batches]
      .sort((a, b) => b.window_start.localeCompare(a.window_start))
      .slice(0, Number(p))
      .map((b) => b.id),
  );
  return ids.has(v.batch);
}
function rows(geo = true) {
  return data.videos.filter((v) => filters(v, geo));
}
function stats(v) {
  const a = v.filter((x) => x.aai != null),
    n = v.length;
  return {
    n,
    a,
    channels: unique(v.map((x) => x.channel_id)),
    sfi: mean(v.map((x) => x.sfi)),
    strong: v.filter(
      (x) => x.othering >= 2 && x.aversion >= 2 && x.moralization >= 2,
    ).length,
    comments: sum(a, (x) => x.comments_analyzed || 0),
    aai: mean(a.map((x) => x.aai)),
    high: a.filter((x) => x.aai >= 0.7).length,
    injection: a.filter((x) => x.injection > 0).length,
  };
}
function collectionOnly() {
  return !demo && !data.videos.length && !!data.collection?.batches?.length;
}
function coverageRows(geo = true) {
  return (data.collection?.coverage || []).filter((x) =>
    filters(x, geo, data.collection.batches),
  );
}
function renderCollection() {
  const panel = $("#collection-status"),
    progress = data.collection;
  panel.hidden = demo || !progress?.batches?.length;
  if (panel.hidden) return;
  const b = progress.batches.at(-1);
  panel.innerHTML = `<strong>Real collection · ${esc(b.id)} · ${esc({ discovery_complete: "Screening news relevance", sampling_complete: "Retrieving sampled comments", comments_complete: "Classifying sampled content", classification_complete: "Calculating research measures", analytics_complete: "Awaiting human validation" }[b.status] || human(b.status))}</strong>
    <p>${b.candidates.toLocaleString()} candidates discovered · ${b.relevance_checked.toLocaleString()} relevance checks completed · ${b.classified.toLocaleString()} videos classified.</p>
    <p class="small">Snapshot exported ${esc(new Date(progress.as_of).toLocaleString())}. Counts update on deployment and after collection completes. Research scores require human validation of 100 videos and 20 comment clusters. <a href="https://github.com/kedmahamelberg-ai/european-information-integrity-monitor/actions/workflows/weekly.yml" target="_blank" rel="noopener">View collection run ↗</a></p>`;
}
function render() {
  const v = rows(),
    s = stats(v);
  $("#data-status").textContent = demo
    ? "DEMONSTRATION · Synthetic cases only. These are not findings about any country or channel."
    : data.message || "Published research observations";
  $(".modebar").classList.toggle("demo", demo);
  $("#demo-toggle").textContent = demo
    ? "Return to live status"
    : "Explore demonstration";
  $("#edition-label").textContent = data.batches.length
    ? data.batches.at(-1).label
    : "Awaiting first verified collection";
  $("#country-label").textContent = selected.size
    ? `${selected.size} countries selected`
    : "All Europe";
  $("#stats").innerHTML = [
    [
      "Mean sectarian framing",
      fmt(s.sfi),
      `${s.n} analyzed videos · 0–4 scale`,
    ],
    [
      "Strong sectarian frames",
      percent(s.strong, s.n),
      `${s.strong} of ${s.n} analyzed videos`,
    ],
    [
      "Experimental mean AAI",
      fmt(s.aai),
      `${s.a.length} comment-eligible videos · 0–1`,
    ],
    [
      "Visible comments analyzed",
      s.comments.toLocaleString(),
      `${s.a.length} eligible videos · retained pool`,
    ],
  ]
    .map(
      (x) =>
        `<div class="stat"><label>${x[0]}</label><strong>${x[1]}</strong><small>${x[2]}</small></div>`,
    )
    .join("");
  renderCollection();
  const collecting = collectionOnly();
  $("#metric").disabled = collecting;
  if (collecting) $("#metric").value = "coverage";
  else if ($("#metric").value === "coverage") $("#metric").value = "sfi";
  if (collecting) {
    const b = data.collection.batches.at(-1);
    $("#data-status").textContent =
      "Real collection data · Candidate coverage is available. Research scores are awaiting analysis and human validation.";
    $("#edition-label").textContent =
      `${b.window_start.slice(0, 10)} – ${b.window_end.slice(0, 10)}`;
    $("#stats").innerHTML = [
      [
        "Candidates discovered",
        sum(coverageRows(), (x) => x.candidates),
        "Current date, country and tier filters",
      ],
      [
        "Relevance checks",
        b.relevance_checked,
        `Latest batch ${b.id} · all candidates`,
      ],
      ["Videos sampled", b.sampled, `Latest batch ${b.id} · all countries`],
      [
        "Videos classified",
        b.classified,
        "Automated processing · not yet validated",
      ],
    ]
      .map(
        ([label, value, note]) =>
          `<div class="stat"><label>${label}</label><strong>${value.toLocaleString()}</strong><small>${note}</small></div>`,
      )
      .join("");
  }
  $(".map-key").hidden = false;
  $(".map-note").textContent = collecting
    ? "Circle area scales with candidate count within the current filters; the largest circle matches the legend maximum. One video can concern several countries. Colour remains neutral until research scores are available."
    : "Marker size: analyzed videos. A country marks content about that country, not the behaviour of its population or government.";
  renderMap();
  renderCountry();
  renderNarratives(v);
  renderEvidence();
  renderValidation();
}
function renderMap() {
  const metric = $("#metric").value;
  $("#map-subtitle").textContent = {
    sfi: "Sectarian Framing Index · 0–4",
    strong: "Strong-frame prevalence · % of analyzed videos",
    narratives: "Narrative-labelled videos · count",
    aai: "Experimental amplification index · 0–1",
    injection: "Coherent off-topic comments · share of retained comments",
  }[metric];
  if (!$("#geography").children.length)
    $("#geography").innerHTML = world.features
      .map(
        (f) =>
          `<path class="land ${countries.some((c) => c.iso2 === f.properties.iso2) ? "monitored" : ""}" data-iso="${esc(f.properties.iso2)}" d="${pathGeometry(f.geometry)}"/>`,
      )
      .join("");
  document
    .querySelectorAll(".land")
    .forEach((x) =>
      x.classList.toggle(
        "selected",
        selected.has(x.dataset.iso) || focus === x.dataset.iso,
      ),
    );
  const collecting = collectionOnly();
  if (collecting)
    $("#map-subtitle").textContent =
      "Discovery coverage · candidate videos · analysis pending";
  const coverage = collecting ? coverageRows(false) : [];
  const all = rows(false);
  const counts = new Map(
    countries.map((c) => [
      c.iso2,
      collecting
        ? sum(
            coverage.filter((x) => x.countries.includes(c.iso2)),
            (x) => x.candidates,
          )
        : all.filter((x) => x.countries.includes(c.iso2)).length,
    ]),
  );
  const maxCount = Math.max(1, ...counts.values());
  const radius = (count) =>
    count ? Math.max(4, 22 * Math.sqrt(count / maxCount)) : 3;
  const legendCounts = [
    ...new Set([
      Math.max(1, Math.round(maxCount / 4)),
      Math.max(1, Math.round(maxCount / 2)),
      maxCount,
    ]),
  ];
  $(".map-key").innerHTML =
    `<span>Circle area · ${collecting ? "candidates" : "analyzed videos"}</span>` +
    legendCounts
      .map(
        (n) =>
          `<span class="size-key"><svg width="48" height="48" aria-hidden="true"><circle cx="24" cy="24" r="${radius(n)}" fill="#80b5b1" stroke="#527f83"/></svg><span>${n}</span></span>`,
      )
      .join("") +
    (collecting
      ? "<span>Colour: not yet scored</span>"
      : '<span class="scale"></span><span>Lower score</span><span>Higher score</span><span class="ring"></span><span>High experimental AAI</span>');
  $("#markers").innerHTML = countries
    .map((c) => {
      const v = all.filter((x) => x.countries.includes(c.iso2)),
        s = stats(v),
        val = {
          sfi: s.sfi == null ? null : s.sfi / 4,
          strong: s.n ? s.strong / s.n : null,
          narratives: s.n
            ? Math.min(
                1,
                v.filter((x) => x.narratives.some((n) => n !== "none_unclear"))
                  .length / 20,
              )
            : null,
          aai: s.aai,
          injection: mean(s.a.map((x) => x.injection)),
        }[metric];
      const [x, y] = project(c.longitude, c.latitude);
      const count = counts.get(c.iso2);
      const unit = collecting ? "candidate videos" : "analyzed videos";
      const r = radius(count);
      const fill =
        collecting && count
          ? "#80b5b1"
          : val == null
            ? "#fafcfd"
            : `hsl(${175 + val * 20} ${40 + val * 20}% ${78 - val * 58}%)`;
      return `<g class="map-marker" tabindex="0" role="button" aria-label="${esc(c.country_name)}, ${count} ${unit}" data-country="${c.iso2}" transform="translate(${x.toFixed(1)},${y.toFixed(1)})"><title>${esc(c.country_name)} · ${count} ${unit} · ${collecting ? "analysis pending" : s.n ? "mean SFI " + fmt(s.sfi) : "no observations"}</title>${s.high ? `<circle r="${r + 5}" fill="none" stroke="#cd8c39" stroke-width="2"/>` : ""}<circle r="${r}" fill="${fill}" stroke="${focus === c.iso2 ? "#142b43" : "#92aab7"}" stroke-width="${focus === c.iso2 ? 3 : 1}"/>${["FR", "GB", "DE", "ES", "IT", "PL", "UA", "RU", "TR", "SE", "NO", "FI", "IS", "KZ"].includes(c.iso2) ? `<text y="${r + 17}" text-anchor="middle">${esc(c.country_name)}</text>` : ""}</g>`;
    })
    .join("");
  document.querySelectorAll("[data-country]").forEach((el) => {
    const go = () => {
      focus = el.dataset.country;
      renderMap();
      renderCountry();
    };
    el.onclick = go;
    el.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        go();
      }
    };
  });
}
function trend(v, key) {
  const bins = [...data.batches].sort((a, b) =>
    a.window_start.localeCompare(b.window_start),
  );
  if (!v.length) return '<p class="small">No observations for a trend.</p>';
  const points = bins
    .map((b, i) => {
      const m = mean(
        v.filter((x) => x.batch === b.id && x[key] != null).map((x) => x[key]),
      );
      return m == null
        ? null
        : [
            10 + (i * 250) / Math.max(1, bins.length - 1),
            43 - (m / (key === "sfi" ? 4 : 1)) * 37,
            b.label,
          ];
    })
    .filter(Boolean);
  return `<svg class="trend" viewBox="0 0 275 55" role="img" aria-label="${esc(key.toUpperCase())} weekly trend">${points.length > 1 ? `<polyline fill="none" stroke="${key === "sfi" ? "#007f79" : "#ba842f"}" stroke-width="2" points="${points.map((p) => p.slice(0, 2).join(",")).join(" ")}"/>` : ""}${points.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#007f79"><title>${esc(p[2])}</title></circle>`).join("")}</svg>`;
}
function renderCountry() {
  if (collectionOnly()) {
    const country = countries.find((c) => c.iso2 === focus);
    const count = sum(
      coverageRows().filter((x) => !focus || x.countries.includes(focus)),
      (x) => x.candidates,
    );
    $("#country-panel").innerHTML =
      `<p class="eyebrow">REAL DISCOVERY DATA</p><h2>${esc(country?.country_name || "All selected countries")}</h2><h3>${count.toLocaleString()} candidate videos</h3><p>Discovered in the current observation window and filters. Candidates are still being screened for news relevance and sampling.</p><p>Framing, narratives and amplification scores are unavailable until analysis and human validation are complete. An unavailable score does not mean zero.</p><a href="#methodology">Read the measurement protocol</a>`;
    return;
  }
  const c = countries.find((c) => c.iso2 === focus),
    v = rows().filter((x) => !focus || x.countries.includes(focus)),
    s = stats(v),
    candidates = (data.candidates || []).filter(
      (x) =>
        filters({ ...x, tier: x.tier || "low" }) &&
        (!focus || x.countries.includes(focus)),
    );
  const dates = [...new Set(v.map((x) => x.batch))]
    .map((id) => data.batches.find((b) => b.id === id))
    .filter(Boolean)
    .sort((a, b) => a.window_start.localeCompare(b.window_start));
  const narrativeCounts = {};
  v.forEach((x) =>
    new Set(x.narratives || []).forEach(
      (n) => (narrativeCounts[n] = (narrativeCounts[n] || 0) + 1),
    ),
  );
  const topNarratives = Object.entries(narrativeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([n, count]) => `${human(n)} (${count}/${v.length})`)
    .join("; ");
  const visibleIds = new Set(v.map((x) => x.id));
  const emergingCandidates = (data.emerging_narratives || []).filter(
    (x) =>
      x.candidate_emerging_narrative &&
      (x.item_ids || []).some((id) => visibleIds.has(id)),
  );
  const emergingText = emergingCandidates.length
    ? `${emergingCandidates.length} candidates awaiting researcher review: ${[...new Set(emergingCandidates.flatMap((x) => x.labels || []))].slice(0, 3).join("; ")}`
    : "No candidates in the current video sample; researcher review required before promotion.";
  $("#country-panel").innerHTML =
    `<p class="eyebrow">${c ? "COUNTRY FOCUS" : "SAMPLE OVERVIEW"}</p><h2>${esc(c?.country_name || "All Europe")}</h2><p class="small">${dates.length ? `${dates[0].window_start.slice(0, 10)} — ${dates.at(-1).window_end.slice(0, 10)}` : "No observation dates yet"}</p><div class="mini-grid">${[
      [candidates.length, "Candidates discovered"],
      [s.n, "Videos analyzed"],
      [s.channels, "Channels"],
      [s.a.length, "Comment-eligible videos"],
      [s.comments, "Visible comments"],
      [s.high, "High AAI videos"],
    ]
      .map((x) => `<div><strong>${x[0]}</strong><span>${x[1]}</span></div>`)
      .join(
        "",
      )}</div><div class="measure-row"><span>Mean SFI</span><strong>${fmt(s.sfi)} / 4</strong></div><div class="measure-row"><span>Strong frames</span><strong>${percent(s.strong, s.n)} <small>(${s.strong}/${s.n})</small></strong></div>${[
      "othering",
      "aversion",
      "moralization",
    ]
      .map((k) => {
        const n = v.filter((x) => x[k] > 0).length;
        return `<div class="dimension"><span>${human(k)}</span><span class="bar"><i style="width:${s.n ? (n / s.n) * 100 : 0}%"></i></span><span>${percent(n, s.n)} (${n}/${s.n})</span></div>`;
      })
      .join(
        "",
      )}<div class="measure-row"><span>Mean experimental AAI</span><strong>${fmt(s.aai)} <small>(n=${s.a.length})</small></strong></div><div class="measure-row"><span>Injection cases</span><strong>${s.injection}/${s.a.length}</strong></div><h3>SFI · weekly mean</h3>${trend(v, "sfi")}<h3>AAI · weekly mean</h3>${trend(v, "aai")}<p class="small">Top narratives: ${esc(topNarratives || "No observations")}</p><p class="small">Targets: ${esc([...new Set(v.flatMap((x) => x.targets || []))].slice(0, 4).join(", ") || "No observations")}</p><p class="small">Emerging narratives: ${esc(emergingText)}</p><button id="country-evidence">Inspect video evidence</button>`;
  $("#country-evidence").onclick = () => {
    if (focus) {
      selected = new Set([focus]);
      syncChecks();
      render();
    }
    location.hash = "evidence";
  };
}
function renderNarratives(v) {
  const counts = {};
  v.forEach((x) =>
    new Set(x.narratives).forEach((n) => (counts[n] = (counts[n] || 0) + 1)),
  );
  $("#narratives").innerHTML =
    Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(
        ([n, k]) =>
          `<div class="narrative-row"><span>${esc(human(n))}</span><span class="bar"><i style="width:${(k / v.length) * 100}%"></i></span><small>${k}/${v.length} videos</small></div>`,
      )
      .join("") ||
    '<p class="empty">Narrative distributions will appear after a batch is processed.</p>';
}
function renderValidation() {
  const q = data.validation || {};
  const a = q.agreement || {};
  const agreementText =
    a.n > 0
      ? `Agreement across ${a.n} reviewed videos: ${Object.entries(
          a.dimension_agreement || {},
        )
          .map(([key, value]) => `${human(key)} ${fmt(value)}`)
          .join(
            ", ",
          )}; strong frames ${fmt(a.strong_agreement)}; narrative Jaccard ${fmt(a.narrative_agreement)}; target Jaccard ${fmt(a.target_agreement)}. These are not chance-corrected reliability estimates.`
      : "Dimension, strong-frame, narrative and target agreement: not yet estimated.";
  $("#validation").innerHTML =
    `<h3>Human review ${q.passed ? "recorded" : "pending"}</h3><p class="small">${q.videos_reviewed || 0} / 100 required videos · ${q.clusters_reviewed || 0} / 20 required comment clusters</p><p class="small">${esc(agreementText)} The SFI adaptation and AAI are unvalidated.</p><a href="#methodology">Read the measurement protocol</a>`;
}
function renderEvidence() {
  const q = $("#evidence-search").value.toLowerCase();
  const v = rows().filter((v) =>
    (v.title + " " + v.channel).toLowerCase().includes(q),
  );
  $("#evidence-table").innerHTML = v.length
    ? `<p class="small">${v.length} video cases in the current filters${demo ? " · SYNTHETIC DEMONSTRATION" : ""}</p><div class="table-wrap"><table><thead><tr><th>Video / channel</th><th>Country</th><th>Tier</th><th>SFI</th><th>AAI</th><th>Visible comments</th></tr></thead><tbody>${v.map((x) => `<tr><td><button class="text-btn" data-video="${esc(x.id)}">${esc(x.title)}</button><small>${esc(x.channel)} · ${x.published_at.slice(0, 10)}</small></td><td>${esc(x.countries.join(", "))}</td><td>${esc(human(x.tier))}</td><td>${fmt(x.sfi)}</td><td>${fmt(x.aai)}</td><td>${x.comments_analyzed || 0}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="empty">No video cases match these filters. Live evidence has not been fabricated. You can inspect synthetic cases using “Explore demonstration”.</p>';
  document
    .querySelectorAll("[data-video]")
    .forEach((b) => (b.onclick = () => openVideo(b.dataset.video)));
}
function openVideo(id) {
  const v = data.videos.find((x) => x.id === id);
  $("#video-detail").innerHTML =
    `<p class="eyebrow">${demo ? "SYNTHETIC DEMONSTRATION" : "VIDEO EVIDENCE"} · ${esc(v.batch)}</p><h2>${esc(v.title)}</h2><p>${esc(v.channel)} · ${v.published_at.slice(0, 10)} · ${esc(v.tier)} institutionalization</p><div class="detail-grid"><section><h3>Sectarian framing</h3><strong>${fmt(v.sfi)} / 4</strong>${["othering", "aversion", "moralization"].map((k) => `<div class="measure-row"><span>${human(k)}</span><strong>${v[k]} / 4</strong></div>`).join("")}<p class="small">Confidence ${fmt(v.confidence)} · Target: ${esc(v.targets.join(", "))}</p><p>${v.narratives.map((n) => `<span class="pill">${esc(human(n))}</span>`).join(" ")}</p><p class="small">${esc(v.rationale || "Structured classification of title and description; no full-video transcript claim.")}</p></section><section><h3>Experimental amplification</h3><strong>${fmt(v.aai)} / 1</strong>${Object.entries(
      v.aai_components || {},
    )
      .map(
        ([k, x]) =>
          `<div class="measure-row"><span>${esc(human(k))}</span><strong>${fmt(x)}</strong></div>`,
      )
      .join(
        "",
      )}<p class="small">Narrative injection: ${percent(v.injected_comments || 0, v.comments_analyzed || 0)} (${v.injected_comments || 0}/${v.comments_analyzed || 0} visible comments).</p></section></div><h3>Representative comment evidence</h3>${(v.excerpts || []).map((x) => `<blockquote class="quote">${esc(x)}</blockquote>`).join("") || '<p class="small">No publishable excerpts retained.</p>'}<p class="small">Indicators cannot establish bots, intent, coordination or actor attribution.</p><div class="provenance">Batch: ${esc(v.batch)} · Model: ${esc(v.model_version)} · Prompt: ${esc(v.prompt_version)} · Taxonomy: ${esc(v.taxonomy_version)}<br>Stratum: ${esc(v.stratum)} · Sampling probability: ${fmt(v.sampling_probability, 4)} · Seed: ${v.sampling_seed}<br>Comment pool: ${v.comment_pool_size || 0} retrieved; ${v.comments_analyzed || 0} analyzed. Source: title + description.</div>${!demo && /^[A-Za-z0-9_-]{11}$/.test(v.video_id || "") ? `<p><a href="https://www.youtube.com/watch?v=${encodeURIComponent(v.video_id)}" target="_blank" rel="noopener">View source on YouTube ↗</a></p>` : ""}`;
  $("#video-dialog").showModal();
}
function demoData() {
  let videos = [],
    candidates = [],
    batches = [];
  for (let w = 0; w < 4; w++) {
    const start = new Date(Date.UTC(2026, 8, 6 + w * 7)),
      end = new Date(+start + 6 * 86400000 + 86399000),
      batch = `fixture-2026-${37 + w}`;
    batches.push({
      id: batch,
      label: `${start.toISOString().slice(0, 10)} – ${end.toISOString().slice(0, 10)}`,
      window_start: start.toISOString(),
      window_end: end.toISOString(),
    });
    [
      "NL",
      "DE",
      "FR",
      "GB",
      "PL",
      "UA",
      "ES",
      "IT",
      "SE",
      "RO",
      "TR",
      "BE",
    ].forEach((co, ci) => {
      for (let j = 0; j < 5; j++) {
        const k = ci * 5 + j + w,
          id = `fixture-${w}-${co}-${j}`,
          o = k % 5,
          a = (k + 2) % 5,
          m = (k + 1) % 5,
          cm = j === 0 ? 0 : 30,
          parts = {
            duplicate_similarity: (k % 7) / 10,
            temporal_burstiness: (k % 6) / 7,
            cross_video_recurrence: (k % 4) / 4,
            topic_divergence: (k % 5) / 5,
            narrative_concentration: 0.25 + (k % 4) / 5,
          },
          aai = cm
            ? Object.entries(parts).reduce(
                (s, [n, x]) =>
                  s +
                  x *
                    {
                      duplicate_similarity: 0.25,
                      temporal_burstiness: 0.2,
                      cross_video_recurrence: 0.2,
                      topic_divergence: 0.2,
                      narrative_concentration: 0.15,
                    }[n],
                0,
              )
            : null,
          v = {
            id,
            video_id: null,
            batch,
            countries: [co],
            title: `Illustrative ${["public-policy debate", "institutional criticism", "security discussion", "economic policy report", "migration debate"][j]} · ${countries.find((c) => c.iso2 === co).country_name}`,
            channel: `Synthetic channel ${ci + 1}.${j + 1}`,
            channel_id: `fixture-channel-${ci}-${j}`,
            published_at: new Date(+start + j * 86400000).toISOString(),
            tier: ["low", "low", "medium", "medium", "high"][j],
            sfi: (o + a + m) / 3,
            othering: o,
            aversion: a,
            moralization: m,
            confidence: 0.62 + (k % 6) * 0.06,
            narratives: [
              [
                "economic_grievance",
                "elite_betrayal",
                "national_sovereignty",
                "security_terrorism",
                "foreign_interference",
              ][j],
            ],
            targets: ["institutions"],
            aai,
            aai_components: cm ? parts : {},
            comments_analyzed: cm,
            comment_pool_size: cm ? 100 : 0,
            injection: cm ? (k % 4) / 10 : null,
            injected_comments: cm ? (k % 4) * 3 : 0,
            model_version: "fixture-only-no-model",
            prompt_version: "sfi-1.0",
            taxonomy_version: "narratives-1.0",
            stratum: `${co}:${["low", "low", "medium", "medium", "high"][j]}`,
            sampling_probability: 0.25,
            sampling_seed: 20261004,
            excerpts: cm
              ? [
                  "Synthetic example: discussion shifts from the policy itself to institutional betrayal. No real comment or person is represented.",
                ]
              : [],
          };
        videos.push(v);
        for (let z = 0; z < 4; z++)
          candidates.push({ ...v, id: `candidate-${id}-${z}` });
      }
    });
  }
  return {
    mode: "fixture",
    batches,
    videos,
    candidates,
    validation: { videos_reviewed: 0, clusters_reviewed: 0 },
  };
}
function syncChecks() {
  document
    .querySelectorAll("#countries-list input")
    .forEach((x) => (x.checked = selected.has(x.value)));
}
function route() {
  const r = ["monitor", "evidence", "methodology"].includes(
    location.hash.slice(1),
  )
    ? location.hash.slice(1)
    : "monitor";
  ["monitor", "evidence", "methodology"].forEach(
    (k) => ($("#" + k).hidden = k !== r),
  );
  document
    .querySelectorAll("nav a")
    .forEach((a) => a.classList.toggle("active", a.hash === "#" + r));
}
async function init() {
  try {
    [countries, world, live] = await Promise.all(
      ["countries.json", "assets/world.json", "data.json"].map((p) =>
        fetch(
          `${p}?v=${encodeURIComponent(document.documentElement.dataset.build || "local")}`,
          { cache: "no-store" },
        ).then((r) => {
          if (!r.ok) throw Error("Data unavailable");
          return r.json();
        }),
      ),
    );
    data = live;
    $("#countries-list").innerHTML = countries
      .map(
        (c) =>
          `<label><input type="checkbox" value="${c.iso2}">${esc(c.country_name)}</label>`,
      )
      .join("");
    $("#countries-list").onchange = (e) => {
      e.target.checked
        ? selected.add(e.target.value)
        : selected.delete(e.target.value);
      render();
    };
    $("#country-search").oninput = (e) =>
      document
        .querySelectorAll("#countries-list label")
        .forEach(
          (x) =>
            (x.hidden = !x.textContent
              .toLowerCase()
              .includes(e.target.value.toLowerCase())),
        );
    $("#clear-countries").onclick = () => {
      selected.clear();
      syncChecks();
      render();
    };
    $("#reset-map").onclick = () => {
      focus = null;
      selected.clear();
      syncChecks();
      render();
    };
    ["period", "tier", "metric", "from", "through"].forEach(
      (id) =>
        ($("#" + id).onchange = () => {
          $("#custom-dates").hidden = $("#period").value !== "custom";
          render();
        }),
    );
    $("#demo-toggle").onclick = () => {
      demo = !demo;
      data = demo ? demoData() : live;
      render();
    };
    $("#evidence-search").oninput = renderEvidence;
    $("#video-dialog .close").onclick = () => $("#video-dialog").close();
    $("#methodology").innerHTML = await fetch("methodology.html").then((r) =>
      r.text(),
    );
    window.onhashchange = route;
    route();
    render();
  } catch (e) {
    $("#data-status").textContent =
      "The monitor data could not be loaded. Please reload to retry.";
    $("#demo-toggle").disabled = true;
    console.error(e);
  }
}
init();

if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  window.addEventListener("pagehide", () => lifecycle.abort(), { once: true });
  Promise.resolve(
    document.modelContext.registerTool(
      {
        name: "inspect_monitor_sample",
        description:
          "Read the currently displayed research sample, data mode and denominators. No attribution is inferred.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
        annotations: { readOnlyHint: true, untrustedContentHint: true },
        execute(input) {
          if (!input || Object.keys(input).length)
            throw Error("Expected an empty object");
          if (!data.videos) throw Error("Monitor is not ready");
          const s = stats(rows());
          return {
            mode: demo ? "synthetic_demonstration" : data.mode,
            videos: s.n,
            mean_sfi: s.sfi,
            mean_experimental_aai: s.aai,
            visible_comments: s.comments,
            validation: data.validation,
          };
        },
      },
      { signal: lifecycle.signal },
    ),
  ).catch(() => {});
}
