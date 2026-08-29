/** Incident Investigator — product UX */

let currentResult = null;
let selectedCaseId = null;
let currentMetadata = null;
let benchmarkCases = [];
let caseStatuses = {};
let sessionResults = {};
let investigatingCaseId = null;
let evidenceExpanded = false;
let loaderMessageTimer = null;

const LOADER_MESSAGES = [
  "Processing: ingesting distributed logs",
  "Processing: reconstructing workflow timeline",
  "Processing: evaluating process divergence",
  "Processing: checking safety gates",
  "Processing: hydrating evidence",
  "Processing: preparing incident report",
];

const caseSelectEl = document.getElementById("case-select");
const benchmarkGridEl = document.getElementById("benchmark-case-grid");
const benchmarkOverviewEl = document.getElementById("benchmark-overview");
const investigateBtn = document.getElementById("investigate-btn");
const inputErrorEl = document.getElementById("input-error");
const loadingOverlay = document.getElementById("loading-overlay");
const payloadInput = document.getElementById("payload-input");
const storyRoot = document.getElementById("story-root");
const investigateView = document.getElementById("investigate-view");
const evaluationView = document.getElementById("evaluation-view");

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || response.statusText || "Request failed");
  }
  return body;
}

function showError(message) {
  inputErrorEl.textContent = message;
  inputErrorEl.classList.remove("hidden");
}

