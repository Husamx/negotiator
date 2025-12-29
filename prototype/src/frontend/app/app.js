const state = {
  caseId: null,
  caseData: null,
  runs: [],
  personaDistribution: null,
};

const navLinks = document.querySelectorAll(".nav-link");
const panels = document.querySelectorAll(".panel");
const debugToggle = document.getElementById("debugToggle");
const debugNav = document.getElementById("debugNav");

navLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.target;
    setActivePanel(target);
  });
});

debugToggle.addEventListener("change", () => {
  debugNav.hidden = !debugToggle.checked;
  if (debugToggle.checked) {
    setActivePanel("debug");
  }
});

function setActivePanel(id) {
  panels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === id);
  });
}

function updateStatus(message) {
  const el = document.getElementById("caseStatus");
  el.textContent = message;
}

function formatJson(obj) {
  return JSON.stringify(obj, null, 2);
}

function generateCaseId() {
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return "case-" + Math.random().toString(16).slice(2);
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function parseValue(raw) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return "";
  const num = Number(trimmed);
  if (!Number.isNaN(num) && trimmed.match(/^[-+]?[0-9]*\.?[0-9]+$/)) return num;
  return trimmed;
}

function parseParamValue(valueType, raw) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return "";
  if (valueType === "NUMBER" || valueType === "MONEY") {
    const num = Number(trimmed);
    return Number.isNaN(num) ? trimmed : num;
  }
  if (valueType === "BOOLEAN") {
    return trimmed.toLowerCase() === "true" || trimmed === "1";
  }
  return trimmed;
}

function getControlsFromInputs() {
  return {
    outcome_vs_agreement: parseFloat(document.getElementById("outcome_vs_agreement").value || 0.5),
    speed_vs_thoroughness: parseFloat(document.getElementById("speed_vs_thoroughness").value || 0.5),
    risk_tolerance: parseFloat(document.getElementById("risk_tolerance").value || 0.5),
    relationship_sensitivity: parseFloat(document.getElementById("relationship_sensitivity").value || 0.5),
    info_sharing: parseFloat(document.getElementById("info_sharing").value || 0.5),
    creativity_vs_discipline: parseFloat(document.getElementById("creativity_vs_discipline").value || 0.5),
    constraint_confidence: parseFloat(document.getElementById("constraint_confidence").value || 0.5),
  };
}

const userIssuesEditor = document.getElementById("userIssuesEditor");
const counterpartyIssuesEditor = document.getElementById("counterpartyIssuesEditor");
const parametersEditor = document.getElementById("parametersEditor");
const objectiveVectorSection = document.getElementById("objectiveVectorSection");
const objectiveSingleSection = document.getElementById("objectiveSingleSection");
const objectiveType = document.getElementById("objectiveType");

