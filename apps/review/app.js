"use strict";
let packet = JSON.parse(document.getElementById("review-payload").textContent);
const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const human = (s) =>
  String(s)
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
const storageKey = "eiim-private-review-v1";
let saved = {},
  currentId = null,
  draft = null,
  storageOK = true;
try {
  saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
} catch {
  storageOK = false;
}
$("#reviewer").value = saved.reviewer || "";
const decisions = () => saved.items || (saved.items = {});
function current() {
  return packet.items.find((x) => x.queue_record_id === currentId);
}
function stateFor(item) {
  const s = decisions()[item.queue_record_id];
  return s?.queue_hash === item.queue_hash
    ? s
    : {
        status: "pending",
        queue_hash: item.queue_hash,
        decisions: {},
        human_label: {},
        notes: "",
      };
}
function persist() {
  saved.reviewer = $("#reviewer").value;
  try {
    localStorage.setItem(storageKey, JSON.stringify(saved));
    storageOK = true;
  } catch {
    storageOK = false;
    notice(
      "Browser storage is unavailable. Keep this page open and download your reviews before leaving.",
      true,
    );
  }
}
function notice(message, error = false) {
  $("#notice").textContent = message;
  $("#notice").classList.toggle("error", error);
}
function filtered() {
  const kind = $("#kind").value,
    status = $("#status").value,
    q = $("#search").value.toLowerCase();
  return packet.items.filter(
    (x) =>
      (kind === "all" || x.item_type === kind) &&
      (status === "all" || stateFor(x).status === status) &&
      ($("#assessment").value === "all" ||
        x.model_label.assessment_status === $("#assessment").value) &&
      JSON.stringify([
        x.source_observation?.title,
        x.source_observation?.channel,
        x.source_observation?.video_id,
        x.model_label?.countries,
      ])
        .toLowerCase()
        .includes(q),
  );
}
function summary() {
  const complete = packet.items.filter(
    (x) => stateFor(x).status === "complete",
  );
  const video = complete.filter(
      (x) =>
        x.item_type === "video" &&
        ["othering", "aversion", "moralization"].every(
          (k) =>
            Number.isInteger(x.ai_values[k]) &&
            Number.isInteger(stateFor(x).human_label[k]),
        ),
    ).length,
    clusters = complete.filter((x) => x.item_type === "comment_cluster").length;
  $("#summary").innerHTML = [
    [video + " / 100", "Videos confirmed"],
    [clusters + " / 20", "Comment clusters confirmed"],
    [packet.items.length - complete.length, "Items not confirmed"],
    [packet.items.length, "Available review items"],
  ]
    .map(([n, t]) => `<div><strong>${n}</strong><span>${t}</span></div>`)
    .join("");
  $("#export").disabled = !complete.length;
}
function renderQueue() {
  summary();
  const items = filtered();
  $("#queue").innerHTML = items
    .map(
      (x) =>
        `<button data-item="${esc(x.queue_record_id)}" class="${x.queue_record_id === currentId ? "active" : ""}">${esc(x.source_observation?.title || x.item_id)}<small>${esc(human(x.item_type))} · ${esc(human(stateFor(x).status))}</small></button>`,
    )
    .join("");
  $("#queue")
    .querySelectorAll("button")
    .forEach((b) => (b.onclick = () => selectItem(b.dataset.item)));
  $("#workspace").hidden = !items.length;
  $("#empty").hidden = !!items.length;
  if (!items.length) {
    const b = packet.progress?.batches?.at(-1);
    $("#empty").innerHTML = packet.items.length
      ? "<h2>No matching items</h2><p>Change the queue filters to show your review items.</p>"
      : `<h2>Waiting for real classifications</h2><p>The collector is ${esc(human(b?.status || "processing the first batch"))}. ${b?.relevance_checked || 0} relevance checks are saved; ${b?.classified || 0} videos are classified.</p><p>Your review controls will appear when classified items are added to this private packet. Nothing here has been pre-approved.</p>`;
  }
}
function selectItem(id) {
  currentId = id;
  draft = structuredClone(stateFor(current()));
  renderQueue();
  renderItem();
}
function showValue(value) {
  if (value === null)
    return "Not scored — insufficient evidence / out of scope";
  return Array.isArray(value)
    ? value.join(", ") || "None"
    : typeof value === "boolean"
      ? value
        ? "Yes"
        : "No"
      : String(value);
}
function renderItem() {
  const item = current();
  if (!item) return;
  const source = item.source_observation || {},
    model = item.model_label;
  $("#title").textContent = source.title || item.item_id;
  $("#recorded-title").textContent = source.title || "Source title unavailable";
  $("#description").textContent =
    source.description || "No retained description.";
  $("#source-meta").textContent = [
    source.channel,
    source.published_at?.slice(0, 10),
  ]
    .filter(Boolean)
    .join(" · ");
  $("#item-meta").textContent = [
    human(item.item_type),
    item.batch,
    model.tier,
    model.language,
  ]
    .filter(Boolean)
    .join(" · ");
  const id = source.video_id;
  const valid = /^[A-Za-z0-9_-]{11}$/.test(id || "");
  $("#player").innerHTML = valid
    ? `<iframe title="YouTube video for human review" src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?cc_lang_pref=en&cc_load_policy=1" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>`
    : '<p class="help">No playable source ID is available for this item.</p>';
  $("#source-link").innerHTML = valid
    ? `<a target="_blank" rel="noopener" href="https://www.youtube.com/watch?v=${encodeURIComponent(id)}">Open video on YouTube ↗</a><span class="help"> · Use this if the uploader blocks embedding.</span>`
    : "";
  const access = item.english_access || {};
  $("#language-access").textContent =
    `Original audio language: ${access.original_language || "unknown"} (${human(access.language_basis || "unknown")}). English access: ${human(access.status || "unverified")}. Language is an observed content attribute, not proof of the intended audience.`;
  const transcript = access.transcript_english || [];
  $("#evidence-scope").textContent = model.evidence_scope
    ? `AI evidence: ${human(model.evidence_scope)}. Assessment: ${human(model.assessment_status)}. ${model.transcript_truncated ? "Only part of the transcript was supplied. " : ""}${model.evidence_scope === "metadata_only" ? "These labels do not assess the spoken video. " : "Captions may contain transcription/translation errors. "}Candidate classifier awaiting validation; original labels are retained.`
    : "AI evidence: title and description only. These labels do not assess the spoken video. Record whether your judgment uses additional video evidence.";
  $("#transcript").innerHTML = transcript.length
    ? `<details open><summary>English transcript · ${esc(human(access.caption_translation === "youtube_auto_translation" ? "YouTube auto translation" : access.caption_is_generated ? "automatic captions" : "caption track"))}</summary><p class="help">Original caption language: ${esc(access.caption_source_language)}. ${model.evidence_scope === "metadata_and_english_transcript" ? "The revised AI classification includes this transcript" + (model.transcript_truncated ? " (partially)" : "") : "The baseline AI classification did not use this transcript"}.</p><div class="transcript-text">${transcript.map((s) => `<p><small>${Math.floor(s.start / 60)}:${String(Math.floor(s.start % 60)).padStart(2, "0")}</small> ${esc(s.text)}</p>`).join("")}</div></details>`
    : "";
  $("#comments").innerHTML =
    item.item_type === "comment_cluster"
      ? "<h3>Comments in this cluster</h3>" +
        item.source_comments
          .map(
            (c) =>
              `<blockquote><b>English · ${esc(human(c.translation_status || "translation unavailable"))}</b><p>${esc(c.text_english || "Not available — do not label this comment yet.")}</p><details><summary>Original · ${esc(c.original_language || "und")}</summary><p>${esc(c.text)}</p></details><small>${esc(c.published_at || "")}</small></blockquote>`,
          )
          .join("")
      : "";
  $("#model-context").innerHTML =
    `<b>AI rationale</b><p>${esc(model.short_rationale || model.rationale || "Review the cluster evidence and proposed labels below.")}</p><span>Confidence: ${model.confidence == null ? "not supplied" : esc(model.confidence)} · Version: ${esc(item.classifier_version)}</span>` +
    (model.baseline_scores
      ? `<p class="help">Previous AI (O / A / M): ${esc([model.baseline_scores.othering, model.baseline_scores.aversion, model.baseline_scores.moralization].join(" / "))}. Kept for comparison.</p>`
      : "") +
    (item.previous_reviews || [])
      .map(
        (r) =>
          `<p class="help">Imported previous review by ${esc(r.reviewer)} (${esc(r.classifier_version)}): O / A / M ${esc([r.human_label.othering, r.human_label.aversion, r.human_label.moralization].map(showValue).join(" / "))}. Basis: ${esc(human(r.review_evidence_basis || "unspecified"))}. This has not been overwritten.</p>`,
      )
      .join("");
  $("#notes").value = draft.notes || "";
  $("#review-basis").value = draft.review_evidence_basis || "unspecified";
  $("#evidence-note").value = draft.review_evidence_note || "";
  renderFields();
  const list = filtered(),
    idx = list.findIndex((x) => x.queue_record_id === currentId);
  $("#previous").disabled = idx <= 0;
  $("#next").disabled = idx >= list.length - 1;
  $("#save-state").textContent =
    draft.status === "complete"
      ? `Confirmed by ${draft.reviewer} · ${new Date(draft.reviewed_at).toLocaleString()}`
      : "Choose agree or disagree for each label, then confirm.";
}
function renderFields() {
  const item = current();
  $("#fields").innerHTML = Object.entries(item.ai_values)
    .map(([key, value]) => {
      const decision = draft.decisions?.[key];
      let control = "";
      if (decision === "disagree") {
        const corrected = draft.human_label[key] ?? value;
        if (["othering", "aversion", "moralization"].includes(key)) {
          control = `<select data-correction="${key}" aria-label="Corrected ${human(key)}"><option value="" ${corrected == null ? "selected" : ""}>Choose a score</option>${[0, 1, 2, 3, 4].map((n) => `<option value="${n}" ${corrected === n ? "selected" : ""}>${n} · ${["Absent", "Weak / implicit", "Moderate / clear", "Strong", "Extreme / categorical"][n]}</option>`).join("")}</select>`;
        } else if (typeof value === "boolean") {
          control = `<select data-correction="${key}" aria-label="Corrected ${human(key)}"><option value="true" ${corrected === true ? "selected" : ""}>Yes</option><option value="false" ${corrected === false ? "selected" : ""}>No</option></select>`;
        } else if (key === "narratives") {
          control = `<div class="checkboxes">${packet.narratives.map((n) => `<label><input type="checkbox" data-narrative="${n}" ${corrected.includes(n) ? "checked" : ""}>${esc(human(n))}</label>`).join("")}</div>`;
        } else {
          control = `<textarea rows="2" data-correction="${key}" aria-label="Corrected ${human(key)}" placeholder="${key === "countries" ? "ISO2 country codes, separated by commas" : "One target name per line"}">${esc(corrected.join(key === "countries" ? ", " : "\n"))}</textarea>`;
          if (key === "countries")
            control +=
              "<small>Use ISO2 codes (e.g. NL, FR); leave blank for no specific country.</small>";
        }
        control = `<div class="correction"><label>Your corrected label</label>${control}</div>`;
      }
      const e = item.model_label.dimension_evidence?.find(
        (e) => e.dimension === key,
      );
      const evidence = e
        ? `<div class="help">${e.quote ? `<blockquote>“${esc(e.quote)}”</blockquote><span>${esc(e.source_id)} · ${esc(e.speaker)} · ${esc(human(e.attribution))}</span>` : ""}<p>${esc(e.explanation)}</p></div>`
        : "";
      return `<section class="field"><div class="field-header"><b>${esc(human(key))}</b><span class="ai-value">AI: ${esc(showValue(value))}</span></div>${evidence}<div class="choices"><button data-field="${key}" data-decision="agree" class="${decision === "agree" ? "chosen" : ""}" aria-pressed="${decision === "agree"}">Agree</button><button data-field="${key}" data-decision="disagree" class="${decision === "disagree" ? "chosen" : ""}" aria-pressed="${decision === "disagree"}">Disagree / correct</button></div>${control}</section>`;
    })
    .join("");
  $("#fields")
    .querySelectorAll("[data-decision]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          const key = b.dataset.field;
          draft.decisions[key] = b.dataset.decision;
          draft.human_label[key] = structuredClone(item.ai_values[key]);
          if (
            typeof item.ai_values[key] === "boolean" &&
            b.dataset.decision === "disagree"
          )
            draft.human_label[key] = !item.ai_values[key];
          autosave();
          renderFields();
        }),
    );
  $("#fields")
    .querySelectorAll("[data-correction]")
    .forEach(
      (el) =>
        (el.oninput = () => {
          const key = el.dataset.correction;
          draft.human_label[key] = [
            "othering",
            "aversion",
            "moralization",
          ].includes(key)
            ? el.value === ""
              ? null
              : Number(el.value)
            : typeof item.ai_values[key] === "boolean"
              ? el.value === "true"
              : el.value
                  .split(key === "countries" ? /[\s,]+/ : /\n/)
                  .map((x) => x.trim())
                  .filter(Boolean);
          if (key === "countries")
            draft.human_label[key] = draft.human_label[key].map((x) =>
              x.toUpperCase(),
            );
          autosave();
        }),
    );
  $("#fields")
    .querySelectorAll("[data-narrative]")
    .forEach(
      (el) =>
        (el.onchange = () => {
          draft.human_label.narratives = [
            ...$("#fields").querySelectorAll("[data-narrative]:checked"),
          ].map((x) => x.dataset.narrative);
          autosave();
        }),
    );
}
function autosave() {
  if (!current()) return;
  draft.status = "pending";
  draft.notes = $("#notes").value;
  draft.review_evidence_basis = $("#review-basis").value;
  draft.review_evidence_note = $("#evidence-note").value;
  decisions()[currentId] = structuredClone(draft);
  persist();
  summary();
  $("#save-state").textContent = storageOK
    ? "Draft saved in this browser · not yet confirmed"
    : "Draft in memory only · download a backup";
}
function equal(a, b) {
  return (
    JSON.stringify(Array.isArray(a) ? [...a].sort() : a) ===
    JSON.stringify(Array.isArray(b) ? [...b].sort() : b)
  );
}
function validate(item, state) {
  if (!state.reviewer?.trim()) throw Error("Enter your reviewer name first.");
  if (
    item.model_label.evidence_scope &&
    ![
      "metadata_only",
      "metadata_and_english_transcript",
      "watched_video",
    ].includes(state.review_evidence_basis)
  )
    throw Error("Choose the evidence you used for this review.");
  if (item.model_label.evidence_scope) {
    const scores = ["othering", "aversion", "moralization"].map(
      (k) => state.human_label[k],
    );
    if (scores.some((v) => v === null) && !scores.every((v) => v === null))
      throw Error(
        "Either retain all three unscored dimensions, or supply all three scores from the evidence you reviewed.",
      );
  }
  for (const [key, ai] of Object.entries(item.ai_values)) {
    const d = state.decisions[key],
      value = state.human_label[key];
    if (!["agree", "disagree"].includes(d))
      throw Error(`Review ${human(key)} before confirming.`);
    if (d === "agree" && !equal(value, ai))
      throw Error(`The agreed ${human(key)} must match the AI label.`);
    if (d === "disagree" && equal(value, ai))
      throw Error(`Provide a different ${human(key)} label, or choose Agree.`);
    if (
      ["othering", "aversion", "moralization"].includes(key) &&
      !(value === null && ai === null && d === "agree") &&
      (!Number.isInteger(value) || value < 0 || value > 4)
    )
      throw Error("Scores must be whole numbers from 0 to 4.");
    if (typeof ai === "boolean" && typeof value !== "boolean")
      throw Error("Choose Yes or No.");
    if (
      Array.isArray(ai) &&
      (!Array.isArray(value) || value.some((x) => typeof x !== "string"))
    )
      throw Error(`Invalid ${key}.`);
    if (
      key === "countries" &&
      value.some((c) => !packet.countries.some((x) => x.iso2 === c))
    )
      throw Error("Use valid country codes from the monitor.");
    if (
      key === "narratives" &&
      (!value.length || value.some((x) => !packet.narratives.includes(x)))
    )
      throw Error(
        "Choose at least one narrative, including none_unclear if appropriate.",
      );
  }
}
$("#reviewer").oninput = persist;
$("#notes").oninput = autosave;
$("#review-basis").onchange = autosave;
$("#evidence-note").oninput = autosave;
$("#agree-all").onclick = () => {
  draft.decisions = Object.fromEntries(
    Object.keys(current().ai_values).map((k) => [k, "agree"]),
  );
  draft.human_label = structuredClone(current().ai_values);
  autosave();
  renderFields();
};
$("#confirm").onclick = () => {
  try {
    draft.reviewer = $("#reviewer").value.trim();
    validate(current(), draft);
    draft.reviewed_at = new Date().toISOString();
    draft.status = "complete";
    draft.notes = $("#notes").value;
    decisions()[currentId] = structuredClone(draft);
    persist();
    notice(
      "Review confirmed and saved locally. Download confirmed reviews when ready.",
    );
    const list = filtered(),
      at = list.findIndex((x) => x.queue_record_id === currentId);
    const next =
      list.slice(at + 1).find((x) => stateFor(x).status !== "complete") ||
      list.find((x) => stateFor(x).status !== "complete");
    renderQueue();
    if (next) selectItem(next.queue_record_id);
    else {
      renderItem();
      $("#save-state").textContent =
        "All matching items confirmed. Download your reviews.";
    }
  } catch (e) {
    notice(e.message, true);
  }
};
$("#defer").onclick = () => {
  draft.status = "deferred";
  draft.notes = $("#notes").value;
  decisions()[currentId] = structuredClone(draft);
  persist();
  const list = filtered(),
    at = list.findIndex((x) => x.queue_record_id === currentId);
  renderQueue();
  if (list[at + 1]) selectItem(list[at + 1].queue_record_id);
  else renderItem();
};
function move(delta) {
  const list = filtered(),
    at = list.findIndex((x) => x.queue_record_id === currentId);
  if (list[at + delta]) selectItem(list[at + delta].queue_record_id);
}
$("#previous").onclick = () => move(-1);
$("#next").onclick = () => move(1);
for (const id of ["kind", "status", "search", "assessment"])
  $("#" + id).oninput = () => {
    renderQueue();
    const list = filtered();
    if (!list.some((x) => x.queue_record_id === currentId) && list.length)
      selectItem(list[0].queue_record_id);
  };
