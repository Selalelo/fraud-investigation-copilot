const dashboardView = document.getElementById("dashboard-view");
const queueView = document.getElementById("queue-view");
const caseView = document.getElementById("case-view");
const queueBody = document.getElementById("queue-body");
const caseScreen = document.getElementById("case-screen");
const backBtn = document.getElementById("back-btn");
const sidebar = document.getElementById("sidebar");
const statCards = document.getElementById("stat-cards");
const recentCasesBody = document.getElementById("recent-cases-body");

const ACTIONS = [
  ["CONTACT_CUSTOMER", "Contact customer"],
  ["RELEASE", "Release"],
  ["BLOCK", "Block"],
  ["ESCALATE", "Escalate"],
  ["REQUEST_INFO", "Request info"],
  ["START_STR", "Start STR"],
  ["GENERATE_SAPS_PDF", "Generate SAPS PDF"],
];

// Mirrors render.py's SCENARIO_DESCRIPTIONS -- keep both in sync.
const SCENARIO_DESCRIPTIONS = {
  APP_SCAM: "Push payment scam pattern: a newly added beneficiary combined with an unusually large transfer.",
  ACCOUNT_TAKEOVER: "Account takeover pattern: an unusual device or a recent SIM swap suggests this may not be the genuine customer.",
  MULE: "Money mule pattern: funds received and rapidly passed through this account.",
  FIRST_PARTY: "First-party risk pattern: an unusually large transfer from a long-standing customer, with no new beneficiary or device signal.",
};

let reasonCodes = [];

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.error || "request failed"), { data });
  return data;
}

function fmtMoney(n) {
  return "R" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function slaText(sla_deadline) {
  if (!sla_deadline) return "n/a";
  const mins = Math.round((new Date(sla_deadline) - new Date()) / 60000);
  if (mins < 0) return "overdue";
  if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}min`;
  return `${mins} min`;
}

const STAT_CARD_DEFS = [
  ["open", "Open"],
  ["decided", "Decided"],
  ["sla_overdue", "SLA Overdue"],
  ["high_priority", "High Priority"],
];

async function loadDashboard() {
  const { stats, recent_cases } = await api("/api/dashboard");
  statCards.innerHTML = STAT_CARD_DEFS.map(
    ([key, label]) => `<div class="stat-card"><div class="stat-value">${stats[key]}</div><div class="stat-label">${label}</div></div>`
  ).join("");

  recentCasesBody.innerHTML = "";
  for (const c of recent_cases) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="badge badge-${c.priority || "LOW"}">${c.priority || "n/a"}</span></td>
      <td>#${c.case_id.slice(0, 8)}</td>
      <td>${c.customer_id}</td>
      <td>${fmtMoney(c.amount)}</td>
      <td>${c.likely_scenario}</td>
      <td><span class="badge badge-${c.status}">${c.status}</span></td>
    `;
    tr.addEventListener("click", () => openCase(c.case_id));
    recentCasesBody.appendChild(tr);
  }
  if (!recent_cases.length) {
    recentCasesBody.innerHTML = '<tr><td colspan="6" class="empty">no cases yet</td></tr>';
  }
}

function showView(name) {
  dashboardView.classList.toggle("hidden", name !== "dashboard");
  queueView.classList.toggle("hidden", name !== "cases");
  caseView.classList.add("hidden");
  sidebar.querySelectorAll(".nav-link[data-nav]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.nav === name);
  });
}

document.getElementById("sidebar-toggle").addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});

sidebar.querySelectorAll(".nav-link[data-nav]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    showView(btn.dataset.nav);
    if (btn.dataset.nav === "dashboard") await loadDashboard();
    if (btn.dataset.nav === "cases") await loadQueue();
  });
});