function createIssueRow(issue = {}, onChange = null) {
  const row = document.createElement("div");
  row.className = "editor-row issue-row";
  row.innerHTML = `
    <div>
      <label>Issue ID</label>
      <input data-field="issue_id" value="${issue.issue_id ?? ""}" />
    </div>
    <div>
      <label>Name</label>
      <input data-field="name" value="${issue.name ?? ""}" />
    </div>
    <div>
      <label>Type</label>
      <select data-field="type">
        ${["PRICE","SALARY","DATE","SCOPE","RISK","BENEFIT","OTHER"].map((type) => `<option ${issue.type === type ? "selected" : ""} value="${type}">${type}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>Direction</label>
      <select data-field="direction">
        ${["MINIMIZE","MAXIMIZE"].map((dir) => `<option ${issue.direction === dir ? "selected" : ""} value="${dir}">${dir}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>Unit</label>
      <select data-field="unit">
        ${["GBP","USD","days","text"].map((unit) => `<option ${issue.unit === unit ? "selected" : ""} value="${unit}">${unit}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>Bounds min</label>
      <input data-field="bounds_min" value="${issue.bounds?.min ?? ""}" />
    </div>
    <div>
      <label>Bounds max</label>
      <input data-field="bounds_max" value="${issue.bounds?.max ?? ""}" />
    </div>
    <div>
      <label>&nbsp;</label>
      <button class="remove">Remove</button>
    </div>
  `;
  row.querySelector(".remove").addEventListener("click", () => {
    row.remove();
    if (onChange) onChange();
  });
  row.querySelectorAll("input, select").forEach((el) => {
    if (onChange) {
      el.addEventListener("change", onChange);
    }
  });
  const nameInput = row.querySelector("[data-field='name']");
  const idInput = row.querySelector("[data-field='issue_id']");
  nameInput.addEventListener("blur", () => {
    if (!idInput.value.trim() && nameInput.value.trim()) {
      idInput.value = slugify(nameInput.value.trim());
      if (onChange) onChange();
    }
  });
  return row;
}

function createParameterRow(param = {}) {
  const row = document.createElement("div");
  row.className = "editor-row param-row";
  const disclosureValue =
    param.disclosure ?? (param.class === "PREFERENCE" ? "SHAREABLE" : "PRIVATE");
  row.innerHTML = `
    <div>
      <label>Param ID</label>
      <input data-field="param_id" value="${param.param_id ?? ""}" />
    </div>
    <div>
      <label>Label</label>
      <input data-field="label" value="${param.label ?? ""}" />
    </div>
    <div>
      <label>Value Type</label>
      <select data-field="value_type">
        ${["MONEY","NUMBER","TEXT","DATE","ENUM","BOOLEAN"].map((type) => `<option ${param.value_type === type ? "selected" : ""} value="${type}">${type}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>Value</label>
      <input data-field="value" value="${param.value ?? ""}" />
    </div>
    <div>
      <label>Must never be violated?</label>
      <select data-field="class">
        ${[
          ["NON_NEGOTIABLE", "Yes - must never be violated"],
          ["HARD_IN_RUN_REVISABLE", "No - can be revised"],
          ["PREFERENCE", "No - preference / nice-to-have"],
        ]
          .map(
            ([cls, label]) =>
              `<option ${param.class === cls ? "selected" : ""} value="${cls}">${label}</option>`
          )
          .join("")}
      </select>
    </div>
    <div>
      <label>Would you ever say this to the other side?</label>
      <select data-field="disclosure">
        ${[
          ["PRIVATE", "No (private)"],
          ["SHAREABLE", "Yes (shareable)"],
          ["CONDITIONAL", "Only if asked / later"],
        ]
          .map(
            ([val, label]) =>
              `<option ${disclosureValue === val ? "selected" : ""} value="${val}">${label}</option>`
          )
          .join("")}
      </select>
    </div>
    <div>
      <label>Allow rethink</label>
      <input type="checkbox" data-field="allow_rethink" ${param.allow_rethink_suggestions ? "checked" : ""} />
    </div>
    <div>
      <label>Scope</label>
      <select data-field="scope">
        ${["OFFER","DISCLOSURE","SCHEDULE","OTHER"].map((scope) => `<option ${param.applies_to?.scope === scope ? "selected" : ""} value="${scope}">${scope}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>Issue ID</label>
      <input data-field="issue_id" value="${param.applies_to?.issue_id ?? ""}" />
    </div>
    <div>
      <label>Path</label>
      <input data-field="path" value="${param.applies_to?.path ?? ""}" />
    </div>
    <div>
      <label>&nbsp;</label>
      <button class="remove">Remove</button>
    </div>
  `;
  row.querySelector(".remove").addEventListener("click", () => {
    row.remove();
  });
  return row;
}

function ensureIssueIds(editor) {
  const rows = Array.from(editor.querySelectorAll(".issue-row"));
  const seen = new Set();
  rows.forEach((row, index) => {
    const idInput = row.querySelector("[data-field='issue_id']");
    const nameInput = row.querySelector("[data-field='name']");
    let value = idInput.value.trim();
    if (!value) {
      value = slugify(nameInput.value.trim()) || `issue_${index + 1}`;
      idInput.value = value;
    }
    let unique = value;
    let counter = 2;
    while (seen.has(unique)) {
      unique = `${value}_${counter}`;
      counter += 1;
    }
    if (unique !== value) {
      idInput.value = unique;
    }
    seen.add(unique);
  });
}

function collectIssuesFromEditor(editor) {
  ensureIssueIds(editor);
  const rows = Array.from(editor.querySelectorAll(".issue-row"));
  return rows
    .map((row) => {
      const issueId = row.querySelector("[data-field='issue_id']").value.trim();
      const name = row.querySelector("[data-field='name']").value.trim();
      const type = row.querySelector("[data-field='type']").value;
      const direction = row.querySelector("[data-field='direction']").value;
      const unit = row.querySelector("[data-field='unit']").value;
      const boundsMin = row.querySelector("[data-field='bounds_min']").value.trim();
      const boundsMax = row.querySelector("[data-field='bounds_max']").value.trim();
      const bounds = {};
      if (boundsMin !== "") bounds.min = parseValue(boundsMin);
      if (boundsMax !== "") bounds.max = parseValue(boundsMax);
      return {
        issue_id: issueId,
        name,
        type,
        direction,
        unit,
        bounds: Object.keys(bounds).length ? bounds : undefined,
      };
    })
    .filter((issue) => issue.name || issue.issue_id);
}

function collectUserIssues() {
  return collectIssuesFromEditor(userIssuesEditor);
}

function collectCounterpartyIssues() {
  return collectIssuesFromEditor(counterpartyIssuesEditor);
}

function readObjectiveMap() {
  const map = {};
  objectiveVectorSection.querySelectorAll(".objective-row").forEach((row) => {
    const issueId = row.dataset.issueId;
    map[issueId] = {
      target: row.querySelector("[data-field='target']").value,
      reservation: row.querySelector("[data-field='reservation']").value,
      weight: row.querySelector("[data-field='weight']").value,
    };
  });
  return map;
}

function renderObjectiveInputs() {
  ensureIssueIds(userIssuesEditor);
  const type = objectiveType.value;
  objectiveVectorSection.hidden = type !== "OFFER_VECTOR";
  objectiveSingleSection.hidden = type !== "SINGLE_VALUE";

  if (type !== "OFFER_VECTOR") return;

  const current = readObjectiveMap();
  const issues = collectUserIssues();
  objectiveVectorSection.innerHTML = "";
  issues.forEach((issue) => {
    const existing = current[issue.issue_id] || {};
    const row = document.createElement("div");
    row.className = "editor-row objective-row";
    row.dataset.issueId = issue.issue_id;
    row.innerHTML = `
      <div>
        <label>${issue.name || issue.issue_id}</label>
        <div class="mini">${issue.issue_id}</div>
      </div>
      <div>
        <label>Target</label>
        <input data-field="target" value="${existing.target ?? ""}" />
      </div>
      <div>
        <label>Reservation</label>
        <input data-field="reservation" value="${existing.reservation ?? ""}" />
      </div>
      <div>
        <label>Weight</label>
        <input data-field="weight" value="${existing.weight ?? "1.0"}" />
      </div>
    `;
    objectiveVectorSection.appendChild(row);
  });
}

function collectObjectives() {
  const type = objectiveType.value;
  const noDealAcceptable = document.getElementById("noDealAcceptable").checked;
  const issues = collectUserIssues();
  const issueWeights = {};

  if (type === "SINGLE_VALUE") {
    const targetRaw = document.getElementById("objectiveTargetSingle").value;
    const reservationRaw = document.getElementById("objectiveReservationSingle").value;
    issues.forEach((issue) => (issueWeights[issue.issue_id] = 1.0));
    return {
      target: { type, value: parseValue(targetRaw) },
      reservation: { type, value: parseValue(reservationRaw) },
      no_deal_acceptable: noDealAcceptable,
      issue_weights: issueWeights,
    };
  }

  const target = {};
  const reservation = {};
  objectiveVectorSection.querySelectorAll(".objective-row").forEach((row) => {
    const issueId = row.dataset.issueId;
    const targetVal = row.querySelector("[data-field='target']").value;
    const reservationVal = row.querySelector("[data-field='reservation']").value;
    const weightVal = row.querySelector("[data-field='weight']").value;
    target[issueId] = parseValue(targetVal);
    reservation[issueId] = parseValue(reservationVal);
    issueWeights[issueId] = parseFloat(weightVal || "1.0");
  });

  return {
    target: { type, value: target },
    reservation: { type, value: reservation },
    no_deal_acceptable: noDealAcceptable,
    issue_weights: issueWeights,
  };
}

function collectParameters() {
  const rows = Array.from(parametersEditor.querySelectorAll(".param-row"));
  return rows
    .map((row) => {
      const paramId = row.querySelector("[data-field='param_id']").value.trim();
      const label = row.querySelector("[data-field='label']").value.trim();
      const valueType = row.querySelector("[data-field='value_type']").value;
      const valueRaw = row.querySelector("[data-field='value']").value;
      const klass = row.querySelector("[data-field='class']").value;
      const disclosure = row.querySelector("[data-field='disclosure']").value;
      const allowRethink = row.querySelector("[data-field='allow_rethink']").checked;
      const scope = row.querySelector("[data-field='scope']").value;
      const issueId = row.querySelector("[data-field='issue_id']").value.trim();
      const path = row.querySelector("[data-field='path']").value.trim();
      if (!paramId && !label) return null;
      return {
        param_id: paramId || slugify(label) || `param_${Math.random().toString(16).slice(2, 6)}`,
        label,
        value_type: valueType,
        value: parseParamValue(valueType, valueRaw),
        class: klass,
        disclosure: disclosure,
        allow_rethink_suggestions: allowRethink,
        applies_to: {
          scope,
          issue_id: issueId || undefined,
          path: path || undefined,
        },
      };
    })
    .filter(Boolean);
}

function validateCaseInputs() {
  const missing = [];
  const topic = document.getElementById("topic").value.trim();
  if (!topic) missing.push("topic");

  const userIssues = collectUserIssues();
  const counterpartyIssues = collectCounterpartyIssues();
  if (!userIssues.length) missing.push("user issues");
  if (!counterpartyIssues.length) missing.push("counterparty issues");
  if (userIssues.some((issue) => !issue.name)) missing.push("user issue name");
  if (counterpartyIssues.some((issue) => !issue.name)) missing.push("counterparty issue name");

  const objectives = collectObjectives();
  if (objectiveType.value === "SINGLE_VALUE") {
    if (objectives.target.value === "") missing.push("objective target");
    if (objectives.reservation.value === "") missing.push("objective reservation");
  } else {
    const targetValues = Object.values(objectives.target.value || {});
    const reservationValues = Object.values(objectives.reservation.value || {});
    if (targetValues.some((v) => v === "")) missing.push("objective target" );
    if (reservationValues.some((v) => v === "")) missing.push("objective reservation");
  }

  return missing;
}

function setIssues(editor, issues, onChange = null) {
  editor.innerHTML = "";
  issues.forEach((issue) => editor.appendChild(createIssueRow(issue, onChange)));
  if (!issues.length) {
    editor.appendChild(createIssueRow({}, onChange));
  }
  if (onChange) onChange();
}

function setUserIssues(issues) {
  setIssues(userIssuesEditor, issues, renderObjectiveInputs);
}

function setCounterpartyIssues(issues) {
  setIssues(counterpartyIssuesEditor, issues, null);
}

function setParameters(params) {
  parametersEditor.innerHTML = "";
  params.forEach((param) => parametersEditor.appendChild(createParameterRow(param)));
  if (!params.length) {
    parametersEditor.appendChild(createParameterRow());
  }
}

function setObjectives(objectives) {
  objectiveType.value = objectives.target?.type || "OFFER_VECTOR";
  document.getElementById("noDealAcceptable").checked = !!objectives.no_deal_acceptable;

  if (objectiveType.value === "SINGLE_VALUE") {
    document.getElementById("objectiveTargetSingle").value = objectives.target?.value ?? "";
    document.getElementById("objectiveReservationSingle").value = objectives.reservation?.value ?? "";
  }
  renderObjectiveInputs();

  if (objectiveType.value === "OFFER_VECTOR") {
    const target = objectives.target?.value || {};
    const reservation = objectives.reservation?.value || {};
    const weights = objectives.issue_weights || {};
    objectiveVectorSection.querySelectorAll(".objective-row").forEach((row) => {
      const issueId = row.dataset.issueId;
      row.querySelector("[data-field='target']").value = target[issueId] ?? "";
      row.querySelector("[data-field='reservation']").value = reservation[issueId] ?? "";
      row.querySelector("[data-field='weight']").value = weights[issueId] ?? "1.0";
    });
  }
}

function loadSampleCase() {
  const sampleIssues = [
    {
      issue_id: "salary",
      name: "Base Salary",
      type: "SALARY",
      direction: "MAXIMIZE",
      unit: "USD",
      bounds: { min: 140000, max: 160000 },
    },
  ];
  const sampleCounterpartyIssues = [
    {
      issue_id: "salary",
      name: "Base Salary",
      type: "SALARY",
      direction: "MINIMIZE",
      unit: "USD",
      bounds: { min: 110000, max: 130000 },
    },
  ];
  const sampleObjectives = {
    target: { type: "OFFER_VECTOR", value: { salary: 140000 } },
    reservation: { type: "OFFER_VECTOR", value: { salary: 120000 } },
    no_deal_acceptable: false,
    issue_weights: { salary: 1.0 },
  };
  const sampleParameters = [
    {
      param_id: "P_MIN_BASE",
      label: "Minimum base salary",
      value_type: "MONEY",
      value: 120000,
      class: "NON_NEGOTIABLE",
      disclosure: "PRIVATE",
      allow_rethink_suggestions: false,
      applies_to: { scope: "OFFER", issue_id: "salary" },
    },
  ];
  document.getElementById("topic").value = "Negotiate job offer compensation";
  document.getElementById("domain").value = "JOB_OFFER_COMP";
  document.getElementById("channel").value = "EMAIL";

  setUserIssues(sampleIssues);
  setCounterpartyIssues(sampleCounterpartyIssues);
  setObjectives(sampleObjectives);
  setParameters(sampleParameters);
}

document.getElementById("loadSample").addEventListener("click", loadSampleCase);

const addUserIssueButton = document.getElementById("addUserIssue");
if (addUserIssueButton) {
  addUserIssueButton.addEventListener("click", () => {
    const editor = document.getElementById("userIssuesEditor");
    if (!editor) return;
    editor.appendChild(createIssueRow({}, renderObjectiveInputs));
    renderObjectiveInputs();
  });
}

const addCounterpartyIssueButton = document.getElementById("addCounterpartyIssue");
if (addCounterpartyIssueButton) {
  addCounterpartyIssueButton.addEventListener("click", () => {
    const editor = document.getElementById("counterpartyIssuesEditor");
    if (!editor) return;
    editor.appendChild(createIssueRow({}, null));
  });
}

document.getElementById("addParameter").addEventListener("click", () => {
  parametersEditor.appendChild(createParameterRow());
});

objectiveType.addEventListener("change", renderObjectiveInputs);

const createCaseBtn = document.getElementById("createCase");
createCaseBtn.addEventListener("click", async () => {
  const missing = validateCaseInputs();
  if (missing.length) {
    updateStatus(`Missing: ${missing.join(", ")}`);
    return;
  }
  try {
    const userIssues = collectUserIssues();
    const counterpartyIssues = collectCounterpartyIssues();
    const objectives = collectObjectives();
    const parameters = collectParameters();
    const caseId = generateCaseId();
    const payload = {
      case_id: caseId,
      revision: 1,
      created_at: new Date().toISOString(),
      status: "DRAFT",
      topic: document.getElementById("topic").value,
      domain: document.getElementById("domain").value,
      channel: document.getElementById("channel").value,
      parameters: parameters,
      objectives: objectives,
      user_issues: userIssues,
      counterparty_issues: counterpartyIssues,
      counterparty_assumptions: {
        calibration: { answers: {} },
        persona_distribution: state.personaDistribution || [
          { persona_id: "POLICY_BOUND", weight: 0.6 },
          { persona_id: "COLLABORATIVE", weight: 0.4 },
        ],
        notes: "",
      },
      controls: getControlsFromInputs(),
      mode: {
        auto_enabled: true,
        advanced_enabled: true,
        enabled_strategies: [],
        pinned_strategy: null,
      },
    };

    const res = await fetch("/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.caseId = data.case_id;
    state.caseData = data;
    updateStatus(`Case created: ${state.caseId}`);
  } catch (err) {
    updateStatus(`Error: ${err.message}`);
  }
});

document.getElementById("validateCase").addEventListener("click", () => {
  const missing = validateCaseInputs();
  updateStatus(missing.length ? `Missing: ${missing.join(", ")}` : "Ready to save.");
});

document.getElementById("calibratePersona").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const answers = {
    policy_rigidity: document.getElementById("policyRigidity").value || "medium",
    cooperativeness: document.getElementById("cooperativeness").value || "medium",
    time_pressure: document.getElementById("timePressure").value || "medium",
    authority_clarity: document.getElementById("authorityClarity").value || "medium",
  };
  const res = await fetch(`/cases/${state.caseId}/persona/calibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ calibration: { answers } }),
  });
  const data = await res.json();
  state.personaDistribution = data.persona_distribution;
  document.getElementById("personaDistribution").textContent = formatJson(data);
});

