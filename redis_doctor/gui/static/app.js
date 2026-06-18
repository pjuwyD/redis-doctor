"use strict";

const SEV_COLOR = { critical: "#d33", warning: "#e8a300", info: "#888" };
let catChart = null;

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === name));
  document.querySelectorAll("#nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name)
  );
  if (name === "history") loadHistory();
  if (name === "schedules") loadSchedules();
  if (name === "fleet") loadFleet();
}

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

document.querySelectorAll("#nav button").forEach((b) =>
  b.addEventListener("click", () => showView(b.dataset.view))
);

async function errorMessage(r) {
  // Tolerate non-JSON error bodies (e.g. a plain "Internal Server Error").
  const text = await r.text();
  try {
    return JSON.parse(text).detail || text;
  } catch {
    return text || r.statusText;
  }
}
async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}
async function jpost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

function renderDashboard(report, reportId) {
  document.getElementById("dash-empty").hidden = true;
  document.getElementById("dash-content").hidden = false;
  document.getElementById("score").textContent = report.health_score;
  document.getElementById("c-crit").textContent = report.summary.critical;
  document.getElementById("c-warn").textContent = report.summary.warning;
  document.getElementById("c-info").textContent = report.summary.info;

  // Export links require a persisted report id.
  const bar = document.getElementById("export-bar");
  if (reportId != null) {
    document.getElementById("exp-md").href = `/api/export/${reportId}.md`;
    document.getElementById("exp-pdf").href = `/api/export/${reportId}.pdf`;
    bar.hidden = false;
  } else {
    bar.hidden = true;
  }

  const cats = report.category_scores || {};
  const labels = Object.keys(cats);
  const data = labels.map((l) => cats[l]);
  const ctx = document.getElementById("cat-chart");
  if (catChart) catChart.destroy();
  catChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Category score", data, backgroundColor: "#6688cc" }],
    },
    options: { scales: { y: { min: 0, max: 100 } } },
  });

  const order = { critical: 0, warning: 1, info: 2 };
  const findings = [...report.findings].sort((a, b) => order[a.severity] - order[b.severity]);
  const box = document.getElementById("findings");
  box.innerHTML = "";
  for (const f of findings) {
    const div = document.createElement("div");
    div.className = "finding " + f.severity;
    const title = document.createElement("div");
    title.textContent = f.title;
    const id = document.createElement("div");
    id.className = "id";
    id.textContent = "[" + f.severity + "] " + f.id;
    div.appendChild(id);
    div.appendChild(title);
    if ((f.suggested_fixes || []).length || (f.suggested_checks || []).length) {
      const det = document.createElement("details");
      const sum = document.createElement("summary");
      sum.textContent = "details";
      det.appendChild(sum);
      const body = document.createElement("div");
      body.textContent =
        (f.explanation || "") +
        "\nChecks: " + (f.suggested_checks || []).join(" | ") +
        "\nFixes: " + (f.suggested_fixes || []).join("; ");
      det.appendChild(body);
      div.appendChild(det);
    }
    box.appendChild(div);
  }
}

document.getElementById("run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const target = document.getElementById("target").value.trim();
  const status = document.getElementById("run-status");
  status.textContent = "Analyzing " + target + " ...";
  try {
    const report = await jpost("/api/analyze", { target, options: {} });
    status.textContent = "Done.";
    renderDashboard(report, report.id);
    showView("dashboard");
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
});