async function loadQueue() {
  const cases = await api("/api/cases");
  queueBody.innerHTML = "";
  for (const c of cases) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="badge badge-${c.priority || "LOW"}">${c.priority || "n/a"}</span></td>
      <td>#${c.case_id.slice(0, 8)}</td>
      <td>${c.customer_id}</td>
      <td>${fmtMoney(c.amount)}</td>
      <td>${c.likely_scenario}</td>
      <td>${slaText(c.sla_deadline)}</td>
      <td><span class="badge badge-${c.status}">${c.status}</span></td>
      <td>${c.data_source === "AMLSIM_REAL"
        ? '<span class="badge badge-AMLSIM">REAL (AMLSim)</span>'
        : '<span class="badge badge-SYNTHETIC">synthetic</span>'}</td>
    `;
    tr.addEventListener("click", () => openCase(c.case_id));
    queueBody.appendChild(tr);
  }
}

function citationBadges(caseId, evidenceIds) {
  return evidenceIds.map((e) => `<span class="ev-badge" data-eid="${e}">[${e}]</span>`).join("");
}

function wireCitationClicks(container, caseId) {
  container.querySelectorAll(".ev-badge").forEach((badge) => {
    badge.addEventListener("click", async (e) => {
      e.stopPropagation();
      await api(`/api/cases/${caseId}/evidence-view`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evidence_id: badge.dataset.eid, investigator_id: "investigator1" }),
      });
      badge.style.color = "#3fb950";
    });
  });
}

function fmtDateTime(iso) {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// Mirrors copilot.py's _format_delta -- keep both in sync. Makes a real time gap explicit in a
// timeline label instead of leaving the investigator to infer recency (or lack of it) from two
// separate timestamps.
function fmtRelativeDelta(fromIso, toIso) {
  const diffMs = new Date(toIso) - new Date(fromIso);
  const before = diffMs >= 0;
  const totalMinutes = Math.round(Math.abs(diffMs) / 60000);
  let amount, unit;
  if (totalMinutes < 60) {
    amount = totalMinutes; unit = "minute";
  } else if (totalMinutes < 24 * 60) {
    amount = Math.round(totalMinutes / 60); unit = "hour";
  } else {
    amount = Math.round(totalMinutes / (24 * 60)); unit = "day";
  }
  return `${amount} ${unit}${amount === 1 ? "" : "s"} ${before ? "before" : "after"} this transfer`;
}

// -- Sidebar ---------------------------------------------------------------

function buildSidebar(c) {
  const aside = document.createElement("aside");
  aside.className = "case-sidebar";

  const txCard = document.createElement("div");
  txCard.className = "sidebar-card";
  txCard.innerHTML = `
    <h3>Transaction</h3>
    <div class="tx-amount">${fmtMoney(c.amount)}</div>
    <div class="tx-field"><span>Customer</span><span>${c.customer_id}</span></div>
    <div class="tx-field"><span>Beneficiary</span><span>${(c.beneficiary_ids || []).join(", ") || "n/a"}</span></div>
    <div class="tx-field"><span>Time</span><span>${fmtDateTime(c.created_at)}</span></div>
  `;
  aside.appendChild(txCard);

  const riskCard = document.createElement("div");
  riskCard.className = "sidebar-card";
  const riskItems = c.indicators.map(
    (i) => `<div class="risk-item"><span class="risk-dot risk-dot-${i.severity || "LOW"}"></span>${i.statement}</div>`
  ).join("");
  riskCard.innerHTML = `<h3>Risk indicators</h3>${riskItems || '<div class="empty">none found</div>'}`;
  aside.appendChild(riskCard);

  return aside;
}

// -- Tabs --------------------------------------------------------------

const TABS = [
  ["overview", "Overview"],
  ["evidence", "Evidence"],
  ["timeline", "Timeline"],
  ["related", "Related Cases"],
  ["audit", "Audit Trail"],
];

function buildTabBar(c, panels) {
  const bar = document.createElement("div");
  bar.className = "tab-bar";
  TABS.forEach(([key, label], idx) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (idx === 0 ? " active" : "");
    btn.textContent = label;
    btn.addEventListener("click", () => {
      bar.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      Object.entries(panels).forEach(([k, el]) => el.classList.toggle("hidden", k !== key));
      if (key === "evidence" || key === "timeline") loadEvidenceOnce(c);
    });
    bar.appendChild(btn);
  });
  return bar;
}

// -- Overview panel ------------------------------------------------------

function buildOverviewPanel(c) {
  const panel = document.createElement("div");
  panel.className = "tab-panel";
  panel.dataset.panel = "overview";

  const div = document.createElement("div");
  div.innerHTML = `
    <div class="summary-badge">&#9888; ${c.indicators.length} notable indicator${c.indicators.length === 1 ? "" : "s"}</div>
  `;
  panel.appendChild(div);

  const narrBox = document.createElement("div");
  narrBox.className = "narrative-box" + (c.narrative_status === "VALIDATED" && c.narrative ? "" : " narrative-unavailable");
  narrBox.textContent = c.narrative_status === "VALIDATED" && c.narrative
    ? c.narrative
    : "AI narrative unavailable.";
  panel.appendChild(narrBox);

  const ciSection = document.createElement("div");
  ciSection.className = "section";
  ciSection.innerHTML = "<h2>Counter-indicators</h2>";
  if (c.counter_indicators.length) {
    c.counter_indicators.forEach((i) => {
      const d = document.createElement("div");
      d.className = "evidence-item";
      d.innerHTML = `<span>${i.statement}</span><span>${citationBadges(c.case_id, i.evidence_ids)}</span>`;
      ciSection.appendChild(d);
    });
  } else {
    ciSection.innerHTML += '<div class="empty">none found</div>';
  }
  panel.appendChild(ciSection);
  wireCitationClicks(ciSection, c.case_id);

  const relPreview = document.createElement("div");
  relPreview.className = "section";
  const previewItems = (c.linked_entities || []).slice(0, 2).map(
    (l) => `<div class="evidence-item"><span>${l.narrative_hint}</span></div>`
  ).join("");
  relPreview.innerHTML = `<h2>Related cases</h2>${previewItems || '<div class="empty">none found</div>'}`;
  panel.appendChild(relPreview);

  return panel;
}

// -- Evidence + Timeline (lazy-loaded together, since Timeline derives from evidence) --------

let _evidenceCache = {};

async function loadEvidenceOnce(c) {
  if (_evidenceCache[c.case_id]) return _evidenceCache[c.case_id];
  const data = await api(`/api/cases/${c.case_id}/evidence`);
  _evidenceCache[c.case_id] = data;
  renderEvidencePanel(c, data);
  renderTimelinePanel(c, data);
  return data;
}

function renderEvidencePanel(c, evidence) {
  const panel = document.querySelector('.tab-panel[data-panel="evidence"]');
  if (!panel) return;
  panel.innerHTML = "";
  evidence.sources.forEach((src) => {
    const card = document.createElement("div");
    card.className = "evidence-card";
    let body;
    if (src.status === "FOUND" && src.data) {
      body = Object.entries(src.data).map(
        ([k, v]) => `<div class="evidence-field"><span>${k.replace(/_/g, " ")}</span><span>${v === null ? "·" : v}</span></div>`
      ).join("");
    } else {
      body = `<div class="evidence-field"><span>Status</span><span>${src.status}${src.error ? " · " + src.error : ""}</span></div>`;
    }
    card.innerHTML = `<h4>${src.source} <span class="badge badge-${src.status === "FOUND" ? "LOW" : "MEDIUM"}">${src.status}</span></h4>${body}`;
    panel.appendChild(card);
  });
}

function renderTimelinePanel(c, evidence) {
  const panel = document.querySelector('.tab-panel[data-panel="timeline"]');
  if (!panel) return;
  panel.innerHTML = "";

  const events = [];
  const beneficiary = evidence.sources.find((s) => s.source === "BENEFICIARY");
  if (beneficiary && beneficiary.status === "FOUND" && beneficiary.data.date_added) {
    events.push({
      time: beneficiary.data.date_added,
      label: `Beneficiary added, ${fmtRelativeDelta(beneficiary.data.date_added, c.created_at)}`,
      source: `evidence [${beneficiary.evidence_id}]`,
    });
  }
  events.push({ time: c.created_at, label: "Alert received / transfer initiated", source: "case.created_at" });
  events.push({ time: evidence.created_at, label: "Evidence snapshot frozen (investigation began)", source: `snapshot ${evidence.snapshot_id.slice(0, 8)}` });
  (c.audit_history || []).forEach((a) => {
    (a.evidence_views || []).forEach((v) => {
      events.push({ time: v.viewed_at, label: `Investigator viewed evidence [${v.evidence_id}]`, source: `audit log, ${v.investigator_id}` });
    });
    events.push({ time: a.decided_at, label: `Decision recorded: ${a.decision}`, source: `audit log, ${a.decided_by}` });
  });

  events
    .filter((e) => e.time)
    .sort((a, b) => new Date(a.time) - new Date(b.time))
    .forEach((e) => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      item.innerHTML = `
        <div class="timeline-time">${fmtDateTime(e.time)}</div>
        <div class="timeline-label">${e.label}</div>
        <div class="timeline-source">from ${e.source}</div>
      `;
      panel.appendChild(item);
    });

  if (!panel.children.length) panel.innerHTML = '<div class="empty">no timestamped events available</div>';
}

// -- Related Cases + Audit Trail (built from data already in the case detail response) -----

function buildRelatedPanel(c) {
  const panel = document.createElement("div");
  panel.className = "tab-panel hidden";
  panel.dataset.panel = "related";
  if (c.linked_entities.length) {
    c.linked_entities.forEach((l) => {
      const d = document.createElement("div");
      d.className = "evidence-item";
      d.innerHTML = `<span>${l.narrative_hint}</span><span>${l.hops}-hop, shared ${l.shared_attribute.toLowerCase()}</span>`;
      panel.appendChild(d);
    });
  } else {
    panel.innerHTML = '<div class="empty">none found</div>';
  }
  return panel;
}

function buildAuditPanel(c) {
  const panel = document.createElement("div");
  panel.className = "tab-panel hidden";
  panel.dataset.panel = "audit";
  if (!c.audit_history.length) {
    panel.innerHTML = '<div class="empty">no decisions recorded yet</div>';
    return panel;
  }
  c.audit_history.forEach((a) => {
    const row = document.createElement("div");
    row.className = "audit-row";
    row.innerHTML = `
      <div><span class="audit-label">Decision</span>${a.decision}</div>
      <div><span class="audit-label">Reason code</span>${a.reason_code}</div>
      <div><span class="audit-label">Rationale</span>${a.rationale}</div>
      <div><span class="audit-label">Decided by / at</span>${a.decided_by}<br>${fmtDateTime(a.decided_at)}</div>
    `;
    panel.appendChild(row);
    (a.evidence_views || []).forEach((v) => {
      const vr = document.createElement("div");
      vr.className = "audit-view-row";
      vr.innerHTML = `<span>Evidence [${v.evidence_id}] viewed by ${v.investigator_id}</span><span>${fmtDateTime(v.viewed_at)}</span>`;
      panel.appendChild(vr);
    });
  });
  return panel;
}

// -- Decision panel --------------------------------------------------------

function buildDecisionPanel(c) {
  const panel = document.createElement("div");
  panel.className = "decision-panel";

  if (c.status === "DECIDED") {
    const last = c.audit_history[c.audit_history.length - 1];
    panel.innerHTML = `<h3>Investigator decision</h3><div class="decided-banner">${
      last
        ? `Decided: ${last.decision} · ${last.reason_code} · "${last.rationale}" (by ${last.decided_by})`
        : "This case has been decided."
    }</div>`;
    return panel;
  }

  panel.innerHTML = `
    <h3>Investigator decision</h3>
    <div class="decision-row">
      <label>Action</label>
      <select id="decision-action">
        <option value="">Choose an action (required)</option>
        ${ACTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
      </select>
    </div>
    <div class="decision-row">
      <label>Reason code</label>
      <select id="reason-code">
        <option value="">Reason code (required)</option>
        ${reasonCodes.map((r) => `<option value="${r}">${r}</option>`).join("")}
      </select>
    </div>
    <div class="decision-row">
      <label>Rationale</label>
      <textarea id="rationale" placeholder="Rationale (required)"></textarea>
    </div>
    <div class="form-error" id="form-error"></div>
    <button class="submit-decision-btn" id="submit-decision-btn">Submit Investigation</button>
  `;

  panel.querySelector("#submit-decision-btn").addEventListener("click", () => submitDecision(c.case_id, panel));
  return panel;
}

async function submitDecision(caseId, panel) {
  const decisionValue = panel.querySelector("#decision-action").value;
  const reasonCode = panel.querySelector("#reason-code").value;
  const rationale = panel.querySelector("#rationale").value;
  const errorEl = panel.querySelector("#form-error");
  errorEl.textContent = "";
  if (!decisionValue) {
    errorEl.textContent = "Choose an action first.";
    return;
  }
  try {
    await api(`/api/cases/${caseId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision: decisionValue, reason_code: reasonCode, rationale,
        investigator_id: "investigator1",
      }),
    });
    await openCase(caseId);
  } catch (e) {
    errorEl.textContent = e.data && e.data.error ? e.data.error : "Could not record decision.";
  }
}