function clearError() {
  inputErrorEl.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function titleCase(text) {
  return text.replace(/\b\w/g, (char) => char.toUpperCase());
}

function caseDisplayName(caseId) {
  return caseId.replace("case_", "Case ");
}

function caseNumberLabel(caseNumber) {
  return String(caseNumber).padStart(2, "0");
}

function formatDeltaPp(delta) {
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(2)} pp`;
}

function stopLoaderMessages() {
  if (loaderMessageTimer) {
    clearInterval(loaderMessageTimer);
    loaderMessageTimer = null;
  }
}

function startLoaderMessages() {
  stopLoaderMessages();
  const subtitleEl = document.getElementById("loading-subtitle");
  if (!subtitleEl) return;
  let index = 0;
  subtitleEl.textContent = `${LOADER_MESSAGES[index]}…`;
  loaderMessageTimer = setInterval(() => {
    index = (index + 1) % LOADER_MESSAGES.length;
    subtitleEl.textContent = `${LOADER_MESSAGES[index]}…`;
  }, 3200);
}

function setLoading(active) {
  loadingOverlay.classList.toggle("hidden", !active);
  const canInvestigate = Boolean(selectedCaseId || payloadInput.value.trim());
  investigateBtn.disabled = active || !canInvestigate;
  if (active) {
    startLoaderMessages();
  } else {
    stopLoaderMessages();
  }
}

function setView(view) {
  const isInvestigate = view === "investigate";
  investigateView.classList.toggle("hidden", !isInvestigate);
  evaluationView.classList.toggle("hidden", isInvestigate);
  document.getElementById("nav-investigate").classList.toggle("active", isInvestigate);
  document.getElementById("nav-evaluation").classList.toggle("active", !isInvestigate);
}

function renderCasePreview(metadata) {
  if (!metadata) return;
  document.getElementById("preview-case-name").textContent = caseDisplayName(metadata.case_id);
  document.getElementById("preview-process-name").textContent = titleCase(metadata.process_name.replace(/_/g, " "));
  document.getElementById("preview-log-count").textContent = `${metadata.log_count} logs`;
}

function renderCaseSelect() {
  caseSelectEl.innerHTML = benchmarkCases.map((item) => `
    <option value="${escapeHtml(item.case_id)}">
      ${escapeHtml(caseDisplayName(item.case_id))} — ${escapeHtml(titleCase(item.process_label))}
    </option>`).join("");
  if (selectedCaseId) {
    caseSelectEl.value = selectedCaseId;
  }
}

function renderBenchmarkGrid() {
  benchmarkGridEl.innerHTML = benchmarkCases.map((item) => {
    const isActive = item.case_id === selectedCaseId;
    const isInvestigated = caseStatuses[item.case_id] === "investigated";
    const isInvestigating = investigatingCaseId === item.case_id;
    return `
      <button type="button"
        class="benchmark-card ${isActive ? "active" : ""} ${isInvestigated ? "investigated" : ""} ${isInvestigating ? "investigating" : ""}"
        data-case-id="${escapeHtml(item.case_id)}"
        role="option"
        aria-selected="${isActive}">
        <span class="benchmark-card-num">${caseNumberLabel(item.case_number)}</span>
        <span class="benchmark-card-process">${escapeHtml(titleCase(item.process_label))}</span>
      </button>`;
  }).join("");

  benchmarkGridEl.querySelectorAll(".benchmark-card").forEach((btn) => {
    btn.addEventListener("click", () => selectCase(btn.dataset.caseId));
  });
}

function refreshCaseSelectors() {
  renderCaseSelect();
  renderBenchmarkGrid();
}

function renderBenchmarkOverview(overview) {
  benchmarkOverviewEl.classList.remove("empty-state");
  const metricRows = overview.metrics.map((row) => `
    <tr><td>${escapeHtml(row.label)}</td><td>${row.value_percent.toFixed(2)}%</td></tr>`).join("");

  const holdoutBlock = overview.holdout ? `
    <section class="eval-split-section holdout" aria-labelledby="eval-holdout-title">
      <span class="eval-split-badge holdout">Unseen holdout</span>
      <h3 class="eval-split-title" id="eval-holdout-title">Generalization benchmark (not used for tuning)</h3>
      <p class="eval-split-desc">
        ${escapeHtml(overview.holdout.note)}
        Source: <span class="mono">${escapeHtml(overview.holdout.source)}</span>
      </p>
      <div class="eval-scores">
        <div class="eval-score"><span class="eval-label">Unseen cases</span><span class="eval-value">${overview.holdout.case_count}</span></div>
        <div class="eval-score"><span class="eval-label">Stage 0 IQS</span><span class="eval-value">${overview.holdout.stage_0_iqs_percent.toFixed(2)}%</span></div>
        <div class="eval-score"><span class="eval-label">Stage 3 IQS</span><span class="eval-value">${overview.holdout.stage_3_iqs_percent.toFixed(2)}%</span></div>
        <div class="eval-score"><span class="eval-label">Delta</span><span class="eval-value">${formatDeltaPp(overview.holdout.delta_pp)}</span></div>
      </div>
      <table class="eval-table eval-holdout-table">
        <thead><tr><th>Checkpoint</th><th>Mean IQS</th></tr></thead>
        <tbody>
          <tr><td>Stage 0 frozen baseline</td><td>${overview.holdout.stage_0_iqs_percent.toFixed(2)}%</td></tr>
          <tr><td>Stage 3 (adjudication + gates)</td><td>${overview.holdout.stage_3_iqs_percent.toFixed(2)}%</td></tr>
        </tbody>
      </table>
      <p class="eval-note">Net change vs Stage 0: <strong>${formatDeltaPp(overview.holdout.delta_pp)}</strong>.</p>
    </section>` : "";

  benchmarkOverviewEl.innerHTML = `
    <section class="eval-split-section dev" aria-labelledby="eval-dev-title">
      <span class="eval-split-badge dev">Development benchmark</span>
      <h3 class="eval-split-title" id="eval-dev-title">15-case development benchmark</h3>
      <p class="eval-split-desc">Fixed development set used for ablation and product evaluation. Source: <span class="mono">${escapeHtml(overview.source)}</span></p>
      <div class="eval-scores">
        <div class="eval-score"><span class="eval-label">Cases</span><span class="eval-value">${overview.case_count}</span></div>
        <div class="eval-score highlight">
          <span class="eval-label">Stage 3 mean IQS</span>
          <span class="eval-value">${overview.stage_3_iqs_percent.toFixed(2)}%</span>
          <span class="eval-hero-context">Measured on a fixed 15-case development benchmark</span>
        </div>
      </div>
      <div class="eval-history">
        <h4 class="eval-history-title">IQS progression</h4>
        <p class="eval-history-desc">Mean IQS on the fixed 15-case development benchmark at each evaluation checkpoint:</p>
        <table class="eval-table eval-history-table">
          <thead><tr><th>Checkpoint</th><th>Mean IQS</th><th>Source</th></tr></thead>
          <tbody>
            <tr>
              <td>Stage 0 frozen baseline</td>
              <td>${overview.stage_0_iqs_percent.toFixed(2)}%</td>
              <td class="mono">eval_submission.json</td>
            </tr>
            <tr>
              <td>Stage 3 (adjudication + gates)</td>
              <td>${overview.stage_3_iqs_percent.toFixed(2)}%</td>
              <td class="mono">eval_submission.json</td>
            </tr>
          </tbody>
        </table>
        <p class="eval-note">Net change vs Stage 0: <strong>${formatDeltaPp(overview.delta_pp)}</strong>. Stage 0 is the frozen single-prompt baseline embedded in the submission artifact; Stage 3 adds rule-checker challenger, adjudication verifier, and deterministic gates.</p>
      </div>
      <table class="eval-table">
        <thead><tr><th>Metric</th><th>Stage 3 mean</th></tr></thead>
        <tbody>${metricRows}</tbody>
      </table>
      <p class="eval-note">${escapeHtml(overview.note)}</p>
    </section>
    ${holdoutBlock}`;
}

async function selectCase(caseId) {
  selectedCaseId = caseId;
  clearError();
  payloadInput.value = "";
  investigateBtn.disabled = false;
  caseSelectEl.value = caseId;

  if (sessionResults[caseId]) {
    showResults(sessionResults[caseId], { scroll: false });
  } else {
    storyRoot.classList.add("hidden");
    currentResult = null;
    hideSecondaryPanels();
  }

  refreshCaseSelectors();
  const metadata = await fetchJson(`/api/cases/${caseId}/preview`);
  currentMetadata = metadata;
  renderCasePreview(metadata);
}

function hideSecondaryPanels() {
  document.getElementById("evidence-explorer-panel").classList.add("hidden");
  document.getElementById("postmortem-panel").classList.add("hidden");
}

function roleClass(role) {
  if (role.includes("culprit") && role.includes("evidence")) return "culprit-evidence";
  if (role.includes("culprit")) return "culprit";
  if (role.includes("evidence")) return "evidence";
  return "context";
}

function evidenceCardHtml(log) {
  return `
    <article class="evidence-card" data-log-id="${escapeHtml(log.log_id)}" tabindex="0" role="button">
      <div class="evidence-card-top">
        <span class="log-id-link">${escapeHtml(log.log_id)}</span>
      </div>
      <div class="msg">${escapeHtml(log.message)}</div>
    </article>`;
}

function bindLogInteractions(container, logs) {
  container.querySelectorAll(".evidence-card, .mechanism-node").forEach((el) => {
    el.addEventListener("click", () => showLogDetail(el.dataset.logId, logs));
  });
}

function showLogDetail(logId, logs) {
  const log = logs.find((entry) => entry.log_id === logId);
  const detailEl = document.getElementById("log-detail");
  detailEl.classList.remove("hidden-detail", "empty-state");
  document.querySelectorAll(".evidence-card, .mechanism-node").forEach((card) => {
    card.classList.toggle("selected", card.dataset.logId === logId);
  });
  detailEl.textContent = log ? JSON.stringify(log, null, 2) : "Log not found.";
}

function renderHero(result) {
  const story = result.story;
  const processName = result.metadata?.process_name || "";
  document.getElementById("hero-process-name").textContent = titleCase(processName.replace(/_/g, " "));
  document.getElementById("hero-failure-title").textContent = story.failure_title;
  document.getElementById("hero-divergence").textContent = story.divergence_step;
  document.getElementById("hero-root-cause").textContent = story.root_cause_label;
  document.getElementById("hero-explanation").textContent = story.why_brief || story.why_it_failed || story.headline;
  document.getElementById("hero-case-id").textContent = result.case_id;
}

function renderKeyEvidence(result) {
  const logsById = Object.fromEntries(result.hydrated_logs.map((log) => [log.log_id, log]));
  const keyIds = result.story.key_evidence_log_ids;
  const keyList = document.getElementById("key-evidence-list");
  const keyLogs = keyIds.map((id) => logsById[id]).filter(Boolean);
  keyList.innerHTML = keyLogs.map(evidenceCardHtml).join("");
  bindLogInteractions(keyList, result.hydrated_logs);

  const diagnosticLogs = result.hydrated_logs.filter(
    (log) => log.role !== "context" || result.diagnosis.evidence_log_ids.includes(log.log_id),
  );
  document.getElementById("full-evidence-list").innerHTML = diagnosticLogs.map(evidenceCardHtml).join("");
  bindLogInteractions(document.getElementById("full-evidence-list"), result.hydrated_logs);
}

const MECHANISM_ROLE_LABELS = {
  failure: "Root cause",
  consequence: "Downstream consequence",
  precursor: "Precursor signal",
};

function renderMechanismChain(result) {
  const chain = result.story.mechanism_chain;
  const container = document.getElementById("mechanism-chain");
  if (!chain.length) {
    container.innerHTML = '<p class="empty-state">No causal chain available.</p>';
    return;
  }
  container.innerHTML = chain.map((node, index) => {
    const arrow = index < chain.length - 1 ? '<div class="mechanism-arrow" aria-hidden="true">↓</div>' : "";
    const roleLabel = MECHANISM_ROLE_LABELS[node.kind] || "";
    return `
      <div class="mechanism-node ${node.kind}" data-log-id="${escapeHtml(node.log_id)}" tabindex="0" role="button">
        <span class="mechanism-role">${escapeHtml(roleLabel)}</span>
        <div class="mechanism-label">${escapeHtml(node.label)}</div>
      </div>${arrow}`;
  }).join("");
  bindLogInteractions(container, result.hydrated_logs);
}

const TRACE_TITLES = {
  analyze: "Logs analyzed",
  diagnose: "Diagnosis generated",
  validate: "Safety gates evaluated",
  evidence_retrieval: "Evidence retrieved",
  report: "Post-mortem generated",
};

function renderStoryPhases(story) {
  document.getElementById("story-phases").innerHTML = story.story_phases.map((phase, index) => `
    <div class="trace-step">
      <span class="trace-step-num">${index + 1}</span>
      <div class="trace-step-body">
        <span class="trace-step-title">${escapeHtml(TRACE_TITLES[phase.phase_id] || phase.title)}</span>
        <p class="trace-step-desc">${escapeHtml(phase.description)}</p>
      </div>
    </div>`).join("");
}

function renderPostMortem(markdown) {
  document.getElementById("post-mortem-content").innerHTML = markdownToHtml(markdown);
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  let html = "";
  let inTable = false;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      if (inTable) { html += "</table>"; inTable = false; }
      html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
    } else if (line.startsWith("# ")) {
      if (inTable) { html += "</table>"; inTable = false; }
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
    } else if (line.startsWith("|")) {
      const cells = line.split("|").filter(Boolean).map((c) => c.trim());
      if (!inTable) { html += "<table>"; inTable = true; }
      const tag = line.includes("---") ? null : (html.endsWith("<table>") ? "th" : "td");
      if (tag) html += `<tr>${cells.map((c) => `<${tag}>${escapeHtml(c)}</${tag}>`).join("")}</tr>`;
    } else if (line.trim()) {
      if (inTable) { html += "</table>"; inTable = false; }
      html += `<p>${escapeHtml(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")}</p>`;
    }
  }
  if (inTable) html += "</table>";
  return html;
}

