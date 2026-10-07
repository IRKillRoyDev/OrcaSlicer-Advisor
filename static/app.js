const setupSelect = document.querySelector("#setup");
const groupsEl = document.querySelector("#groups");
const userPresetsEl = document.querySelector("#user-presets");
const promptEl = document.querySelector("#prompt");
const notesEl = document.querySelector("#notes");
const filamentFields = {
  brand: document.querySelector("#filament-brand"),
  type: document.querySelector("#filament-type"),
  color: document.querySelector("#filament-color"),
  diameter: document.querySelector("#filament-diameter"),
};
const filamentTouched = { brand: false, type: false, color: false, diameter: false };
const metaEl = document.querySelector("#profile-meta");
const feedbackEl = document.querySelector("#feedback");
const summaryEl = document.querySelector("#summary");
const diffEl = document.querySelector("#diff");
const resultEl = document.querySelector("#result");
const toastEl = document.querySelector("#toast");
let toastTimer = 0;
const applyBtn = document.querySelector("#apply");
const presetNameEl = document.querySelector("#preset-name");
const presetPreviewEl = document.querySelector("#preset-preview");
const stlStatusEl = document.querySelector("#stl-status");
const clearStlBtn = document.querySelector("#clear-stl");
const fileInput = document.querySelector("#file");
let presetNameTouched = false;

let snapshot = null;
let review = null;
let promptDirty = false;
let notesTimer = 0;

async function loadState(setup) {
  const body = {
    setup: setup ?? null,
    notes: notesEl.value,
    brand: filamentFields.brand.value,
    type: filamentFields.type.value,
    color: filamentFields.color.value,
    diameter_mm: filamentFields.diameter.value,
  };
  const response = await fetch("/api/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not read OrcaSlicer presets");
  snapshot = data;
  review = null;
  render();
  await loadUserPresets();
}

function render() {
  const current = String(snapshot.setup.index);
  setupSelect.innerHTML = snapshot.setups.map((item) => {
    const label = `${item.machine} · ${item.filament}`;
    const selected = String(item.index) === current ? "selected" : "";
    return `<option value="${item.index}" ${selected}>${escapeHtml(label)}</option>`;
  }).join("");
  const plate = snapshot.plate.temp ? `${snapshot.plate.name}, ${snapshot.plate.temp}°` : snapshot.plate.name;
  metaEl.textContent = `${snapshot.setup.process} · ${snapshot.nozzle} mm nozzle · ${snapshot.bed} · ${plate}`;
  groupsEl.innerHTML = snapshot.groups.map((group) => {
    const rows = group.settings.map((setting) => {
      const extra = setting.overridden ? `<span class="override">was ${escapeHtml(setting.parent)}</span>` : "";
      return `<div class="setting"><span><code>${escapeHtml(setting.key)}</code> ${extra}</span><span>${escapeHtml(setting.value)}</span></div>`;
    }).join("");
    return `<details><summary>${escapeHtml(group.name)}</summary>${rows}</details>`;
  }).join("");
  if (!promptDirty) promptEl.value = snapshot.prompt;
  fillFilamentSelects();
  const model = snapshot.model;
  const chooseStlBtn = document.querySelector("#choose-stl");
  if (model) {
    const size = model.size_mm;
    stlStatusEl.textContent = `${model.filename} · ${size[0]} × ${size[1]} × ${size[2]} mm. Preset name: ${model.filename.replace(/\.stl$/i, "")}`;
    clearStlBtn.hidden = false;
    chooseStlBtn.classList.add("loaded");
    if (!presetNameTouched) presetNameEl.value = model.filename.replace(/\.stl$/i, "");
  } else {
    stlStatusEl.textContent = "No STL loaded. Load one to name the preset and put the part size in the JSON.";
    clearStlBtn.hidden = true;
    chooseStlBtn.classList.remove("loaded");
  }
  updatePresetPreview();
  applyBtn.disabled = true;
  summaryEl.hidden = true;
  diffEl.innerHTML = "";
  resultEl.hidden = true;
}

setupSelect.addEventListener("change", async () => {
  promptDirty = false;
  filamentTouched.type = false;
  filamentTouched.diameter = false;
  filamentFields.type.value = "";
  filamentFields.diameter.value = "";
  await run(() => loadState(Number(setupSelect.value)));
});

document.querySelector("#reload").addEventListener("click", async () => {
  promptDirty = false;
  await run(() => loadState(Number(setupSelect.value)));
});

function schedulePromptRefresh() {
  clearTimeout(notesTimer);
  notesTimer = setTimeout(() => {
    if (!promptDirty) run(() => loadState(Number(setupSelect.value)));
  }, 400);
}