$("#export").onclick = () => {
  try {
    const out = packet.items
      .filter((x) => stateFor(x).status === "complete")
      .map((x) => {
        const s = stateFor(x);
        validate(x, s);
        return {
          queue_record_id: x.queue_record_id,
          queue_hash: x.queue_hash,
          human_label: s.human_label,
          review_decisions: s.decisions,
          review_method: "ai_assisted_confirmation",
          reviewer: s.reviewer,
          reviewed_at: s.reviewed_at,
          review_notes: s.notes || "",
          review_evidence_basis: s.review_evidence_basis || "unspecified",
          review_evidence_note: s.review_evidence_note || "",
          approved_excerpts: [],
        };
      });
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download =
      "eiim-confirmed-reviews-" +
      new Date().toISOString().slice(0, 10) +
      ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice(
      `${out.length} confirmed reviews exported. Keep this file as your backup and provide it for database import.`,
    );
  } catch (e) {
    notice(e.message, true);
  }
};
$("#restore").onchange = async (e) => {
  try {
    const rows = JSON.parse(await e.target.files[0].text());
    if (!Array.isArray(rows)) throw Error("Expected a review array.");
    const pending = [];
    for (const r of rows) {
      const item = packet.items.find(
        (x) => x.queue_record_id === r.queue_record_id,
      );
      if (!item || r.queue_hash !== item.queue_hash)
        throw Error("This file contains an unknown or changed review item.");
      const state = {
        queue_hash: r.queue_hash,
        decisions: r.review_decisions,
        human_label: r.human_label,
        reviewer: r.reviewer,
        reviewed_at: r.reviewed_at,
        notes: r.review_notes || "",
        review_evidence_basis: r.review_evidence_basis || "unspecified",
        review_evidence_note: r.review_evidence_note || "",
        status: "complete",
      };
      if (!state.reviewed_at || Number.isNaN(Date.parse(state.reviewed_at)))
        throw Error("Missing review timestamp.");
      validate(item, state);
      pending.push([r.queue_record_id, state]);
    }
    for (const [id, state] of pending) decisions()[id] = state;
    persist();
    renderQueue();
    if (current()) selectItem(currentId);
    notice(`Restored ${pending.length} confirmed reviews.`);
  } catch (e) {
    notice("Could not restore: " + e.message, true);
  }
};
renderQueue();
if (packet.items.length) selectItem(filtered()[0]?.queue_record_id);
if (!storageOK)
  notice(
    "Browser storage is unavailable; download your confirmed reviews before closing.",
    true,
  );
// A local export can be refreshed without overwriting in-progress decisions.
if (location.protocol.startsWith("http"))
  setInterval(async () => {
    try {
      const r = await fetch("review-data.json", { cache: "no-store" });
      if (!r.ok) return;
      const next = await r.json();
      if (next.generated_at === packet.generated_at) return;
      packet = next;
      renderQueue();
      if (!currentId && filtered().length)
        selectItem(filtered()[0].queue_record_id);
      notice(
        "The private review packet was refreshed. Your saved decisions are unchanged.",
      );
    } catch {}
  }, 30000);
