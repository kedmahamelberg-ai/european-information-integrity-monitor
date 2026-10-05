"use strict";
const P = JSON.parse(document.querySelector("#packet").textContent),
  $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const human = (s) =>
  ({
    supports: "Aligned · supports the main message",
    opposes: "Not aligned · opposes the main message",
    no_position: "No position on the main message",
    main_message: "Main message / claim",
    video_target: "Person, policy or topic targeted by the video",
    speaker: "Speaker / speaking skill only",
    presentation: "Visuals, music, editing or channel only",
    present: "Yes · present (1)",
    absent_after_watching: "No · absent after watching (0)",
    not_observed_in_transcript:
      "Not observed in transcript · absence unverified",
    not_observable: "Cannot assess from available evidence",
    not_applicable: "Not applicable",
  })[s] ||
  String(s)
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
const names = {
  relevance: "Study relevance",
  topics: "Topics",
  roles: "Military / security portrayal",
  alignment: "2. Agreement with the main message",
  response_focus: "1. What does this comment evaluate?",
  "reference:speaker": "Speaker / narrator",
  "reference:summary": "Main message (attributed proposition)",
  "reference:target": "Target of the main message",
  "reference:speaker_sentiment": "Speaker sentiment toward that target",
  stance_target: "Proposition the comment agrees or disagrees with",
  sentiment: "3. Comment sentiment",
  sentiment_target: "Who or what receives that sentiment?",
  comparative: "Comparative",
  endorsement: "Expert / testimonial endorsement",
  entertainment: "Entertainment / storytelling",
  imagery_visual: "Imagery / visual",
  mnemonic_devices: "Mnemonic devices",
};
const key = "eiim-hybrid-review-v1";
let state = {};
try {
  state = JSON.parse(localStorage.getItem(key) || "{}");
} catch {}
let selected = P.items[0]?.id;
$("#reviewer").value = state.reviewer || "";
function save() {
  state.reviewer = $("#reviewer").value;
  localStorage.setItem(key, JSON.stringify(state));
  summary();
}
function say(s) {
  $("#message").textContent = s;
  document
    .querySelectorAll(".review-message")
    .forEach((x) => (x.textContent = s));
}
function itemState(i, cid = "") {
  const k = i.id + (cid ? ":comment:" + cid : "");
  if (!state[k] || state[k].hash !== i.hash)
    state[k] = {
      hash: i.hash,
      decisions: {},
      values: {},
      basis: "",
      confirmed: false,
    };
  return state[k];
}
function expected(i, c) {
  return c
    ? Object.fromEntries(
        [
          "response_focus",
          "alignment",
          "stance_target",
          "sentiment",
          "sentiment_target",
        ].map((k) => [k, c.ai[k]]),
      )
    : i.model_values;
}
function summary() {
  let done = 0,
    comments = 0;
  for (const i of P.items) {
    done += !!itemState(i).confirmed;
    for (const c of i.comments)
      comments += !!itemState(i, c.comment_id).confirmed;
  }
  $("#summary").textContent =
    `${P.items.length} transcript-eligible videos · ${P.plan.target} assigned for review · ${done} videos and ${comments} comments confirmed. Calibration target: 30 where available; later batches: 3%, minimum 5.`;
}
function options(values, current) {
  return values
    .map(
      (v) =>
        `<option value="${esc(v)}" ${v === current ? "selected" : ""}>${esc(human(v))}</option>`,
    )
    .join("");
}
function describe(k, v) {
  if (k === "roles")
    return v.length
      ? v
          .map((r) => `${r.entity} · ${P.taxonomy.role_labels[r.role]}`)
          .join("\n")
      : "No evidenced security role";
  if (k === "topics")
    return v.length
      ? v.map((x) => P.taxonomy.topic_labels[x] || human(x)).join(" · ")
      : "None";
  return human(v);
}
function editor(k, v) {
  if (k === "topics")
    return `<div class="domain-editor">${P.taxonomy.topics.map((d) => `<label><input type="checkbox" value="${d}" ${v.includes(d) ? "checked" : ""}>${esc(P.taxonomy.topic_labels[d] || human(d))}</label>`).join("")}</div>`;
  if (k === "roles")
    return `<div class="roles">${v.map((r) => roleEditor(r)).join("")}</div><button type="button" data-add-role>Add entity role</button>`;
  const cat = k.startsWith("execution:")
    ? "execution_status"
    : k === "reference:speaker_sentiment"
      ? "sentiment"
      : k;
  let vals = P.taxonomy[cat];
  if (cat === "execution_status") vals = [...vals, "absent_after_watching"];
  if (vals)
    return `<label>Your corrected label<select data-value>${options(vals, v)}</select></label>`;
  return `<label>Your corrected label<textarea data-value>${esc(v)}</textarea></label>`;
}
function roleEditor(
  r = { entity: "", entity_code: "OTHER", role: "readiness" },
) {
  return `<div class="role-editor"><label>Entity<input data-role="entity" value="${esc(r.entity)}"></label><label>Code<input data-role="entity_code" value="${esc(r.entity_code)}" title="European ISO2 code, EU, or OTHER"></label><label>Portrayed role<select data-role="role">${P.taxonomy.roles.map((v) => `<option value="${v}" ${v === r.role ? "selected" : ""}>${esc(P.taxonomy.role_labels[v])}</option>`).join("")}</select></label><button type="button" data-remove-role>Remove</button></div>`;
}
function field(i, k, v, c) {
  const s = itemState(i, c?.comment_id),
    decision = s.decisions[k],
    value = s.values[k] ?? v;
  let explanation = "";
  if (k === "roles")
    explanation = i.label.roles
      .map((r) => `${r.rationale} Evidence: “${r.evidence.quote}”`)
      .join(" · ");
  if (k.startsWith("execution:")) {
    const e = i.label.execution.find((e) => e.category === k.split(":")[1]);
    explanation =
      (e?.rationale || "") +
      (e?.evidence.quote ? ` Evidence: “${e.evidence.quote}”` : "");
  }
  return `<section class="field" data-field="${esc(k)}" data-comment="${esc(c?.comment_id || "")}"><h4>${esc(names[k] || names[k.split(":")[1]])}</h4><div class="model">AI: ${esc(describe(k, v))}</div>${explanation ? `<p class="meta">${esc(explanation)}</p>` : ""}<div class="buttons"><button data-decision="agree" aria-pressed="${decision === "agree"}">Agree</button><button data-decision="disagree" aria-pressed="${decision === "disagree"}">Disagree / correct</button></div><div class="editor" ${decision === "disagree" ? "" : "hidden"}>${editor(k, value)}</div></section>`;
}
function list() {
  const q = $("#search").value.toLowerCase(),
    w = $("#workload").value;
  const items = P.items.filter(
    (i) =>
      (w !== "assigned" || i.review_assignment.selected) &&
      (w !== "related" || i.label.relevance === "related") &&
      `${i.title} ${i.channel}`.toLowerCase().includes(q),
  );
  if (!items.some((i) => i.id === selected)) selected = items[0]?.id;
  $("#list").innerHTML =
    items
      .map(
        (i) =>
          `<button data-item="${esc(i.id)}" aria-pressed="${i.id === selected}">${esc(i.title)}<small>${esc(human(i.label.relevance))} · ${esc(i.source_language)}${itemState(i).confirmed ? " · Confirmed" : ""}</small></button>`,
      )
      .join("") || '<p class="empty">No videos match.</p>';
  render();
}
function render() {
  const i = P.items.find((x) => x.id === selected);
  if (!i) {
    $("#case").innerHTML =
      '<p class="empty">No matching transcript-eligible video.</p>';
    return;
  }
  const s = itemState(i),
    ref = {
      ...i.label.content_reference,
      ...Object.fromEntries(
        Object.entries(s.values)
          .filter(([k]) => k.startsWith("reference:"))
          .map(([k, v]) => [k.split(":")[1], v]),
      ),
    },
    m = i.engagement,
    n = (v) => (v == null ? "Unavailable" : Number(v).toLocaleString());
  $("#case").innerHTML =
    `<section class="card"><p class="eyebrow">${esc(i.batch)} · ${esc(i.model)}</p><h2>${esc(i.title)}</h2><p class="meta">${esc(i.channel)} · Country discussed: ${esc((i.countries || []).map((c) => c.name).join(", ") || "Unidentified")} · Spoken language: ${esc(i.source_language)} · ${esc(human(i.caption_status || "saved English transcript"))}</p><iframe class="video" src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(i.video_id)}?cc_load_policy=1&cc_lang_pref=en" title="${esc(i.title)}" allowfullscreen></iframe><a href="https://www.youtube.com/watch?v=${encodeURIComponent(i.video_id)}" target="_blank" rel="noopener">Watch on YouTube ↗</a><div class="metrics">${[
      ["Views", m.views],
      ["Likes", m.likes],
      ["Total comments", m.total_comments],
      ["Shares", m.shares],
    ]
      .map(([k, v]) => `<div><b>${n(v)}</b><small>${k}</small></div>`)
      .join(
        "",
      )}</div><p class="meta">Counters captured: ${esc(m.captured_at || "unknown")} · ${i.comments.length} comments retained here. Shares are not publicly available.</p><p class="meta">Country is identified from title/description; spoken language alone does not establish country or audience location.</p><details><summary>Thumbnail and sound evidence limits</summary>${i.media_evidence?.thumbnail_url && /^https:\/\//.test(i.media_evidence.thumbnail_url) ? `<img class="thumbnail" src="${esc(i.media_evidence.thumbnail_url)}" alt="Publisher thumbnail; packaging evidence only">` : "<p>No retained thumbnail URL.</p>"}<p>Caption music cues: ${i.media_evidence?.music_caption_cues?.length || 0}. No audio analysis was performed. No cue does not mean no music. Background music alone is not a mnemonic; a thumbnail alone cannot establish storytelling.</p></details><details><summary>Original title and description</summary><p>${esc(i.title)}</p><p>${esc(i.description)}</p></details><details><summary>Read English transcript${i.transcript_truncated ? " · AI input truncated" : ""}</summary><div class="transcript">${i.transcript.map((t) => `<p><a href="https://www.youtube.com/watch?v=${encodeURIComponent(i.video_id)}&t=${Math.floor(t.start)}s" target="_blank" rel="noopener">${Math.floor(t.start / 60)}:${String(Math.floor(t.start % 60)).padStart(2, "0")}</a> ${esc(t.text)}</p>`).join("")}</div></details><p>${esc(i.label.rationale)}</p><blockquote>${esc(i.label.evidence.quote)}</blockquote><p class="meta">Portrayal status: ${esc(human(i.label.evidence_status))}. A report or allegation is not independent verification.</p></section>${(
      i.prior_reviews || []
    )
      .map(
        (r) =>
          `<details class="card"><summary>Your previous review · ${esc(r.version)}</summary><p>Preserved as calibration feedback. The new AI result still needs an explicit decision.</p>${Object.entries(
            r.human_label,
          )
            .filter(
              ([k]) =>
                ![
                  "stance",
                  "context",
                  "domains",
                  "execution:verbal_imagery",
                ].includes(k),
            )
            .map(
              ([k, v]) =>
                `<p><b>${esc(names[k] || names[k.split(":")[1]])}:</b> ${esc(describe(k, v))}</p>`,
            )
            .join("")}</details>`,
      )
      .join(
        "",
      )}<h3>Review the video classifications and message reference</h3><p class="notice">Changing relevance may require new topics and reassessment of all five execution labels. Your draft saves automatically, including before confirmation.</p>${Object.entries(
      i.model_values,
    )
      .map(([k, v]) => field(i, k, v))
      .join(
        "",
      )}<section class="card"><label>Evidence you used<select id="basis"><option value="">Select evidence basis</option>${options(["english_transcript", "watched_video"], s.basis)}</select></label><label>Notes<textarea id="notes">${esc(s.notes || "")}</textarea></label><p class="review-message" role="status"></p><p><button class="confirm" id="confirm-video">Confirm video review</button> <span class="confirmed">${s.confirmed ? "Confirmed" : ""}</span></p></section><h3>Comments · ${i.comments.length} retained</h3><section class="notice"><b>Reference for every comment</b><p>Speaker: ${esc(ref.speaker)}<br>Main message: ${esc(ref.summary)}<br>Target: ${esc(ref.target)}<br>Speaker sentiment toward target: ${esc(human(ref.speaker_sentiment))}</p><p>First identify what the comment evaluates; then agreement with the main message; then sentiment toward its named object. Praise for speaking skill or editing alone is not message agreement. A negative comment about a criticized target can support the speaker’s negative message. This reference includes your draft corrections.</p></section>${i.comments
      .filter((c) => c.ai)
      .map(
        (c) =>
          `<section class="comment" data-cid="${esc(c.comment_id)}"><div class="bilingual"><div><b>Original · ${esc(c.translation.translation_detected_language || "unverified")}</b><p>${esc(c.text_original)}</p></div><div><b>English · ${esc(human(c.translation.translation_status || "unavailable"))}</b><p>${esc(c.translation.text_english || "English translation unavailable — do not confirm")}</p></div></div>${(
            c.prior_reviews || []
          )
            .map(
              (r) =>
                `<details><summary>Your previous comment review · ${esc(r.version)}</summary>${Object.entries(
                  r.human_label,
                )
                  .map(
                    ([k, v]) =>
                      `<p>${esc(names[k] || k)}: ${esc(human(v))}</p>`,
                  )
                  .join("")}</details>`,
            )
            .join(
              "",
            )}<p class="meta">${esc(c.ai.rationale)}</p>${["response_focus", "alignment", "stance_target", "sentiment", "sentiment_target"].map((k) => field(i, k, c.ai[k], c)).join("")}<p class="review-message" role="status"></p><button class="confirm" data-confirm-comment="${esc(c.comment_id)}">Confirm comment review</button> <span class="confirmed">${itemState(i, c.comment_id).confirmed ? "Confirmed" : ""}</span></section>`,
      )
      .join("")}`;
}
function capture(f, i) {
  const k = f.dataset.field,
    c = i.comments.find((c) => c.comment_id === f.dataset.comment),
    s = itemState(i, c?.comment_id);
  if (s.decisions[k] !== "disagree") return;
  const e = f.querySelector(".editor");
  let v;
  if (k === "topics")
    v = [...e.querySelectorAll("input:checked")].map((x) => x.value);
  else if (k === "roles")
    v = [...e.querySelectorAll(".role-editor")].map((r) =>
      Object.fromEntries(
        [...r.querySelectorAll("[data-role]")].map((x) => [
          x.dataset.role,
          x.value,
        ]),
      ),
    );
  else v = e.querySelector("[data-value]").value;
  if (JSON.stringify(s.values[k]) === JSON.stringify(v)) return;
  s.values[k] = v;
  s.confirmed = false;
  save();
}
function check(i, c) {
  const s = itemState(i, c?.comment_id),
    e = expected(i, c);
  if (!$("#reviewer").value.trim()) return "Enter your reviewer name.";
  if (
    !Object.keys(e).every((k) => s.decisions[k] && Object.hasOwn(s.values, k))
  )
    return (
      "Still needs your decision: " +
      Object.keys(e)
        .filter((k) => !s.decisions[k] || !Object.hasOwn(s.values, k))
        .map((k) => names[k] || names[k.split(":")[1]])
        .join(", ") +
      ". Your draft is saved."
    );
  if (!c) {
    if (!s.basis) return "Select the evidence you used.";
    const h = s.values;
    if (
      ["speaker", "summary", "target", "speaker_sentiment"].some(
        (k) => !String(h["reference:" + k] || "").trim(),
      )
    )
      return "Complete the speaker, main message, target and speaker sentiment reference.";
    if (h.relevance !== "related" && (h.topics.length || h.roles.length))
      return "Clear study topics and roles for an out-of-scope/unclear video.";
    if (h.relevance === "related" && !h.topics.length)
      return "Choose at least one topic for a relevant video.";
    for (const k of P.taxonomy.execution) {
      let v = h["execution:" + k];
      if ((v === "not_applicable") === (h.relevance === "related"))
        return `${names[k]} still has an incompatible label. For a related video, use Yes, No after watching, or an uncertainty option; for an out-of-scope video use Not applicable. Your draft is saved.`;
      if (v === "absent_after_watching" && s.basis !== "watched_video")
        return "Watch the video before making an audiovisual judgment.";
    }
    if (h.roles.some((r) => !r.entity.trim() || !r.entity_code.trim()))
      return "Enter each role’s entity and country code.";
  } else if (!c.translation.text_english)
    return "English translation is missing; do not confirm yet.";
  else if (
    ["speaker", "presentation", "unrelated"].includes(
      s.values.response_focus,
    ) &&
    ["supports", "opposes", "mixed"].includes(s.values.alignment)
  )
    return "Speaker or presentation praise alone is not agreement with the main message. Choose No position, or Mixed focus if the comment also addresses the message.";
  else if (
    ["supports", "opposes", "mixed"].includes(s.values.alignment) &&
    !s.values.stance_target.trim()
  )
    return "Specify the video content this comment supports or opposes.";
  return "";
}
$("#case").addEventListener("click", (e) => {
  const i = P.items.find((x) => x.id === selected),
    button = e.target.closest("button");
  if (!button) return;
  const f = button.closest("[data-field]");
  if (button.dataset.decision) {
    const k = f.dataset.field,
      c = i.comments.find((c) => c.comment_id === f.dataset.comment),
      s = itemState(i, c?.comment_id);
    s.decisions[k] = button.dataset.decision;
    if (button.dataset.decision === "agree" || !Object.hasOwn(s.values, k))
      s.values[k] = structuredClone(expected(i, c)[k]);
    s.confirmed = false;
    save();
    f.outerHTML = field(i, k, expected(i, c)[k], c);
  } else if (button.hasAttribute("data-add-role")) {
    f.querySelector(".roles").insertAdjacentHTML("beforeend", roleEditor());
    capture(f, i);
  } else if (button.hasAttribute("data-remove-role")) {
    button.closest(".role-editor").remove();
    capture(f, i);
  } else if (button.id === "confirm-video" || button.dataset.confirmComment) {
    const c = i.comments.find(
        (c) => c.comment_id === button.dataset.confirmComment,
      ),
      error = (() => {
        document.querySelectorAll("[data-field]").forEach((f) => capture(f, i));
        return check(i, c);
      })();
    if (error) {
      say(error);
      return;
    }
    const s = itemState(i, c?.comment_id);
    s.confirmed = true;
    s.reviewed_at = new Date().toISOString();
    s.reviewer = $("#reviewer").value.trim();
    if (c) s.basis = "english_transcript";
    save();
    say("Review confirmed locally. Export to save a transferable copy.");
    render();
  }
});
function onEdit(e) {
  const i = P.items.find((x) => x.id === selected);
  if (e.target.id === "basis" || e.target.id === "notes") {
    const s = itemState(i);
    s[e.target.id] = e.target.value;
    s.confirmed = false;
    save();
  }
  const f = e.target.closest("[data-field]");
  if (f) capture(f, i);
  if (f?.dataset.field.startsWith("reference:") && e.type === "change")
    render();
}
$("#case").addEventListener("input", onEdit);
$("#case").addEventListener("change", onEdit);
$("#list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-item]");
  if (b) {
    selected = b.dataset.item;
    list();
  }
});
$("#workload").onchange = list;
$("#search").oninput = list;
$("#reviewer").oninput = save;
$("#export").onclick = () => {
  const out = [];
  for (const i of P.items) {
    for (const cid of ["", ...i.comments.map((c) => c.comment_id)]) {
      const s = itemState(i, cid);
      if (s.confirmed)
        out.push({
          version: P.version,
          item_type: cid ? "hybrid_comment" : "hybrid_video",
          queue_record_id: i.id,
          queue_hash: i.hash,
          comment_id: cid || null,
          reviewer: s.reviewer,
          reviewed_at: s.reviewed_at,
          basis: s.basis,
          notes: s.notes || "",
          human_label: s.values,
          decisions: s.decisions,
        });
    }
  }
  if (!out.length) {
    say("No confirmed reviews to export.");
    return;
  }
  const a = document.createElement("a"),
    url = URL.createObjectURL(
      new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }),
    );
  a.href = url;
  a.download = `eiim-hybrid-confirmed-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  say(`Exported ${out.length} confirmed reviews.`);
};
summary();
list();