notesEl.addEventListener("input", schedulePromptRefresh);
for (const key of Object.keys(filamentFields)) {
  filamentFields[key].addEventListener("change", () => {
    filamentTouched[key] = true;
    if (key === "brand") {
      const types = typesForBrand(filamentFields.brand.value);
      if (filamentFields.type.value && !types.includes(filamentFields.type.value)) {
        filamentTouched.type = true;
        filamentFields.type.value = "";
      }
      fillFilamentSelects();
    }
    schedulePromptRefresh();
  });
}

let filamentOptions = null;

function typesForBrand(brand) {
  if (!filamentOptions) return [];
  if (brand && filamentOptions.types_by_brand[brand]) return filamentOptions.types_by_brand[brand];
  const all = new Set();
  for (const types of Object.values(filamentOptions.types_by_brand)) {
    for (const type of types) all.add(type);
  }
  return [...all].sort((a, b) => a.localeCompare(b));
}

function fillSelect(select, values, selected) {
  const items = [...values];
  if (selected && !items.includes(selected)) items.unshift(selected);
  const blank = `<option value="">Select</option>`;
  select.innerHTML = blank + items.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = selected || "";
}

function chosenFilamentValue(key, fallback) {
  if (filamentTouched[key]) return filamentFields[key].value;
  return fallback || "";
}

function fillFilamentSelects() {
  if (!filamentOptions || !snapshot) return;
  const filament = snapshot.filament || {};
  const brand = chosenFilamentValue("brand", filament.brand);
  const type = chosenFilamentValue("type", filament.type);
  const color = chosenFilamentValue("color", filament.color);
  const diameter = chosenFilamentValue("diameter", filament.diameter_mm);
  fillSelect(filamentFields.brand, filamentOptions.brands, brand);
  const types = typesForBrand(filamentFields.brand.value);
  const typeValue = types.includes(type) ? type : "";
  fillSelect(filamentFields.type, types, typeValue);
  fillSelect(filamentFields.color, filamentOptions.colors, color);
  fillSelect(filamentFields.diameter, filamentOptions.diameters, diameter);
}

async function loadFilamentOptions() {
  const response = await fetch("/api/filament-options");
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not read filament choices");
  filamentOptions = data;
  fillFilamentSelects();
}

promptEl.addEventListener("input", () => {
  promptDirty = true;
});

document.querySelector("#choose-stl").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) loadStl(file);
});
clearStlBtn.addEventListener("click", async () => {
  await run(async () => {
    const response = await fetch("/api/model", { method: "DELETE" });
    if (!response.ok) throw new Error("Could not remove the STL");
    promptDirty = false;
    if (!presetNameTouched) presetNameEl.value = "";
    await loadState(snapshot ? snapshot.setup.index : null);
  });
});

async function loadStl(file) {
  await run(async () => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/model", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not read that STL");
    promptDirty = false;
    presetNameTouched = false;
    await loadState(snapshot ? snapshot.setup.index : null);
    notify(`Loaded ${data.filename}`);
  });
}

document.querySelector("#copy").addEventListener("click", async () => {
  try {
    await copyText(promptEl.value);
    notify("Copied to clipboard");
  } catch {
    notify("Could not copy to the clipboard", false);
  }
});