function showResults(result, options = {}) {
  const { scroll = true } = options;
  currentResult = result;
  hideSecondaryPanels();

  if (result.case_id) {
    sessionResults[result.case_id] = result;
    caseStatuses[result.case_id] = "investigated";
    investigatingCaseId = null;
    refreshCaseSelectors();
  }

  setLoading(false);
  setView("investigate");
  storyRoot.classList.remove("hidden");

  renderHero(result);
  renderKeyEvidence(result);
  renderMechanismChain(result);
  renderPostMortem(result.post_mortem_markdown);
  renderStoryPhases(result.story);

  if (scroll) {
    document.getElementById("hero-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function runInvestigation() {
  clearError();
  const pasted = payloadInput.value.trim();
  if (!pasted && selectedCaseId) {
    investigatingCaseId = selectedCaseId;
    refreshCaseSelectors();
  }
  setLoading(true);
  try {
    let result;
    if (pasted) {
      result = await fetchJson("/api/investigate/payload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case: JSON.parse(pasted), stage: 3 }),
      });
    } else if (selectedCaseId) {
      result = await fetchJson("/api/investigate/benchmark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: selectedCaseId, stage: 3 }),
      });
    } else {
      throw new Error("Select a benchmark incident or paste incident JSON.");
    }
    showResults(result);
  } catch (error) {
    investigatingCaseId = null;
    refreshCaseSelectors();
    setLoading(false);
    showError(error.message);
  }
}