document.getElementById("saveControls").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const controls = getControlsFromInputs();
  const res = await fetch(`/cases/${state.caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ controls }),
  });
  const data = await res.json();
  state.caseData = data;
  updateStatus("Controls saved.");
});

document.getElementById("runSim").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const runs = parseInt(document.getElementById("runs").value, 10) || 1;
  const maxTurns = parseInt(document.getElementById("max_turns").value, 10);
  const mode = document.getElementById("mode").value;
  document.getElementById("runProgress").textContent = "Running...";
  const res = await fetch(`/cases/${state.caseId}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runs, max_turns: maxTurns, mode }),
  });
  const data = await res.json();
  state.runs = data;
  renderRuns();
  document.getElementById("runProgress").textContent = `Completed ${data.length} runs.`;
});

function renderRuns() {
  const table = document.getElementById("runsTable");
  table.innerHTML = "";
  state.runs.forEach((run) => {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<strong>${run.outcome}</strong> | persona: ${run.persona_id} | utility: ${run.user_utility.toFixed(2)} | turns: ${run.turns.length}`;
    table.appendChild(row);
  });
}

document.getElementById("loadInsights").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  try {
    const res = await fetch(`/cases/${state.caseId}/insights`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    document.getElementById("insightsOutput").textContent = formatJson(data);
    renderInsights(data);
    const status = document.getElementById("insightsStatus");
    if (status) status.textContent = `Loaded ${data?.turns_to_termination?.length || 0} runs.`;
  } catch (err) {
    const status = document.getElementById("insightsStatus");
    if (status) status.textContent = `Error: ${err.message}`;
  }
});

document.getElementById("loadStrategies").addEventListener("click", async () => {
  const res = await fetch("/strategies");
  const data = await res.json();
  const grid = document.getElementById("strategyGrid");
  grid.innerHTML = "";
  data.forEach((strategy) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="title">${strategy.ui.card_title}</div>
      <div class="meta">${strategy.category} • ${strategy.strategy_id}</div>
      <div>${strategy.summary}</div>
    `;
    grid.appendChild(card);
  });
});