document.querySelector("#send-grok").addEventListener("click", async () => {
  const button = document.querySelector("#send-grok");
  const status = document.querySelector("#grok-status");
  button.disabled = true;
  status.className = "muted";
  status.textContent = "Checking your Grok login. A signed-in session uses a hidden tab. Otherwise Safari shows the login first.";
  try {
    const response = await fetch("/api/grok", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptEl.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Grok did not answer");
    feedbackEl.value = data.reply;
    status.className = "result ok";
    status.textContent = "Grok replied. The response is in the review box.";
    document.querySelector("#review").click();
  } catch (error) {
    status.className = "result error";
    status.textContent = error.message || String(error);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#review").addEventListener("click", async () => {
  await run(async () => {
    const response = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ setup: snapshot.setup.index, feedback: feedbackEl.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not read that response");
    review = data;
    renderDiff();
  });
});

function renderDiff() {
  summaryEl.hidden = false;
  summaryEl.textContent = review.summary || "No summary was included.";
  const rows = review.diffs.map((item) => {
    const cls = item.changed ? "" : "same";
    const warn = item.warning ? `<div class="muted">${escapeHtml(item.warning)}</div>` : "";
    return `<tr class="${cls}"><td><code>${escapeHtml(item.key)}</code><div class="muted">${escapeHtml(item.reason)}</div>${warn}</td><td>${escapeHtml(item.before)}</td><td>${escapeHtml(item.after)}</td></tr>`;
  }).join("");
  const unknown = review.unknown.length ? `<p class="error">Unknown keys, left unchanged: ${escapeHtml(review.unknown.join(", "))}</p>` : "";
  diffEl.innerHTML = `${unknown}<table><thead><tr><th>Setting</th><th>Now</th><th>Suggested</th></tr></thead><tbody>${rows}</tbody></table>`;
  applyBtn.disabled = review.change_count < 1;
}

presetNameEl.addEventListener("input", () => {
  presetNameTouched = true;
  updatePresetPreview();
});

function updatePresetPreview() {
  const label = presetNameEl.value.trim();
  const parent = snapshot?.setup?.process || "current profile";
  const suffix = ` - ${label}`;
  const full = parent.endsWith(suffix) ? parent : `${parent}${suffix}`;
  presetPreviewEl.textContent = label
    ? `Saves as “${full}”.`
    : "Name it after the part. It is saved as the current profile, then this name.";
}

applyBtn.addEventListener("click", async () => {
  const label = presetNameEl.value.trim();
  if (!label) {
    notify("Name the preset after the part", false);
    return;
  }
  applyBtn.disabled = true;
  try {
    const response = await fetch("/api/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ setup: snapshot.setup.index, diffs: review.diffs, label }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not save presets");
    const lines = data.written.map((item) => `${item.kind}: ${item.name}`);
    result(`${data.note}\n${lines.join("\n")}`, true);
    notify(`Saved “${label}”`);
    await loadUserPresets();
  } catch (error) {
    result(error.message || String(error), false);
    applyBtn.disabled = false;
  }
});

let userPresets = [];

async function loadUserPresets() {
  const response = await fetch("/api/user-presets");
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not list user presets");
  userPresets = data.presets || [];
  renderUserPresets();
}

function showPresetMessage(text, ok) {
  const message = document.querySelector("#preset-message");
  message.hidden = false;
  message.className = ok ? "result ok" : "result error";
  message.textContent = text;
}

function renderUserPresets() {
  if (!userPresets.length) {
    userPresetsEl.innerHTML = "<p class=\"muted\">No user presets.</p>";
    return;
  }
  const groups = ["process", "filament"];
  userPresetsEl.innerHTML = groups.map((kind) => {
    const items = userPresets.filter((item) => item.kind === kind);
    if (!items.length) return "";
    const rows = items.map((item) => {
      const overall = userPresets.indexOf(item);
      const parent = item.inherits ? `<p class="muted">Based on ${escapeHtml(item.inherits)}</p>` : "";
      return `<div class="preset-row"><span><strong>${escapeHtml(item.name)}</strong>${parent}</span><button type="button" data-preset="${overall}">Delete</button></div>`;
    }).join("");
    return `<div class="preset-group"><h3>${escapeHtml(items[0].label)}</h3>${rows}</div>`;
  }).join("");
}

userPresetsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-preset]");
  if (!button) return;
  const preset = userPresets[Number(button.dataset.preset)];
  if (!preset) return;
  const confirmed = window.confirm(`Delete the ${preset.label.toLowerCase()} preset “${preset.name}”?`);
  if (!confirmed) return;
  button.disabled = true;
  try {
    const response = await fetch("/api/user-presets", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: preset.kind, name: preset.name }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not delete that preset");
    notify(`Deleted “${preset.name}”`);
    showPresetMessage(data.note, true);
    await loadUserPresets();
  } catch (error) {
    const message = error.message || String(error);
    notify(message, false);
    showPresetMessage(message, false);
    button.disabled = false;
  }
});

function result(text, ok) {
  resultEl.hidden = false;
  resultEl.className = ok ? "result ok" : "result error";
  resultEl.textContent = text;
}

function notify(text, ok = true) {
  toastEl.textContent = text;
  toastEl.className = ok ? "toast show" : "toast show error";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 4500);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.left = "0";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    if (!copied) throw new Error("copy failed");
  }
}

async function run(action) {
  try {
    await action();
  } catch (error) {
    result(error.message || String(error), false);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

document.querySelectorAll("[role='tab']").forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});

function showTab(name) {
  document.querySelectorAll("[role='tab']").forEach((tab) => {
    tab.setAttribute("aria-selected", tab.dataset.tab === name ? "true" : "false");
  });
  document.querySelector("#panel-review").hidden = name !== "review";
  document.querySelector("#panel-presets").hidden = name !== "presets";
  if (name === "presets") loadUserPresets().catch((error) => notify(error.message, false));
}

loadFilamentOptions().catch((error) => result(error.message, false));
loadState(null).catch((error) => result(error.message, false));