// -- Copilot chat panel ------------------------------------------------------

function copilotMessage(role, text) {
  const div = document.createElement("div");
  div.className = `copilot-msg copilot-msg-${role}`;
  div.textContent = text;
  return div;
}

async function copilotAsk(caseId, question, log) {
  log.appendChild(copilotMessage("user", question));
  const thinking = copilotMessage("bot", "…");
  log.appendChild(thinking);
  log.scrollTop = log.scrollHeight;
  try {
    const { answer } = await api(`/api/cases/${caseId}/copilot/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    thinking.textContent = answer;
  } catch (e) {
    thinking.textContent = "Could not get an answer for that question.";
  }
  log.scrollTop = log.scrollHeight;
}

function buildCopilotPanel(c) {
  const aside = document.createElement("aside");
  aside.className = "copilot-panel";
  aside.innerHTML = `
    <h3>Copilot</h3>
    <div class="copilot-log" id="copilot-log"></div>
    <div class="copilot-suggestions" id="copilot-suggestions"></div>
    <div class="copilot-input-row">
      <input type="text" id="copilot-input" placeholder="Ask a question..." />
      <button id="copilot-send">&#10148;</button>
    </div>
  `;

  const log = aside.querySelector("#copilot-log");
  const suggestions = aside.querySelector("#copilot-suggestions");
  const input = aside.querySelector("#copilot-input");
  const sendBtn = aside.querySelector("#copilot-send");

  const send = (question) => {
    const q = (question || input.value).trim();
    if (!q) return;
    input.value = "";
    copilotAsk(c.case_id, q, log);
  };

  sendBtn.addEventListener("click", () => send());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });

  api(`/api/cases/${c.case_id}/copilot/intro`).then(({ intro, suggested_questions }) => {
    log.appendChild(copilotMessage("bot", intro));
    suggested_questions.forEach((q) => {
      const btn = document.createElement("button");
      btn.className = "copilot-suggestion-btn";
      btn.textContent = q;
      btn.addEventListener("click", () => send(q));
      suggestions.appendChild(btn);
    });
  });

  return aside;
}

// -- Top-level case screen -------------------------------------------------

function renderCaseScreen(c) {
  caseScreen.innerHTML = "";

  const statusLine = c.immediate_action === "HOLD" ? "PAYMENT HELD" : c.immediate_action;
  const header = document.createElement("div");
  header.innerHTML = `
    <div class="case-header">
      <div>
        <div class="case-title">Case #${c.case_id.slice(0, 8)}${
          c.data_source === "AMLSIM_REAL"
            ? ' <span class="badge badge-AMLSIM">REAL (AMLSim)</span>'
            : ""
        }</div>
        <div class="case-amount">${fmtMoney(c.amount)} transfer · ${statusLine}</div>
      </div>
      <span class="badge badge-${c.priority || "LOW"}">${c.priority || "n/a"} &middot; SLA ${slaText(c.sla_deadline)}</span>
    </div>
    <div class="case-scenario">Potential typology: ${c.likely_scenario}${
      c.scenario_evidence.length ? ` (triggered by ${c.scenario_evidence.join(", ")})` : ""
    }</div>
    ${SCENARIO_DESCRIPTIONS[c.likely_scenario]
      ? `<div class="case-scenario-description">${SCENARIO_DESCRIPTIONS[c.likely_scenario]}</div>`
      : ""}
  `;
  caseScreen.appendChild(header);

  if (c.evidence_incomplete_warnings.length) {
    const warn = document.createElement("div");
    warn.className = "warning-banner";
    warn.textContent = "⚠ " + c.evidence_incomplete_warnings.join(" / ");
    caseScreen.appendChild(warn);
  }

  const layout = document.createElement("div");
  layout.className = "case-layout";
  layout.appendChild(buildSidebar(c));

  const main = document.createElement("div");
  main.className = "case-main";

  const overviewPanel = buildOverviewPanel(c);
  const evidencePanel = document.createElement("div");
  evidencePanel.className = "tab-panel hidden";
  evidencePanel.dataset.panel = "evidence";
  evidencePanel.innerHTML = '<div class="empty">loading…</div>';
  const timelinePanel = document.createElement("div");
  timelinePanel.className = "tab-panel hidden";
  timelinePanel.dataset.panel = "timeline";
  timelinePanel.innerHTML = '<div class="empty">loading…</div>';
  const relatedPanel = buildRelatedPanel(c);
  const auditPanel = buildAuditPanel(c);

  const panels = {
    overview: overviewPanel, evidence: evidencePanel, timeline: timelinePanel,
    related: relatedPanel, audit: auditPanel,
  };

  main.appendChild(buildTabBar(c, panels));
  Object.values(panels).forEach((p) => main.appendChild(p));
  main.appendChild(buildDecisionPanel(c));

  layout.appendChild(main);
  layout.appendChild(buildCopilotPanel(c));
  caseScreen.appendChild(layout);
}

let _returnToView = "dashboard";

async function openCase(caseId) {
  _returnToView = dashboardView.classList.contains("hidden") ? "cases" : "dashboard";
  const c = await api(`/api/cases/${caseId}`);
  renderCaseScreen(c);
  dashboardView.classList.add("hidden");
  queueView.classList.add("hidden");
  caseView.classList.remove("hidden");
}

backBtn.addEventListener("click", async () => {
  caseView.classList.add("hidden");
  showView(_returnToView);
  if (_returnToView === "dashboard") await loadDashboard();
  else await loadQueue();
});

(async function init() {
  reasonCodes = await api("/api/reason-codes");
  await loadDashboard();
})();