document.getElementById("loadTrace").addEventListener("click", async () => {
  if (!state.runs.length) {
    updateStatus("Run a simulation first.");
    return;
  }
  const runId = state.runs[state.runs.length - 1].run_id;
  const res = await fetch(`/runs/${runId}/trace`);
  const data = await res.json();
  document.getElementById("traceOutput").textContent = formatJson(data);
  renderTraceFlow(data);
});

loadSampleCase();

function renderInsights(data) {
  renderOutcomeSummary(data);
  renderOutcomeChart(data);
  renderBucketInsights(data);
}

function renderOutcomeSummary(data) {
  const container = document.getElementById("insightsSummary");
  if (!container) return;
  container.innerHTML = "";
  const rates = data?.outcome_rates?.overall || {};
  const turns = Array.isArray(data?.turns_to_termination) ? data.turns_to_termination : [];
  const utilities = Array.isArray(data?.utility_distribution) ? data.utility_distribution : [];
  const totalRuns = turns.length;

  const cards = [
    { label: "PASS Rate", value: formatPercent(rates.PASS) },
    { label: "NEUTRAL Rate", value: formatPercent(rates.NEUTRAL) },
    { label: "FAIL Rate", value: formatPercent(rates.FAIL) },
    { label: "Avg Turns", value: formatNumber(mean(turns), 1) },
    { label: "Median Utility", value: formatNumber(median(utilities), 2) },
    { label: "Runs", value: totalRuns || 0 },
  ];

  cards.forEach((card) => {
    const el = document.createElement("div");
    el.className = "insight-card";
    el.innerHTML = `
      <div class="insight-label">${card.label}</div>
      <div class="insight-value">${card.value}</div>
    `;
    container.appendChild(el);
  });
}