async function loadHistory() {
  const tbody = document.querySelector("#history-table tbody");
  tbody.innerHTML = "";
  const rows = await jget("/api/reports");
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${r.id}</td><td>${esc(r.generated_at)}</td><td>${esc(r.target)}</td>` +
      `<td>${r.health_score}</td><td>${r.critical}</td>` +
      `<td><button data-id="${r.id}">Open</button> ` +
      `<a href="/api/export/${r.id}.md" target="_blank" rel="noopener">MD</a> ` +
      `<a href="/api/export/${r.id}.pdf" target="_blank" rel="noopener">PDF</a></td>`;
    tr.querySelector("button").addEventListener("click", async () => {
      const report = await jget("/api/reports/" + r.id);
      renderDashboard(report, r.id);
      showView("dashboard");
    });
    tbody.appendChild(tr);
  }
}
document.getElementById("refresh-history").addEventListener("click", loadHistory);

document.getElementById("diff-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const before = document.getElementById("diff-before").value;
  const after = document.getElementById("diff-after").value;
  const out = document.getElementById("diff-output");
  try {
    const d = await jget(`/api/diff?before=${before}&after=${after}`);
    out.textContent = JSON.stringify(d, null, 2);
  } catch (err) {
    out.textContent = "Error: " + err.message;
  }
});

async function loadSchedules() {
  const tbody = document.querySelector("#schedule-table tbody");
  tbody.innerHTML = "";
  const rows = await jget("/api/schedule");
  for (const s of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${s.id}</td><td>${s.target}</td><td>${s.cron}</td><td>${s.notify}</td>` +
      `<td><button data-id="${s.id}">Delete</button></td>`;
    tr.querySelector("button").addEventListener("click", async () => {
      await fetch("/api/schedule/" + s.id, { method: "DELETE" });
      loadSchedules();
    });
    tbody.appendChild(tr);
  }
}
document.getElementById("schedule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await jpost("/api/schedule", {
    target: document.getElementById("sched-target").value.trim(),
    cron: document.getElementById("sched-cron").value.trim(),
    notify: document.getElementById("sched-notify").checked,
  });
  loadSchedules();
});

async function loadFleet() {
  const box = document.getElementById("fleet-cards");
  box.innerHTML = "";
  const fleet = await jget("/api/fleet");
  if (!fleet.length) {
    box.innerHTML =
      "<p>No fleet configured. Start the server with " +
      "<code>redis-doctor serve --fleet fleet.yml</code>.</p>";
    return;
  }
  for (const item of fleet) {
    const div = document.createElement("div");
    div.className = "card";
    const score = item.score ?? "–";
    div.innerHTML = `<div class="big">${score}</div><div>${item.name || item.target}</div>`;
    if (item.report_id != null) {
      div.style.cursor = "pointer";
      div.title = "Open latest report";
      div.addEventListener("click", async () => {
        const report = await jget("/api/reports/" + item.report_id);
        renderDashboard(report, item.report_id);
        showView("dashboard");
      });
    }
    box.appendChild(div);
  }
}

// --- Explore ---------------------------------------------------------------

let exploreCursor = 0;

function exploreUnlocked() {
  return document.getElementById("exp-unlock").checked;
}

document.getElementById("exp-unlock").addEventListener("change", () => {
  const label = document.getElementById("exp-lock-label");
  if (exploreUnlocked()) {
    label.textContent = "🔓 full reads UNLOCKED";
    label.style.color = "#d12b2b";
  } else {
    label.textContent = "🔒 full reads locked";
    label.style.color = "";
  }
});

function typeBadge(t) {
  return `<span class="badge">${esc(t)}</span>`;
}