function copySummary() {
  if (currentResult) navigator.clipboard.writeText(currentResult.story.incident_summary);
}

function copyMarkdown() {
  if (currentResult) navigator.clipboard.writeText(currentResult.post_mortem_markdown);
}

function exportMarkdown() {
  if (!currentResult) return;
  const blob = new Blob([currentResult.post_mortem_markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${currentResult.case_id}_post_mortem.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportJson() {
  if (!currentResult?.post_mortem_artifact) return;
  const jsonText = JSON.stringify(currentResult.post_mortem_artifact, null, 2);
  const blob = new Blob([jsonText], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${currentResult.case_id}_post_mortem.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function init() {
  benchmarkCases = await fetchJson("/api/benchmark-cases");
  benchmarkCases.forEach((item) => {
    caseStatuses[item.case_id] = "idle";
  });

  renderCaseSelect();
  refreshCaseSelectors();

  try {
    const overview = await fetchJson("/api/benchmark-overview");
    renderBenchmarkOverview(overview);
  } catch {
    benchmarkOverviewEl.textContent = "Evaluation summary is not available.";
  }

  const viewParam = new URLSearchParams(window.location.search).get("view");
  if (viewParam === "evaluation") {
    setView("evaluation");
  }

  caseSelectEl.addEventListener("change", () => selectCase(caseSelectEl.value));
  investigateBtn.addEventListener("click", runInvestigation);
  payloadInput.addEventListener("input", () => {
    investigateBtn.disabled = !selectedCaseId && !payloadInput.value.trim();
  });

  document.getElementById("nav-investigate").addEventListener("click", () => setView("investigate"));
  document.getElementById("nav-evaluation").addEventListener("click", () => setView("evaluation"));

  document.getElementById("explore-evidence-btn").addEventListener("click", () => {
    document.getElementById("evidence-explorer-panel").classList.remove("hidden");
    document.getElementById("evidence-explorer-panel").scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("close-evidence-btn").addEventListener("click", () => {
    document.getElementById("evidence-explorer-panel").classList.add("hidden");
  });
  document.getElementById("view-postmortem-btn").addEventListener("click", () => {
    document.getElementById("postmortem-panel").classList.remove("hidden");
    document.getElementById("postmortem-panel").scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("close-postmortem-btn").addEventListener("click", () => {
    document.getElementById("postmortem-panel").classList.add("hidden");
  });
  document.getElementById("new-investigation-btn").addEventListener("click", () => {
    storyRoot.classList.add("hidden");
    hideSecondaryPanels();
    setView("investigate");
    document.getElementById("input-panel").scrollIntoView({ behavior: "smooth" });
  });

  document.getElementById("copy-summary-btn").addEventListener("click", copySummary);
  document.getElementById("copy-md-btn").addEventListener("click", copyMarkdown);
  document.getElementById("export-md-btn").addEventListener("click", exportMarkdown);
  document.getElementById("export-json-btn").addEventListener("click", exportJson);

  await selectCase("case_01");
}

init().catch((error) => showError(error.message));