function renderOutcomeChart(data) {
  const container = document.getElementById("outcomeChart");
  if (!container) return;
  container.innerHTML = "";
  const rates = data?.outcome_rates?.overall || {};
  const outcomes = [
    { key: "PASS", value: rates.PASS ?? 0, className: "pass" },
    { key: "NEUTRAL", value: rates.NEUTRAL ?? 0, className: "neutral" },
    { key: "FAIL", value: rates.FAIL ?? 0, className: "fail" },
  ];
  outcomes.forEach((item) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const label = document.createElement("div");
    label.className = "bar-label";
    label.textContent = item.key;
    const barWrap = document.createElement("div");
    barWrap.className = "bar-track";
    const bar = document.createElement("div");
    bar.className = `bar-fill ${item.className}`;
    bar.style.width = `${Math.round((item.value || 0) * 100)}%`;
    bar.textContent = formatPercent(item.value);
    barWrap.appendChild(bar);
    row.appendChild(label);
    row.appendChild(barWrap);
    container.appendChild(row);
  });
}

function renderBucketInsights(data) {
  const passEl = document.getElementById("bucketPass");
  const neutralEl = document.getElementById("bucketNeutral");
  const failEl = document.getElementById("bucketFail");
  if (!passEl || !neutralEl || !failEl) return;
  passEl.innerHTML = "";
  neutralEl.innerHTML = "";
  failEl.innerHTML = "";

  const buckets = data?.bucket_insights || {};
  renderBucketList(passEl, buckets.PASS, "No PASS insights yet.");
  renderBucketList(neutralEl, buckets.NEUTRAL, "No NEUTRAL insights yet.");
  renderBucketList(failEl, buckets.FAIL, "No FAIL insights yet.");
}