async function exploreScan(reset) {
  const target = document.getElementById("exp-target").value.trim();
  const match = document.getElementById("exp-match").value.trim() || null;
  const status = document.getElementById("explore-status");
  const list = document.getElementById("explore-keys");
  if (reset) {
    exploreCursor = 0;
    list.innerHTML = "";
    document.getElementById("explore-detail").innerHTML = "";
  }
  status.textContent = "Scanning…";
  try {
    const page = await jpost("/api/explore/scan", {
      target,
      match,
      cursor: exploreCursor,
      count: 500,
    });
    exploreCursor = page.cursor;
    for (const k of page.keys) {
      const row = document.createElement("div");
      row.className = "key-row";
      const size = k.size != null ? ` · ${k.size}` : "";
      row.innerHTML =
        `${typeBadge(k.type)} <span class="kname">${esc(k.key)}</span>` +
        `<span class="kmeta">${ttlText(k.ttl)} · ${humanBytes(k.memory)}${size}</span>`;
      row.addEventListener("click", () => {
        list.querySelectorAll(".key-row.sel").forEach((el) => el.classList.remove("sel"));
        row.classList.add("sel");
        exploreOpen(target, k.key);
      });
      list.appendChild(row);
    }
    status.textContent = `${list.childElementCount} keys${page.complete ? " (end)" : ""}`;
    document.getElementById("explore-more").hidden = page.complete;
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
}

async function exploreOpen(target, key) {
  const pane = document.getElementById("explore-detail");
  pane.innerHTML = "Loading…";
  try {
    const d = await jpost("/api/explore/key", { target, key, full: exploreUnlocked() });
    pane.innerHTML = renderKeyDetail(d);
  } catch (err) {
    pane.innerHTML = `<p class="muted">Error: ${esc(err.message)}</p>`;
  }
}

function humanBytes(n) {
  if (n == null) return "?";
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return v.toFixed(1) + " " + u[i];
}
function ttlText(t) {
  return t == null || t < 0 ? "no TTL" : `${t}s`;
}
function chip(label, value) {
  return `<span class="chip"><span class="chip-k">${esc(label)}</span> ${esc(value)}</span>`;
}

function renderKeyDetail(d) {
  jsonValues = []; // reset the copy registry for this key
  if (d.exists === false) return `<p class="muted">Key not found.</p>`;
  const chips = [
    `<span class="badge">${esc(d.type)}</span>`,
    d.encoding ? chip("enc", d.encoding) : "",
    chip("ttl", ttlText(d.ttl)),
    chip("memory", humanBytes(d.memory)),
    d.size != null ? chip("size", d.size) : "",
  ].join(" ");
  let note = `preview: ${d.preview_mode}`;
  if (d.truncated) {
    note += d.size != null ? ` · sample of ${d.size}` : " · sample";
    if (d.preview_mode === "bounded") note += " — unlock for full value";
  }
  return (
    `<div class="kd-head"><div class="kd-key">${esc(d.key)}</div>` +
    `<div class="chips">${chips}</div><p class="muted">${note}</p></div>` +
    `<div class="preview">${renderPreview(d)}</div>`
  );
}

// Collapsible JSON tree -----------------------------------------------------

function tryParseJson(s) {
  if (typeof s !== "string") return undefined;
  const t = s.trim();
  if (!(t.startsWith("{") || t.startsWith("["))) return undefined;
  try {
    return JSON.parse(t);
  } catch {
    return undefined;
  }
}

// Registry so copy buttons can recover a node's value without bloating the HTML.
let jsonValues = [];
function jsonRegister(v) {
  jsonValues.push(v);
  return jsonValues.length - 1;
}

function jsonNode(v, depth) {
  if (v === null) return `<span class="j-null">null</span>`;
  const t = typeof v;
  if (t === "number") return `<span class="j-num">${esc(v)}</span>`;
  if (t === "boolean") return `<span class="j-bool">${v}</span>`;
  if (t === "string") return `<span class="j-str">"${esc(v)}"</span>`;
  const open = depth < 1 ? " open" : "";
  const copy = `<button type="button" class="j-copy" data-jid="${jsonRegister(v)}" title="copy JSON">⧉</button>`;
  if (Array.isArray(v)) {
    if (!v.length) return `<span class="j-empty">[]</span>`;
    const items = v.map((it) => `<li>${jsonNode(it, depth + 1)}</li>`).join("");
    return `<details class="j-node"${open}><summary>${copy}<span class="j-sum">[ ] ${v.length}</span></summary><ul class="j-list">${items}</ul></details>`;
  }
  if (t === "object") {
    const keys = Object.keys(v);
    if (!keys.length) return `<span class="j-empty">{}</span>`;
    const items = keys
      .map((k) => `<li><span class="j-key">${esc(k)}</span>: ${jsonNode(v[k], depth + 1)}</li>`)
      .join("");
    return `<details class="j-node"${open}><summary>${copy}<span class="j-sum">{ } ${keys.length}</span></summary><ul class="j-list">${items}</ul></details>`;
  }
  return `<span>${esc(String(v))}</span>`;
}

function jsonBlock(parsed, raw, startDepth = 0) {
  const toolbar =
    `<div class="json-toolbar">` +
    `<input class="json-filter" type="search" placeholder="filter keys/values…" />` +
    `<button type="button" class="json-expand">expand all</button>` +
    `<button type="button" class="json-collapse">collapse all</button>` +
    `</div>`;
  const tree = `<div class="jsonview">${jsonNode(parsed, startDepth)}</div>`;
  const rawd = `<details class="rawjson"><summary>raw</summary><pre class="strval">${esc(raw)}</pre></details>`;
  return `<div class="jsonblock">${toolbar}${tree}${rawd}</div>`;
}

// Render a value: a full JSON block (tree + toolbar) if it parses as JSON,
// collapsed by default to keep table cells compact; else escaped text.
function cellValue(v) {
  const parsed = tryParseJson(v);
  if (parsed !== undefined) return jsonBlock(parsed, v, 1);
  return esc(v);
}

function rawTable(cols, htmlRows) {
  const head = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const body = htmlRows
    .map((r) => "<tr>" + r.map((c) => `<td>${c}</td>`).join("") + "</tr>")
    .join("");
  return `<table class="kv"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderPreview(d) {
  const t = d.type;
  const p = d.preview;
  if (p && p.error) return `<p class="muted">preview unavailable: ${esc(p.error)}</p>`;
  if (p && p.note) return `<p class="muted">${esc(p.note)}</p>`;
  if (t === "string") {
    if (!p) return `<p class="muted">(empty string)</p>`;
    const parsed = tryParseJson(p);
    if (parsed !== undefined) return jsonBlock(parsed, p);
    return `<pre class="strval">${esc(p)}</pre>`;
  }
  if (t === "hash") {
    const rows = Object.entries(p);
    return rows.length
      ? rawTable(["Field", "Value"], rows.map(([k, v]) => [esc(k), cellValue(v)]))
      : `<p class="muted">(empty)</p>`;
  }
  if (t === "zset") {
    const rows = Array.isArray(p) ? p : Object.entries(p);
    return rows.length
      ? rawTable(["Member", "Score"], rows.map(([m, s]) => [cellValue(m), esc(s)]))
      : `<p class="muted">(empty)</p>`;
  }
  if (t === "set") {
    return (p || []).length
      ? `<div class="chips mono">${p.map((m) => `<span class="chip">${esc(m)}</span>`).join("")}</div>`
      : `<p class="muted">(empty)</p>`;
  }
  if (t === "list") {
    if (Array.isArray(p))
      return p.length
        ? rawTable(["#", "Value"], p.map((v, i) => [i, cellValue(v)]))
        : `<p class="muted">(empty)</p>`;
    return rawTable(
      ["Position", "Value"],
      [["head", cellValue(p.head)], ["tail", cellValue(p.tail)]]
    );
  }
  if (t === "stream") {
    if (!(p || []).length) return `<p class="muted">(no entries)</p>`;
    return p
      .map(
        (e) =>
          `<div class="stream-entry"><code>${esc(e.id)}</code>` +
          rawTable(
            ["Field", "Value"],
            Object.entries(e.fields || {}).map(([k, v]) => [esc(k), cellValue(v)])
          ) +
          `</div>`
      )
      .join("");
  }
  return `<pre>${esc(JSON.stringify(p, null, 2))}</pre>`;
}

document.getElementById("explore-form").addEventListener("submit", (e) => {
  e.preventDefault();
  exploreScan(true);
});
document.getElementById("explore-more").addEventListener("click", () => exploreScan(false));

// JSON tree controls (delegated, since the detail pane is re-rendered each open).
const exploreDetailEl = document.getElementById("explore-detail");

function setOpen(scope, open) {
  (scope || exploreDetailEl).querySelectorAll("details.j-node").forEach((d) => (d.open = open));
}
async function copyJson(jid, btn) {
  const v = jsonValues[jid];
  const text = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    const prev = btn.textContent;
    btn.textContent = "✓";
    setTimeout(() => (btn.textContent = prev), 900);
  } catch {
    /* clipboard unavailable (non-secure context) */
  }
}
function jsonFilter(view, q) {
  q = q.trim().toLowerCase();
  const lis = view.querySelectorAll("li");
  if (!q) {
    lis.forEach((li) => (li.style.display = ""));
    return;
  }
  view.querySelectorAll("details.j-node").forEach((d) => (d.open = true));
  lis.forEach((li) => {
    li.style.display = li.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

exploreDetailEl.addEventListener("click", (e) => {
  const copyBtn = e.target.closest(".j-copy");
  if (copyBtn) {
    e.preventDefault(); // don't toggle the <details> we live inside
    e.stopPropagation();
    copyJson(Number(copyBtn.dataset.jid), copyBtn);
    return;
  }
  const exp = e.target.closest(".json-expand");
  if (exp) {
    setOpen(exp.closest(".jsonblock"), true);
    return;
  }
  const col = e.target.closest(".json-collapse");
  if (col) setOpen(col.closest(".jsonblock"), false);
});
exploreDetailEl.addEventListener("input", (e) => {
  if (e.target.classList.contains("json-filter")) {
    const block = e.target.closest(".jsonblock");
    jsonFilter(block.querySelector(".jsonview"), e.target.value);
  }
});