function renderBucketList(container, bucketData, emptyText) {
  const insights = bucketData?.insights || [];
  if (!insights.length) {
    container.textContent = emptyText;
    return;
  }
  insights.forEach((item) => {
    const row = document.createElement("div");
    row.className = "insight-row";
    const examples = Array.isArray(item.example_snippets) ? item.example_snippets.slice(0, 2) : [];
    const exampleText = examples.length ? `Example: ${examples.join(" · ")}` : "";
    row.innerHTML = `
      <div class="insight-row-title">${item.claim}</div>
      <div class="insight-row-meta">Support ${item.support_count || 0}</div>
      ${exampleText ? `<div class="insight-row-meta">${exampleText}</div>` : ""}
    `;
    container.appendChild(row);
  });
}

function mean(values) {
  if (!values.length) return 0;
  const total = values.reduce((sum, value) => sum + value, 0);
  return total / values.length;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
}

function formatPercent(value) {
  if (value === undefined || value === null) return "0%";
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "0";
  return Number(value).toFixed(digits);
}
function renderTraceFlow(trace) {
  const container = document.getElementById("traceFlow");
  container.innerHTML = "";
  const calls = trace?.agent_call_traces || [];
  if (!calls.length) {
    container.textContent = "No agent calls recorded.";
    return;
  }
  calls.forEach((call) => {
    const agent = call.agent_name || "Agent";
    const side = agent === "UserProxy" ? "left" : agent === "Counterparty" ? "right" : "center";
    const row = document.createElement("div");
    row.className = "trace-row";
    row.dataset.side = side;

    const card = document.createElement("div");
    card.className = `trace-card ${agent.toLowerCase()}`;
    card.dataset.agent = agent;

    const header = document.createElement("div");
    header.className = "trace-header";
    const title = document.createElement("div");
    title.className = "trace-agent";
    title.textContent = agent;
    const meta = document.createElement("div");
    meta.className = "trace-meta";
    const turn = call.prompt_variables?.turn;
    const phase = call.prompt_variables?.phase;
    meta.textContent = `${turn ? `Turn ${turn}` : "Turn ?"}${phase ? ` · ${phase}` : ""} · ${call.prompt_id}@${call.prompt_version}`;
    header.appendChild(title);
    header.appendChild(meta);

    const message = document.createElement("div");
    message.className = "trace-message";
    const parsed = call.parsed_output || {};
    const actionType = parsed.action?.type;
    if (actionType) {
      const actionBadge = document.createElement("div");
      actionBadge.className = "trace-action";
      actionBadge.textContent = `Action: ${actionType}`;
      message.appendChild(actionBadge);
    }
    const messageText = parsed.message_text || parsed.text || "";
    const messageBody = document.createElement("div");
    messageBody.className = "trace-message-text";
    messageBody.textContent = messageText ? messageText : JSON.stringify(parsed, null, 2);
    message.appendChild(messageBody);

    const promptDetails = document.createElement("details");
    promptDetails.className = "trace-details";
    const promptSummary = document.createElement("summary");
    promptSummary.textContent = "Prompt";
    const promptBody = document.createElement("pre");
    promptBody.textContent = call.prompt_text || "";
    promptDetails.appendChild(promptSummary);
    promptDetails.appendChild(promptBody);

    const userPromptDetails = document.createElement("details");
    userPromptDetails.className = "trace-details";
    const userPromptSummary = document.createElement("summary");
    userPromptSummary.textContent = "User Prompt";
    const userPromptBody = document.createElement("pre");
    const userMessage = (call.messages || []).find((msg) => msg.role === "user");
    userPromptBody.textContent = userMessage?.content || "";
    userPromptDetails.appendChild(userPromptSummary);
    userPromptDetails.appendChild(userPromptBody);

    const historyButton = document.createElement("button");
    historyButton.className = "trace-history";
    historyButton.textContent = "Message History";
    historyButton.addEventListener("click", () => {
      const history = call.messages || [];
      const win = window.open("", "_blank");
      if (!win) return;
      win.document.title = "Message History";
      const pre = win.document.createElement("pre");
      pre.textContent = JSON.stringify(history, null, 2);
      win.document.body.appendChild(pre);
    });

    const outputDetails = document.createElement("details");
    outputDetails.className = "trace-details";
    const outputSummary = document.createElement("summary");
    outputSummary.textContent = "Output";
    const outputBody = document.createElement("pre");
    outputBody.textContent = JSON.stringify(parsed, null, 2);
    outputDetails.appendChild(outputSummary);
    outputDetails.appendChild(outputBody);

    card.appendChild(header);
    card.appendChild(message);
    card.appendChild(historyButton);
    card.appendChild(promptDetails);
    card.appendChild(userPromptDetails);
    card.appendChild(outputDetails);
    row.appendChild(card);
    container.appendChild(row);
  });
}
