const state = {
  caseId: null,
  caseData: null,
  runs: [],
  personaDistribution: null,
  debugRunsAll: [],
  snapshotQuestions: [],
  snapshotQuestionKey: null,
  sessionId: null,
  pendingQuestion: null,
};

const navLinks = document.querySelectorAll(".nav-link");
const panels = document.querySelectorAll(".panel");
const debugToggle = document.getElementById("debugToggle");
const debugNav = document.getElementById("debugNav");
const debugRunSelect = document.getElementById("debugRunSelect");
const debugStatus = document.getElementById("debugStatus");
const debugSearchInput = document.getElementById("debugSearchInput");
const debugSearchButton = document.getElementById("debugSearchButton");
const debugSearchClear = document.getElementById("debugSearchClear");
const debugFilterFallbacks = document.getElementById("debugFilterFallbacks");
const debugFilterNonFallbacks = document.getElementById("debugFilterNonFallbacks");
const debugTraceCache = new Map();
const resetCaseButton = document.getElementById("resetCase");
const resetCounterpartyButton = document.getElementById("resetCounterparty");
const snapshotTopicInput = document.getElementById("snapshotTopic");
const snapshotDomainSelect = document.getElementById("snapshotDomain");
const snapshotChannelSelect = document.getElementById("snapshotChannel");
const snapshotQuestionsEl = document.getElementById("snapshotQuestions");
const snapshotStatus = document.getElementById("snapshotStatus");
const refreshSnapshotQuestionsBtn = document.getElementById("refreshSnapshotQuestions");
const openAdvancedCaseBtn = document.getElementById("openAdvancedCase");
const snapshotSampleCaseSelect = document.getElementById("snapshotSampleCaseSelect");
const snapshotLoadSampleBtn = document.getElementById("snapshotLoadSample");
const snapshotCreateCaseBtn = document.getElementById("snapshotCreateCase");
const snapshotSavedCaseSelect = document.getElementById("snapshotSavedCaseSelect");
const snapshotLoadSavedCaseBtn = document.getElementById("snapshotLoadSavedCase");
const snapshotDeleteSavedCasesBtn = document.getElementById("snapshotDeleteSavedCases");
const snapshotClearDraftBtn = document.getElementById("snapshotClearDraft");
const backToSnapshotBtn = document.getElementById("backToSnapshot");
const advancedTopicInput = document.getElementById("topic");
const advancedDomainSelect = document.getElementById("domain");
const advancedChannelSelect = document.getElementById("channel");
const maxQuestionsInput = document.getElementById("max_questions");
const pendingQuestionCard = document.getElementById("pendingQuestionCard");
const pendingQuestionMeta = document.getElementById("pendingQuestionMeta");
const pendingQuestionText = document.getElementById("pendingQuestionText");
const pendingQuestionAnswer = document.getElementById("pendingQuestionAnswer");
const submitQuestionAnswer = document.getElementById("submitQuestionAnswer");
const refreshQuestionsBtn = document.getElementById("refreshQuestions");
const askInfoBudgetStatus = document.getElementById("askInfoBudgetStatus");
const RUN_PREVIEW_WORDS_MAX = 5;
const RUN_PREVIEW_DELAY_CAP_MS = 120;
const RUN_PREVIEW_DELAY_MIN_MS = 30;
const RUN_PREVIEW_SWAP_MS = 6000;
const RUN_PREVIEW_POLL_MS = 2000;
const runPreviewState = {
  active: false,
  summaries: [],
  currentIndex: 0,
  wordTimer: null,
  swapTimer: null,
  pollTimer: null,
  expectedRuns: null,
  completedRuns: 0,
  baseRuns: null,
};
let snapshotQuestionTimer = null;
let questionPollTimer = null;
let draftSaveTimer = null;
const DRAFT_STORAGE_KEY = "negotiator:case_draft:v1";

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
  if (id === "snapshot") {
    maybeGenerateSnapshotQuestions();
  }
  if (id === "counterparty") {
    loadCounterpartyHints();
  }
  if (id === "simulate") {
    fetchPendingQuestion();
  }
  if (id === "debug") {
    refreshDebugRuns();
  }
}

if (openAdvancedCaseBtn) {
  openAdvancedCaseBtn.addEventListener("click", () => {
    setActivePanel("caseAdvanced");
  });
}

if (backToSnapshotBtn) {
  backToSnapshotBtn.addEventListener("click", () => {
    setActivePanel("snapshot");
  });
}

if (snapshotTopicInput) {
  snapshotTopicInput.addEventListener("input", () => {
    if (advancedTopicInput) advancedTopicInput.value = snapshotTopicInput.value;
    scheduleSnapshotQuestions();
    scheduleDraftSave();
  });
}

if (snapshotDomainSelect) {
  snapshotDomainSelect.addEventListener("change", () => {
    if (advancedDomainSelect) advancedDomainSelect.value = snapshotDomainSelect.value;
    scheduleSnapshotQuestions({ force: true });
    scheduleDraftSave();
  });
}

if (snapshotChannelSelect) {
  snapshotChannelSelect.addEventListener("change", () => {
    if (advancedChannelSelect) advancedChannelSelect.value = snapshotChannelSelect.value;
    scheduleSnapshotQuestions({ force: true });
    scheduleDraftSave();
  });
}

if (advancedTopicInput) {
  advancedTopicInput.addEventListener("input", () => {
    if (snapshotTopicInput) snapshotTopicInput.value = advancedTopicInput.value;
    scheduleSnapshotQuestions();
    scheduleDraftSave();
  });
}

if (advancedDomainSelect) {
  advancedDomainSelect.addEventListener("change", () => {
    if (snapshotDomainSelect) snapshotDomainSelect.value = advancedDomainSelect.value;
    scheduleSnapshotQuestions({ force: true });
    scheduleDraftSave();
  });
}

if (advancedChannelSelect) {
  advancedChannelSelect.addEventListener("change", () => {
    if (snapshotChannelSelect) snapshotChannelSelect.value = advancedChannelSelect.value;
    scheduleSnapshotQuestions({ force: true });
    scheduleDraftSave();
  });
}

if (maxQuestionsInput) {
  maxQuestionsInput.addEventListener("input", () => {
    const value = parseInt(maxQuestionsInput.value, 10);
    if (Number.isNaN(value)) {
      updateAskInfoBudgetStatus(0);
    } else {
      updateAskInfoBudgetStatus(value);
    }
  });
}

if (refreshSnapshotQuestionsBtn) {
  refreshSnapshotQuestionsBtn.addEventListener("click", () => {
    scheduleSnapshotQuestions({ force: true });
  });
}

if (refreshQuestionsBtn) {
  refreshQuestionsBtn.addEventListener("click", () => {
    fetchPendingQuestion();
  });
}

if (submitQuestionAnswer) {
  submitQuestionAnswer.addEventListener("click", async () => {
    if (!state.pendingQuestion || !state.caseId) return;
    const answer = pendingQuestionAnswer?.value?.trim() || "";
    if (!answer) {
      if (pendingQuestionText) pendingQuestionText.textContent = "Please enter an answer.";
      return;
    }
    submitQuestionAnswer.disabled = true;
    try {
      const res = await fetch(`/runs/${state.pendingQuestion.run_id}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_id: state.pendingQuestion.question_id,
          answer,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      await fetchPendingQuestion();
      if (state.caseId) {
        const runsRes = await fetch(`/cases/${state.caseId}/runs`);
        if (runsRes.ok) {
          state.runs = await runsRes.json();
          renderRuns();
        }
      }
    } catch (err) {
      if (pendingQuestionText) pendingQuestionText.textContent = `Error: ${err.message}`;
    } finally {
      submitQuestionAnswer.disabled = false;
    }
  });
}

function updateStatus(message) {
  const el = document.getElementById("caseStatus");
  if (el) el.textContent = message;
  if (snapshotStatus) snapshotStatus.textContent = message;
}

function scheduleDraftSave() {
  if (draftSaveTimer) clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(saveDraftState, 500);
}

function clearDraftState() {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch (err) {
    // ignore
  }
}

function saveDraftState() {
  if (!snapshotTopicInput || !advancedTopicInput) return;
  const draft = {
    updated_at: new Date().toISOString(),
    topic: snapshotTopicInput.value || advancedTopicInput.value || "",
    domain: snapshotDomainSelect?.value || advancedDomainSelect?.value || "GENERAL",
    channel: snapshotChannelSelect?.value || advancedChannelSelect?.value || "UNSPECIFIED",
    snapshot_questions: state.snapshotQuestions || [],
    user_issues: collectUserIssues(),
    counterparty_issues: collectCounterpartyIssues(),
    objectives: collectObjectives(),
    parameters: collectParameters(),
    counterparty_controls: {
      policy_rigidity: document.getElementById("policyRigidity")?.value || "unknown",
      cooperativeness: document.getElementById("cooperativeness")?.value || "unknown",
      time_pressure: document.getElementById("timePressure")?.value || "unknown",
      authority_clarity: document.getElementById("authorityClarity")?.value || "unknown",
    },
  };
  try {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch (err) {
    // ignore storage errors
  }
}

function loadDraftState() {
  let raw = null;
  try {
    raw = localStorage.getItem(DRAFT_STORAGE_KEY);
  } catch (err) {
    raw = null;
  }
  if (!raw) return false;
  try {
    const draft = JSON.parse(raw);
    applyDraftState(draft);
    updateStatus("Draft restored.");
    return true;
  } catch (err) {
    return false;
  }
}

function applyDraftState(draft) {
  if (!draft) return;
  const topic = draft.topic || "";
  const domain = draft.domain || "GENERAL";
  const channel = draft.channel || "UNSPECIFIED";
  setSnapshotBasics(topic, domain, channel, { triggerQuestions: false });
  const draftQuestions = Array.isArray(draft.snapshot_questions) ? draft.snapshot_questions : [];
  state.snapshotQuestions = draftQuestions;
  renderSnapshotQuestions(draftQuestions);
  if (topic) {
    state.snapshotQuestionKey = snapshotKey(topic, domain, channel);
  }
  setUserIssues(draft.user_issues || []);
  setCounterpartyIssues(draft.counterparty_issues || []);
  if (draft.objectives) {
    setObjectives(draft.objectives);
  } else {
    renderObjectiveInputs();
  }
  setParameters(draft.parameters || []);
  const controls = draft.counterparty_controls || {};
  const policyEl = document.getElementById("policyRigidity");
  const coopEl = document.getElementById("cooperativeness");
  const timeEl = document.getElementById("timePressure");
  const authEl = document.getElementById("authorityClarity");
  if (policyEl) policyEl.value = controls.policy_rigidity || "unknown";
  if (coopEl) coopEl.value = controls.cooperativeness || "unknown";
  if (timeEl) timeEl.value = controls.time_pressure || "unknown";
  if (authEl) authEl.value = controls.authority_clarity || "unknown";
}

function renderPendingQuestion(question, queueLength = 0) {
  const previousId = state.pendingQuestion?.question_id || null;
  const isSameQuestion = question && previousId && question.question_id == previousId;
  const preserveAnswer =
    isSameQuestion &&
    pendingQuestionAnswer &&
    document.activeElement === pendingQuestionAnswer &&
    pendingQuestionAnswer.value.trim().length > 0;
  state.pendingQuestion = question;
  if (!pendingQuestionCard) return;
  if (!question) {
    if (pendingQuestionMeta) pendingQuestionMeta.textContent = "";
    if (pendingQuestionText) pendingQuestionText.textContent = "No pending questions.";
    if (pendingQuestionAnswer) pendingQuestionAnswer.value = "";
    if (submitQuestionAnswer) submitQuestionAnswer.disabled = true;
    return;
  }
  if (pendingQuestionMeta) {
    const runId = question.run_id ? question.run_id.slice(0, 8) : "unknown";
    pendingQuestionMeta.textContent = `Run ${runId} A? Queue ${queueLength}`;
  }
  if (pendingQuestionText) pendingQuestionText.textContent = question.question || "";
  if (pendingQuestionAnswer && !preserveAnswer && !isSameQuestion) {
    pendingQuestionAnswer.value = "";
  }
  if (submitQuestionAnswer) submitQuestionAnswer.disabled = false;
}

async function fetchPendingQuestion() {
  if (!state.caseId || !state.sessionId) {
    renderPendingQuestion(null, 0);
    return;
  }
  try {
    const res = await fetch(
      `/cases/${state.caseId}/questions/next?session_id=${encodeURIComponent(state.sessionId)}`
    );
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderPendingQuestion(data.question, data.queue_length || 0);
    if (data.remaining_budget !== undefined && data.remaining_budget !== null) {
      updateAskInfoBudgetStatus(data.remaining_budget);
    }
  } catch (err) {
    if (pendingQuestionText) pendingQuestionText.textContent = `Error: ${err.message}`;
  }
}

function startQuestionPolling() {
  if (questionPollTimer) clearInterval(questionPollTimer);
  questionPollTimer = setInterval(fetchPendingQuestion, 3000);
}

function stopQuestionPolling() {
  if (questionPollTimer) clearInterval(questionPollTimer);
  questionPollTimer = null;
}

function updateAskInfoBudgetStatus(value) {
  if (!askInfoBudgetStatus) return;
  if (value === null || value === undefined || Number.isNaN(value)) {
    askInfoBudgetStatus.textContent = "";
    return;
  }
  askInfoBudgetStatus.textContent = `Ask-info budget: ${value}`;
}

function snapshotKey(topic, domain, channel) {
  return `${topic}||${domain}||${channel}`;
}

function renderSnapshotQuestions(questions = []) {
  if (!snapshotQuestionsEl) return;
  snapshotQuestionsEl.innerHTML = "";
  if (!questions.length) {
    snapshotQuestionsEl.textContent = "No questions yet.";
    return;
  }
  questions.forEach((item, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "snapshot-question";
    const rank = item.rank ?? index + 1;
    wrapper.innerHTML = `
      <div class="snapshot-question-header">
        <span class="snapshot-rank">Q${rank}</span>
        <span>${item.question}</span>
      </div>
      <textarea rows="2" placeholder="Your answer..."></textarea>
    `;
    const input = wrapper.querySelector("textarea");
    input.value = item.answer ?? "";
    input.addEventListener("input", () => {
      item.answer = input.value;
      scheduleDraftSave();
    });
    snapshotQuestionsEl.appendChild(wrapper);
  });
}

function setSnapshotClarifications(clarifications = []) {
  if (!Array.isArray(clarifications) || !clarifications.length) {
    state.snapshotQuestions = [];
    renderSnapshotQuestions([]);
    return;
  }
  state.snapshotQuestions = clarifications.map((item, idx) => ({
    rank: item.rank ?? idx + 1,
    question: item.question || "",
    answer: item.answer ?? "",
  }));
  renderSnapshotQuestions(state.snapshotQuestions);
}

function collectSnapshotClarifications() {
  const clarifications = [];
  (state.snapshotQuestions || []).forEach((item) => {
    const question = String(item.question || "").trim();
    const answer = typeof item.answer === "string" ? item.answer.trim() : item.answer;
    if (!question) return;
    if (answer === undefined || answer === null || answer === "") return;
    clarifications.push({ question, answer });
  });
  return clarifications;
}

function setSnapshotBasics(topic, domain, channel, options = {}) {
  const { triggerQuestions = true } = options;
  if (snapshotTopicInput) snapshotTopicInput.value = topic ?? "";
  if (snapshotDomainSelect) snapshotDomainSelect.value = domain ?? "GENERAL";
  if (snapshotChannelSelect) snapshotChannelSelect.value = channel ?? "UNSPECIFIED";
  if (advancedTopicInput) advancedTopicInput.value = topic ?? "";
  if (advancedDomainSelect) advancedDomainSelect.value = domain ?? "GENERAL";
  if (advancedChannelSelect) advancedChannelSelect.value = channel ?? "UNSPECIFIED";
  if (triggerQuestions && (snapshotTopicInput?.value || "").trim()) {
    scheduleSnapshotQuestions({ force: true });
  }
}

function maybeGenerateSnapshotQuestions() {
  if ((snapshotTopicInput?.value || "").trim() && !state.snapshotQuestions.length) {
    scheduleSnapshotQuestions({ force: true });
  }
}

function scheduleSnapshotQuestions(options = {}) {
  if (snapshotQuestionTimer) clearTimeout(snapshotQuestionTimer);
  snapshotQuestionTimer = setTimeout(() => {
    fetchSnapshotQuestions(options);
  }, 500);
}

async function fetchSnapshotQuestions(options = {}) {
  if (!snapshotTopicInput || !snapshotDomainSelect || !snapshotChannelSelect) return;
  const topic = snapshotTopicInput.value.trim();
  if (!topic) {
    state.snapshotQuestions = [];
    state.snapshotQuestionKey = null;
    renderSnapshotQuestions([]);
    if (snapshotStatus) snapshotStatus.textContent = "Add a topic to generate questions.";
    return;
  }
  const domain = snapshotDomainSelect.value || "GENERAL";
  const channel = snapshotChannelSelect.value || "UNSPECIFIED";
  const key = snapshotKey(topic, domain, channel);
  if (!options.force && state.snapshotQuestionKey === key) return;
  state.snapshotQuestionKey = key;
  if (snapshotStatus) snapshotStatus.textContent = "Generating questions...";
  try {
    const res = await fetch("/cases/snapshot/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, domain, channel }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const previousAnswers = new Map(
      (state.snapshotQuestions || []).map((item) => [String(item.question || "").toLowerCase(), item.answer])
    );
    const questions = (data?.questions || []).map((item, idx) => {
      const questionText = item.question || "";
      const priorAnswer = previousAnswers.get(questionText.toLowerCase());
      return {
        rank: item.rank ?? idx + 1,
        question: questionText,
        answer: priorAnswer ?? "",
      };
    });
    state.snapshotQuestions = questions;
    renderSnapshotQuestions(questions);
    scheduleDraftSave();
    if (snapshotStatus) snapshotStatus.textContent = questions.length
      ? "Questions ready."
      : "No questions returned.";
  } catch (err) {
    if (snapshotStatus) snapshotStatus.textContent = `Error: ${err.message}`;
  }
}

function stopRunPreview() {
  runPreviewState.active = false;
  if (runPreviewState.wordTimer) clearTimeout(runPreviewState.wordTimer);
  if (runPreviewState.swapTimer) clearTimeout(runPreviewState.swapTimer);
  if (runPreviewState.pollTimer) clearInterval(runPreviewState.pollTimer);
  runPreviewState.wordTimer = null;
  runPreviewState.swapTimer = null;
  runPreviewState.pollTimer = null;
  runPreviewState.expectedRuns = null;
  runPreviewState.completedRuns = 0;
  runPreviewState.baseRuns = null;
}

function streamPreviewText(text) {
  const target = document.getElementById("runProgress");
  if (!target) return;
  const words = text.split(/\s+/).filter(Boolean);
  let pos = 0;
  if (runPreviewState.wordTimer) clearTimeout(runPreviewState.wordTimer);
  const tick = () => {
    if (!runPreviewState.active) return;
    const step = Math.max(1, Math.floor(Math.random() * RUN_PREVIEW_WORDS_MAX) + 1);
    const next = words.slice(0, pos + step).join(" ");
    pos += step;
    target.textContent = `Preview: ${next}`;
    if (pos >= words.length) return;
    const delay = Math.max(
      RUN_PREVIEW_DELAY_MIN_MS,
      Math.min(RUN_PREVIEW_DELAY_CAP_MS, Math.round(RUN_PREVIEW_DELAY_CAP_MS / step))
    );
    runPreviewState.wordTimer = setTimeout(tick, delay);
  };
  tick();
}

function showNextPreview() {
  if (!runPreviewState.active || !runPreviewState.summaries.length) return;
  const summary = runPreviewState.summaries[runPreviewState.currentIndex];
  runPreviewState.currentIndex =
    (runPreviewState.currentIndex + 1) % runPreviewState.summaries.length;
  streamPreviewText(summary);
  if (runPreviewState.swapTimer) clearTimeout(runPreviewState.swapTimer);
  runPreviewState.swapTimer = setTimeout(showNextPreview, RUN_PREVIEW_SWAP_MS);
}

async function startRunPreview(caseId, expectedRuns) {
  stopRunPreview();
  runPreviewState.active = true;
  const target = document.getElementById("runProgress");
  const meta = document.getElementById("runProgressMeta");
  if (target) target.textContent = "Preparing previews...";
  if (meta) meta.textContent = "";
  runPreviewState.expectedRuns = expectedRuns || null;
  runPreviewState.completedRuns = 0;
  runPreviewState.baseRuns = null;
  await refreshRunPreviewSummaries(caseId);
  runPreviewState.pollTimer = setInterval(() => {
    refreshRunPreviewSummaries(caseId);
  }, RUN_PREVIEW_POLL_MS);
}

async function refreshRunPreviewSummaries(caseId) {
  const target = document.getElementById("runProgress");
  const meta = document.getElementById("runProgressMeta");
  try {
    const res = await fetch(`/cases/${caseId}/runs`);
    if (!res.ok) throw new Error(await res.text());
    const runs = await res.json();
    const summaries = (runs || [])
      .map((run) => {
        if (typeof run.summary === "string") return run.summary;
        return run.summary?.summary || run.summary?.summary_text;
      })
      .filter(Boolean);
    if (runPreviewState.baseRuns === null) {
      runPreviewState.baseRuns = runs.length;
    }
    runPreviewState.completedRuns = Math.max(0, runs.length - runPreviewState.baseRuns);
    if (meta && runPreviewState.expectedRuns) {
      const completed = Math.min(runPreviewState.completedRuns, runPreviewState.expectedRuns);
      meta.textContent = `Running… ${completed}/${runPreviewState.expectedRuns} complete`;
    }
    if (!summaries.length) {
      if (target && !runPreviewState.expectedRuns) target.textContent = "Running simulations...";
      return;
    }
    const hadSummaries = runPreviewState.summaries.length > 0;
    runPreviewState.summaries = summaries;
    if (runPreviewState.currentIndex >= summaries.length) {
      runPreviewState.currentIndex = 0;
    }
    if (!hadSummaries) {
      showNextPreview();
    }
  } catch (err) {
    if (target && !runPreviewState.summaries.length) {
      target.textContent = "Running simulations...";
    }
  }
}

function formatJson(obj) {
  return JSON.stringify(obj, null, 2);
}

function generateCaseId() {
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return "case-" + Math.random().toString(16).slice(2);
}

function generateSessionId() {
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return "session-" + Math.random().toString(16).slice(2);
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

const COUNTERPARTY_HINT_DEFS = {
  policy_rigidity: {
    label: "Policy Rigidity",
    definition: "How strictly the counterparty sticks to internal rules, bands, or approvals.",
    seedExample: "Policy caps base salary at $130k, so we can adjust bonus but not base.",
  },
  cooperativeness: {
    label: "Cooperativeness",
    definition: "How collaborative vs guarded the counterparty's tone and posture are.",
    seedExample: "We want a package that works for both sides and can trade across components.",
  },
  time_pressure: {
    label: "Time Pressure",
    definition: "How urgent the counterparty is to reach a decision and close.",
    seedExample: "We need to finalize by Friday to stay on the hiring timeline.",
  },
  authority_clarity: {
    label: "Authority Clarity",
    definition: "How clear the approval path is and whether the counterparty can commit.",
    seedExample: "I can approve base, but equity needs CFO sign-off.",
  },
};

function renderCounterpartyHints(examples = {}) {
  document.querySelectorAll(".hint[data-control-id]").forEach((el) => {
    const controlId = el.dataset.controlId;
    const def = COUNTERPARTY_HINT_DEFS[controlId];
    if (!def) return;
    const definitionEl = el.querySelector(".hint-definition");
    const exampleEl = el.querySelector(".hint-example");
    if (definitionEl) definitionEl.textContent = def.definition;
    const example = examples[controlId] || def.seedExample;
    if (exampleEl) exampleEl.textContent = `Example: ${example}`;
  });
}

async function loadCounterpartyHints() {
  renderCounterpartyHints();
  if (!state.caseId) return;
  const status = document.getElementById("counterpartyHintStatus");
  if (status) status.textContent = "Generating examples...";
  try {
    const res = await fetch(`/cases/${state.caseId}/counterparty/hints`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const examples = {};
    (data?.hints || []).forEach((hint) => {
      if (hint?.control_id && hint?.example) {
        examples[hint.control_id] = hint.example;
      }
    });
    renderCounterpartyHints(examples);
    if (status) status.textContent = "Examples updated.";
  } catch (err) {
    if (status) status.textContent = `Examples unavailable: ${err.message}`;
  }
}

const DEFAULT_CONTROLS = {
  outcome_vs_agreement: 0.5,
  speed_vs_thoroughness: 0.5,
  risk_tolerance: 0.5,
  relationship_sensitivity: 0.5,
  info_sharing: 0.5,
  creativity_vs_discipline: 0.5,
  constraint_confidence: 0.5,
};

function getControlsFromInputs() {
  return { ...DEFAULT_CONTROLS };
}

const userIssuesEditor = document.getElementById("userIssuesEditor");
const counterpartyIssuesEditor = document.getElementById("counterpartyIssuesEditor");
const parametersEditor = document.getElementById("parametersEditor");
const objectiveVectorSection = document.getElementById("objectiveVectorSection");
const objectiveSingleSection = document.getElementById("objectiveSingleSection");
const objectiveType = document.getElementById("objectiveType");
const sampleCaseSelect = document.getElementById("sampleCaseSelect");
const savedCaseSelect = document.getElementById("savedCaseSelect");

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
    scheduleDraftSave();
  });
  row.querySelectorAll("input, select").forEach((el) => {
    if (onChange) {
      el.addEventListener("change", onChange);
    }
    el.addEventListener("change", scheduleDraftSave);
    el.addEventListener("input", scheduleDraftSave);
  });
  const nameInput = row.querySelector("[data-field='name']");
  const idInput = row.querySelector("[data-field='issue_id']");
  nameInput.addEventListener("blur", () => {
    if (!idInput.value.trim() && nameInput.value.trim()) {
      idInput.value = slugify(nameInput.value.trim());
      if (onChange) onChange();
      scheduleDraftSave();
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
    scheduleDraftSave();
  });
  row.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("change", scheduleDraftSave);
    el.addEventListener("input", scheduleDraftSave);
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
  const issues = collectUserIssues();
  const issueWeights = {};

  if (type === "SINGLE_VALUE") {
    const targetRaw = document.getElementById("objectiveTargetSingle").value;
    const reservationRaw = document.getElementById("objectiveReservationSingle").value;
    issues.forEach((issue) => (issueWeights[issue.issue_id] = 1.0));
    return {
      target: { type, value: parseValue(targetRaw) },
      reservation: { type, value: parseValue(reservationRaw) },
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

function collectCalibrationAnswers() {
  const fields = {
    policy_rigidity: document.getElementById("policyRigidity").value,
    cooperativeness: document.getElementById("cooperativeness").value,
    time_pressure: document.getElementById("timePressure").value,
    authority_clarity: document.getElementById("authorityClarity").value,
  };
  const answers = {};
  Object.entries(fields).forEach(([key, value]) => {
    if (value && value !== "unknown") {
      answers[key] = value;
    }
  });
  return answers;
}

function setObjectives(objectives) {
  objectiveType.value = objectives.target?.type || "OFFER_VECTOR";

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

const SAMPLE_CASES = [
  {
    id: "job_offer",
    label: "Job Offer: Base Salary Negotiation",
    topic:
      "I am negotiating a job offer by email. I have market research and a clear minimum base salary, but I do not know the employer's exact budget.",
    domain: "JOB_OFFER_COMP",
    channel: "EMAIL",
    user_issues: [
      {
        issue_id: "salary",
        name: "Base Salary",
        type: "SALARY",
        direction: "MAXIMIZE",
        unit: "USD",
        bounds: { min: 140000, max: 160000 },
      },
    ],
    counterparty_issues: [
      {
        issue_id: "salary",
        name: "Base Salary",
        type: "SALARY",
        direction: "MINIMIZE",
        unit: "USD",
        bounds: { min: 110000, max: 130000 },
      },
    ],
    objectives: {
      target: { type: "OFFER_VECTOR", value: { salary: 140000 } },
      reservation: { type: "OFFER_VECTOR", value: { salary: 120000 } },
      issue_weights: { salary: 1.0 },
    },
    parameters: [
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
    ],
  },
  {
    id: "roommates",
    label: "Roommates: Boyfriend Visits + Cleaning",
    topic:
      "I am burdened by my roommate Ava's boyfriend, Mike, frequently staying over and leaving shared areas messy.",
    domain: "GENERAL",
    channel: "IN_PERSON",
    user_issues: [
      {
        issue_id: "cleaning",
        name: "Cleaning Standards",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
        bounds: { min: "clean after", max: "clean the whole place" },
      },
    ],
    counterparty_issues: [
      {
        issue_id: "bf_stayover",
        name: "Boyfriend Stay-Overs",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
        bounds: { min: "stay over", max: "stay over more often" },
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "No boyfriend stays over; if he visits, he cleans immediately and leaves no mess.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Visits are limited and he cleans shared areas after each visit.",
      },
      issue_weights: { cleaning: 1.0 },
    },
    parameters: [],
  },
  {
    id: "ai_regulation",
    label: "Tech: Global AI Regulation",
    topic:
      "I want to debate whether there should be global regulations for AI development. I'm a master's student with academic readings but limited industry data.",
    domain: "GENERAL",
    channel: "IN_PERSON",
    user_issues: [
      {
        issue_id: "ai_regulation",
        name: "Global AI Regulation Stance",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
      },
    ],
    counterparty_issues: [
      {
        issue_id: "ai_regulation",
        name: "Global AI Regulation Stance",
        type: "OTHER",
        direction: "MINIMIZE",
        unit: "text",
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "Support global safety regulations with independent audits.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Support voluntary guidelines and transparency reports.",
      },
      issue_weights: { ai_regulation: 1.0 },
    },
    parameters: [],
  },
  {
    id: "pineapple_pizza",
    label: "Food: Pineapple on Pizza",
    topic:
      "I want to debate whether pineapple belongs on pizza. I'm a TikToker who reviews food trends and cares about taste reactions.",
    domain: "GENERAL",
    channel: "DM",
    user_issues: [
      {
        issue_id: "pineapple_pizza",
        name: "Pizza Topping Stance",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
      },
    ],
    counterparty_issues: [
      {
        issue_id: "pineapple_pizza",
        name: "Pizza Topping Stance",
        type: "OTHER",
        direction: "MINIMIZE",
        unit: "text",
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "Pineapple belongs for sweet-salty contrast.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Pineapple is fine as an optional topping.",
      },
      issue_weights: { pineapple_pizza: 1.0 },
    },
    parameters: [],
  },
  {
    id: "kids_social_media",
    label: "Social Media: Under 13 Ban",
    topic:
      "I want to debate whether children under 13 should be banned from social media. I'm a concerned parent with personal experience but limited policy knowledge.",
    domain: "GENERAL",
    channel: "IN_PERSON",
    user_issues: [
      {
        issue_id: "under13_social",
        name: "Under-13 Social Media Policy",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
      },
    ],
    counterparty_issues: [
      {
        issue_id: "under13_social",
        name: "Under-13 Social Media Policy",
        type: "OTHER",
        direction: "MINIMIZE",
        unit: "text",
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "Support a ban for under-13s with strict enforcement.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Require verified parental consent and time limits.",
      },
      issue_weights: { under13_social: 1.0 },
    },
    parameters: [],
  },
  {
    id: "tipping_culture",
    label: "Tipping Culture: Replace with Wages",
    topic:
      "I want to debate whether tipping should be abolished in favor of higher base wages. I'm from the UK and find US tipping norms confusing.",
    domain: "GENERAL",
    channel: "IN_PERSON",
    user_issues: [
      {
        issue_id: "tipping_policy",
        name: "Tipping Policy",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
      },
    ],
    counterparty_issues: [
      {
        issue_id: "tipping_policy",
        name: "Tipping Policy",
        type: "OTHER",
        direction: "MINIMIZE",
        unit: "text",
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "Abolish tipping and pay living wages.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Include a service charge by default.",
      },
      issue_weights: { tipping_policy: 1.0 },
    },
    parameters: [],
  },
  {
    id: "dating_apps",
    label: "Dating Apps vs Traditional Courtship",
    topic:
      "I want to debate whether dating apps have broken modern romance. I'm a frustrated dater with app burnout and want healthier alternatives.",
    domain: "GENERAL",
    channel: "DM",
    user_issues: [
      {
        issue_id: "dating_apps",
        name: "Dating Approach",
        type: "OTHER",
        direction: "MAXIMIZE",
        unit: "text",
      },
    ],
    counterparty_issues: [
      {
        issue_id: "dating_apps",
        name: "Dating Approach",
        type: "OTHER",
        direction: "MINIMIZE",
        unit: "text",
      },
    ],
    objectives: {
      target: {
        type: "SINGLE_VALUE",
        value: "Apps harm romance; return to traditional courtship.",
      },
      reservation: {
        type: "SINGLE_VALUE",
        value: "Limit apps and prioritize in-person connections.",
      },
      issue_weights: { dating_apps: 1.0 },
    },
    parameters: [],
  },
  {
    id: "freelance_contract",
    label: "Freelance Contract: Fee + Timeline",
    topic:
      "I'm a freelance designer negotiating a project fee and delivery timeline by email. I know my minimum fee but not the client's budget.",
    domain: "SERVICES_CONTRACTOR",
    channel: "EMAIL",
    user_issues: [
      {
        issue_id: "fee",
        name: "Project Fee",
        type: "PRICE",
        direction: "MAXIMIZE",
        unit: "USD",
        bounds: { min: 4500, max: 7000 },
      },
      {
        issue_id: "timeline",
        name: "Delivery Timeline",
        type: "DATE",
        direction: "MINIMIZE",
        unit: "days",
        bounds: { min: 14, max: 30 },
      },
    ],
    counterparty_issues: [
      {
        issue_id: "fee",
        name: "Project Fee",
        type: "PRICE",
        direction: "MINIMIZE",
        unit: "USD",
        bounds: { min: 3000, max: 5500 },
      },
      {
        issue_id: "timeline",
        name: "Delivery Timeline",
        type: "DATE",
        direction: "MAXIMIZE",
        unit: "days",
        bounds: { min: 21, max: 45 },
      },
    ],
    objectives: {
      target: { type: "OFFER_VECTOR", value: { fee: 6000, timeline: 21 } },
      reservation: { type: "OFFER_VECTOR", value: { fee: 4500, timeline: 30 } },
      issue_weights: { fee: 0.7, timeline: 0.3 },
    },
    parameters: [
      {
        param_id: "P_MIN_FEE",
        label: "Minimum project fee",
        value_type: "MONEY",
        value: 4500,
        class: "NON_NEGOTIABLE",
        disclosure: "PRIVATE",
        allow_rethink_suggestions: false,
        applies_to: { scope: "OFFER", issue_id: "fee" },
      },
    ],
  },
];

function populateSampleCaseSelect() {
  const selects = [sampleCaseSelect, snapshotSampleCaseSelect].filter(Boolean);
  selects.forEach((select) => {
    select.innerHTML = "";
    SAMPLE_CASES.forEach((sample) => {
      const option = document.createElement("option");
      option.value = sample.id;
      option.textContent = sample.label;
      select.appendChild(option);
    });
  });
}

function setSampleSelection(sampleId) {
  if (sampleCaseSelect) sampleCaseSelect.value = sampleId;
  if (snapshotSampleCaseSelect) snapshotSampleCaseSelect.value = sampleId;
}

function applySampleCase(sample) {
  if (!sample) return;
  setSampleSelection(sample.id);
  document.getElementById("topic").value = sample.topic;
  document.getElementById("domain").value = sample.domain;
  document.getElementById("channel").value = sample.channel;
  setSnapshotBasics(sample.topic, sample.domain, sample.channel, { triggerQuestions: true });
  setSnapshotClarifications([]);
  state.sessionId = null;
  stopQuestionPolling();
  renderPendingQuestion(null, 0);
  setUserIssues(sample.user_issues);
  setCounterpartyIssues(sample.counterparty_issues);
  setObjectives(sample.objectives);
  setParameters(sample.parameters);
  scheduleDraftSave();
}

function loadSampleCase() {
  const selectedId =
    snapshotSampleCaseSelect?.value ||
    sampleCaseSelect?.value ||
    SAMPLE_CASES[0]?.id;
  const sample = SAMPLE_CASES.find((item) => item.id === selectedId) || SAMPLE_CASES[0];
  applySampleCase(sample);
}

document.getElementById("loadSample").addEventListener("click", loadSampleCase);
if (snapshotLoadSampleBtn) {
  snapshotLoadSampleBtn.addEventListener("click", loadSampleCase);
}

function resetCaseForm() {
  document.getElementById("topic").value = "";
  document.getElementById("domain").value = "GENERAL";
  document.getElementById("channel").value = "UNSPECIFIED";
  setSnapshotBasics("", "GENERAL", "UNSPECIFIED", { triggerQuestions: false });
  setSnapshotClarifications([]);
  state.snapshotQuestionKey = null;
  state.sessionId = null;
  stopQuestionPolling();
  renderPendingQuestion(null, 0);
  if (sampleCaseSelect) sampleCaseSelect.selectedIndex = 0;
  if (snapshotSampleCaseSelect) snapshotSampleCaseSelect.selectedIndex = 0;
  if (savedCaseSelect) savedCaseSelect.selectedIndex = -1;
  if (snapshotSavedCaseSelect) snapshotSavedCaseSelect.selectedIndex = 0;
  setUserIssues([]);
  setCounterpartyIssues([]);
  setParameters([]);
  objectiveType.value = "OFFER_VECTOR";
  document.getElementById("objectiveTargetSingle").value = "";
  document.getElementById("objectiveReservationSingle").value = "";
  renderObjectiveInputs();
  state.caseId = null;
  state.caseData = null;
  updateStatus("Case reset.");
  clearDraftState();
  updateAskInfoBudgetStatus(parseInt(maxQuestionsInput?.value, 10) || 0);
}

function resetCounterpartyControls() {
  document.getElementById("policyRigidity").value = "unknown";
  document.getElementById("cooperativeness").value = "unknown";
  document.getElementById("timePressure").value = "unknown";
  document.getElementById("authorityClarity").value = "unknown";
  document.getElementById("personaDistribution").textContent = "";
  const hintStatus = document.getElementById("counterpartyHintStatus");
  if (hintStatus) hintStatus.textContent = "";
  renderCounterpartyHints();
}

function setCounterpartyControlsFromCase(caseData) {
  const answers = caseData?.counterparty_assumptions?.calibration?.answers || {};
  const defaults = {
    policy_rigidity: "unknown",
    cooperativeness: "unknown",
    time_pressure: "unknown",
    authority_clarity: "unknown",
  };
  const values = { ...defaults, ...answers };
  const policyEl = document.getElementById("policyRigidity");
  const coopEl = document.getElementById("cooperativeness");
  const timeEl = document.getElementById("timePressure");
  const authEl = document.getElementById("authorityClarity");
  if (policyEl) policyEl.value = values.policy_rigidity || "unknown";
  if (coopEl) coopEl.value = values.cooperativeness || "unknown";
  if (timeEl) timeEl.value = values.time_pressure || "unknown";
  if (authEl) authEl.value = values.authority_clarity || "unknown";
}

async function applySavedCase(caseData) {
  if (!caseData) return;
  if (snapshotSavedCaseSelect && caseData.case_id) {
    snapshotSavedCaseSelect.value = caseData.case_id;
  }
  document.getElementById("topic").value = caseData.topic || "";
  document.getElementById("domain").value = caseData.domain || "GENERAL";
  document.getElementById("channel").value = caseData.channel || "UNSPECIFIED";
  const clarifications = caseData.clarifications || [];
  setSnapshotBasics(
    caseData.topic || "",
    caseData.domain || "GENERAL",
    caseData.channel || "UNSPECIFIED",
    { triggerQuestions: !clarifications.length }
  );
  setSnapshotClarifications(clarifications);
  state.sessionId = null;
  stopQuestionPolling();
  renderPendingQuestion(null, 0);
  setUserIssues(caseData.user_issues || caseData.issues || []);
  setCounterpartyIssues(caseData.counterparty_issues || caseData.issues || []);
  if (caseData.objectives) {
    setObjectives(caseData.objectives);
  } else {
    renderObjectiveInputs();
  }
  setParameters(caseData.parameters || []);
  setCounterpartyControlsFromCase(caseData);
  state.caseId = caseData.case_id || null;
  state.caseData = caseData;
  updateStatus(state.caseId ? `Loaded case: ${state.caseId}` : "Loaded case.");
  const budgetValue = parseInt(maxQuestionsInput?.value, 10);
  updateAskInfoBudgetStatus(Number.isNaN(budgetValue) ? 0 : budgetValue);
  scheduleDraftSave();
  await autoloadCaseData(state.caseId);
}

function populateSavedCaseSelect(cases = []) {
  const selects = [savedCaseSelect, snapshotSavedCaseSelect].filter(Boolean);
  selects.forEach((select) => {
    select.innerHTML = "";
    if (!cases.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No saved cases";
      select.appendChild(option);
      return;
    }
    cases.forEach((caseItem) => {
      const option = document.createElement("option");
      option.value = caseItem.case_id;
      const title = caseItem.topic || "Untitled case";
      const status = caseItem.status || "DRAFT";
      const domain = caseItem.domain || "GENERAL";
      const shortId = caseItem.case_id ? caseItem.case_id.slice(0, 8) : "unknown";
      option.textContent = `${title} · ${domain} · ${status} · ${shortId}`;
      select.appendChild(option);
    });
  });
}

async function refreshSavedCases() {
  if (!savedCaseSelect) return;
  try {
    const res = await fetch("/cases");
    if (!res.ok) throw new Error(await res.text());
    const cases = await res.json();
    populateSavedCaseSelect(cases || []);
  } catch (err) {
    populateSavedCaseSelect([]);
  }
}

document.getElementById("loadSavedCase").addEventListener("click", async () => {
  if (!savedCaseSelect) return;
  const selected = Array.from(savedCaseSelect.selectedOptions)
    .map((option) => option.value)
    .filter(Boolean);
  if (!selected.length) {
    updateStatus("No saved case selected.");
    return;
  }
  if (selected.length > 1) {
    updateStatus("Select a single saved case to load.");
    return;
  }
  const caseId = selected[0];
  try {
    const res = await fetch(`/cases/${caseId}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    await applySavedCase(data);
  } catch (err) {
    updateStatus(`Error: ${err.message}`);
  }
});

if (snapshotLoadSavedCaseBtn) {
  snapshotLoadSavedCaseBtn.addEventListener("click", async () => {
    if (!snapshotSavedCaseSelect) return;
    const selected = Array.from(snapshotSavedCaseSelect.selectedOptions)
      .map((option) => option.value)
      .filter(Boolean);
    if (!selected.length) {
      updateStatus("No saved case selected.");
      return;
    }
    if (selected.length > 1) {
      updateStatus("Select a single saved case to load.");
      return;
    }
    const caseId = selected[0];
    try {
      const res = await fetch(`/cases/${caseId}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      await applySavedCase(data);
    } catch (err) {
      updateStatus(`Error: ${err.message}`);
    }
  });
}

if (snapshotDeleteSavedCasesBtn) {
  snapshotDeleteSavedCasesBtn.addEventListener("click", async () => {
    if (!snapshotSavedCaseSelect) return;
    const selected = Array.from(snapshotSavedCaseSelect.selectedOptions)
      .map((option) => option.value)
      .filter(Boolean);
    if (!selected.length) {
      updateStatus("Select one or more cases to delete.");
      return;
    }
    const confirmed = window.confirm(`Delete ${selected.length} case(s)? This cannot be undone.`);
    if (!confirmed) return;
    try {
      const res = await fetch("/cases/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_ids: selected }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (selected.includes(state.caseId)) {
        state.caseId = null;
        state.caseData = null;
      }
      updateStatus(
        `Deleted ${data.deleted_cases || 0} case(s), ${data.deleted_runs || 0} run(s), ${data.deleted_traces || 0} trace(s).`
      );
      refreshSavedCases();
    } catch (err) {
      updateStatus(`Error: ${err.message}`);
    }
  });
}

if (snapshotClearDraftBtn) {
  snapshotClearDraftBtn.addEventListener("click", () => {
    clearDraftState();
    updateStatus("Draft cleared.");
  });
}

document.getElementById("deleteSavedCases").addEventListener("click", async () => {
  if (!savedCaseSelect) return;
  const selected = Array.from(savedCaseSelect.selectedOptions)
    .map((option) => option.value)
    .filter(Boolean);
  if (!selected.length) {
    updateStatus("Select one or more cases to delete.");
    return;
  }
  const confirmed = window.confirm(`Delete ${selected.length} case(s)? This cannot be undone.`);
  if (!confirmed) return;
  try {
    const res = await fetch("/cases/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_ids: selected }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    if (selected.includes(state.caseId)) {
      state.caseId = null;
      state.caseData = null;
    }
    updateStatus(
      `Deleted ${data.deleted_cases || 0} case(s), ${data.deleted_runs || 0} run(s), ${data.deleted_traces || 0} trace(s).`
    );
    refreshSavedCases();
  } catch (err) {
    updateStatus(`Error: ${err.message}`);
  }
});

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
objectiveType.addEventListener("change", scheduleDraftSave);

objectiveVectorSection.addEventListener("input", scheduleDraftSave);
objectiveVectorSection.addEventListener("change", scheduleDraftSave);
objectiveSingleSection.addEventListener("input", scheduleDraftSave);
objectiveSingleSection.addEventListener("change", scheduleDraftSave);

userIssuesEditor.addEventListener("input", scheduleDraftSave);
userIssuesEditor.addEventListener("change", scheduleDraftSave);
counterpartyIssuesEditor.addEventListener("input", scheduleDraftSave);
counterpartyIssuesEditor.addEventListener("change", scheduleDraftSave);
parametersEditor.addEventListener("input", scheduleDraftSave);
parametersEditor.addEventListener("change", scheduleDraftSave);

const policyRigidityEl = document.getElementById("policyRigidity");
const cooperativenessEl = document.getElementById("cooperativeness");
const timePressureEl = document.getElementById("timePressure");
const authorityClarityEl = document.getElementById("authorityClarity");
if (policyRigidityEl) policyRigidityEl.addEventListener("change", scheduleDraftSave);
if (cooperativenessEl) cooperativenessEl.addEventListener("change", scheduleDraftSave);
if (timePressureEl) timePressureEl.addEventListener("change", scheduleDraftSave);
if (authorityClarityEl) authorityClarityEl.addEventListener("change", scheduleDraftSave);

const createCaseBtn = document.getElementById("createCase");
async function handleCreateCase() {
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
    const clarifications = collectSnapshotClarifications();
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
      clarifications: clarifications,
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
    state.sessionId = null;
    renderPendingQuestion(null, 0);
    updateStatus(`Case created: ${state.caseId}`);
    refreshSavedCases();
  } catch (err) {
    updateStatus(`Error: ${err.message}`);
  }
}

if (createCaseBtn) {
  createCaseBtn.addEventListener("click", handleCreateCase);
}
if (snapshotCreateCaseBtn) {
  snapshotCreateCaseBtn.addEventListener("click", handleCreateCase);
}

document.getElementById("validateCase").addEventListener("click", () => {
  const missing = validateCaseInputs();
  updateStatus(missing.length ? `Missing: ${missing.join(", ")}` : "Ready to save.");
});

document.getElementById("calibratePersona").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const answers = collectCalibrationAnswers();
  const res = await fetch(`/cases/${state.caseId}/persona/calibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ calibration: { answers } }),
  });
  const data = await res.json();
  if (data.persona_distribution) {
    state.personaDistribution = data.persona_distribution;
  }
  const summary = data.counterparty_controls_summary;
  document.getElementById("personaDistribution").textContent = summary || formatJson(data);
});

document.getElementById("runSim").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const runs = parseInt(document.getElementById("runs").value, 10) || 1;
  const maxTurns = parseInt(document.getElementById("max_turns").value, 10);
  let maxQuestions = parseInt(maxQuestionsInput?.value, 10);
  if (Number.isNaN(maxQuestions)) maxQuestions = 0;
  updateAskInfoBudgetStatus(maxQuestions);
  state.sessionId = generateSessionId();
  const mode = "FAST";
  await startRunPreview(state.caseId, runs);
  startQuestionPolling();
  fetchPendingQuestion();
  try {
    const res = await fetch(`/cases/${state.caseId}/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        runs,
        max_turns: maxTurns,
        mode,
        max_questions: maxQuestions,
        session_id: state.sessionId,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.runs = data;
    state.sessionId = state.sessionId || data?.[0]?.session_id || null;
    renderRuns();
    stopRunPreview();
    await fetchPendingQuestion();
    const pausedCount = data.filter((run) => run.status === "PAUSED").length;
    const runStatusText = pausedCount
      ? `Finished ${data.length} runs (${pausedCount} paused for questions).`
      : `Completed ${data.length} runs.`;
    document.getElementById("runProgress").textContent = runStatusText;
    const meta = document.getElementById("runProgressMeta");
    if (meta) meta.textContent = "";
  } catch (err) {
    stopRunPreview();
    stopQuestionPolling();
    document.getElementById("runProgress").textContent = `Error: ${err.message}`;
    const meta = document.getElementById("runProgressMeta");
    if (meta) meta.textContent = "";
  }
});

function renderRuns() {
  const table = document.getElementById("runsTable");
  table.innerHTML = "";
  state.runs.forEach((run) => {
    const wrapper = document.createElement("div");
    wrapper.className = "run-row";

    const row = document.createElement("div");
    row.className = "row";
    const errorCount = run.error_count || 0;
    const errorBadge = errorCount
      ? `<span class="run-error-badge">⚠ ${errorCount} error${errorCount === 1 ? "" : "s"}</span>`
      : "";
    const statusText = run.status && run.status !== "COMPLETED" ? ` | status: ${run.status}` : "";
    row.innerHTML = `<strong>${run.outcome}</strong>${statusText} | persona: ${run.persona_id} | utility: ${run.user_utility.toFixed(2)} | turns: ${run.turns.length} ${errorBadge}`;

    if (errorCount) {
      const errorButton = document.createElement("button");
      errorButton.className = "run-error-btn";
      errorButton.type = "button";
      errorButton.textContent = "View errors";
      row.appendChild(errorButton);

      const errorPanel = document.createElement("div");
      errorPanel.className = "run-errors";
      errorPanel.hidden = true;

      errorButton.addEventListener("click", async () => {
        errorPanel.hidden = !errorPanel.hidden;
        if (!errorPanel.hidden && !errorPanel.dataset.loaded) {
          errorPanel.textContent = "Loading errors...";
          try {
            const res = await fetch(`/runs/${run.run_id}/trace`);
            if (!res.ok) throw new Error(await res.text());
            const trace = await res.json();
            const failures = (trace?.agent_call_traces || []).filter(
              (call) => (call.validation_result || {}).status === "FAIL"
            );
            if (!failures.length) {
              errorPanel.textContent = "No errors found in trace.";
            } else {
              const lines = failures.map((call) => {
                const agent = call.agent_name || "Agent";
                const reason = (call.validation_result || {}).reason || "Unknown error";
                const raw = call.raw_output || "";
                return `${agent}: ${reason}\n${raw}`.trim();
              });
              errorPanel.textContent = lines.join("\n\n---\n\n");
            }
            errorPanel.dataset.loaded = "true";
          } catch (err) {
            errorPanel.textContent = `Error loading trace: ${err.message}`;
          }
        }
      });

      wrapper.appendChild(row);
      wrapper.appendChild(errorPanel);
    } else {
      wrapper.appendChild(row);
    }

    table.appendChild(wrapper);
  });
  populateDebugRuns(state.runs);
}

document.getElementById("loadInsights").addEventListener("click", async () => {
  if (!state.caseId) {
    updateStatus("Create a case first.");
    return;
  }
  const status = document.getElementById("insightsStatus");
  const button = document.getElementById("loadInsights");
  if (status) status.textContent = "Loading insights...";
  if (button) button.disabled = true;
  try {
    const res = await fetch(`/cases/${state.caseId}/insights`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    document.getElementById("insightsOutput").textContent = formatJson(data);
    renderInsights(data);
    if (status) status.textContent = `Loaded ${data?.turns_to_termination?.length || 0} runs.`;
  } catch (err) {
    if (status) status.textContent = `Error: ${err.message}`;
  } finally {
    if (button) button.disabled = false;
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
  if (!state.caseId) {
    updateStatus("Run a simulation first.");
    return;
  }
  const selectedId = debugRunSelect?.value;
  const fallbackId = state.runs.length ? state.runs[state.runs.length - 1].run_id : null;
  const runId = selectedId || fallbackId;
  if (!runId) {
    updateStatus("Run a simulation first.");
    return;
  }
  const res = await fetch(`/runs/${runId}/trace`);
  const data = await res.json();
  document.getElementById("traceOutput").textContent = formatJson(data);
  renderTraceFlow(data);
});

const closeInsightButton = document.getElementById("closeInsightDetail");
if (closeInsightButton) {
  closeInsightButton.addEventListener("click", closeInsightDetail);
}

if (debugSearchButton) {
  debugSearchButton.addEventListener("click", () => {
    searchDebugTraces();
  });
}

if (debugSearchClear) {
  debugSearchClear.addEventListener("click", () => {
    if (debugSearchInput) debugSearchInput.value = "";
    populateDebugRuns(state.debugRunsAll || state.runs);
    if (debugStatus) debugStatus.textContent = "Search cleared.";
  });
}

if (debugFilterFallbacks) {
  debugFilterFallbacks.addEventListener("click", () => {
    filterRunsByFallback(true);
  });
}

if (debugFilterNonFallbacks) {
  debugFilterNonFallbacks.addEventListener("click", () => {
    filterRunsByFallback(false);
  });
}

if (resetCaseButton) {
  resetCaseButton.addEventListener("click", () => {
    resetCaseForm();
  });
}

if (resetCounterpartyButton) {
  resetCounterpartyButton.addEventListener("click", () => {
    resetCounterpartyControls();
  });
}

populateSampleCaseSelect();
const restoredDraft = loadDraftState();
if (!restoredDraft) {
  loadSampleCase();
}
renderCounterpartyHints();
refreshSavedCases();
refreshDebugRuns();

function renderInsights(data) {
  closeInsightDetail();
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
  renderBucketList(passEl, buckets.PASS, "No PASS insights yet.", "PASS");
  renderBucketList(neutralEl, buckets.NEUTRAL, "No NEUTRAL insights yet.", "NEUTRAL");
  renderBucketList(failEl, buckets.FAIL, "No FAIL insights yet.", "FAIL");
}

function renderBucketList(container, bucketData, emptyText, bucketLabel) {
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
    row.addEventListener("click", () => openInsightDetail(bucketLabel, item));
    container.appendChild(row);
  });
}

function openInsightDetail(bucketLabel, item) {
  const wrapper = document.getElementById("insightsBuckets");
  const detail = document.getElementById("insightDetail");
  const titleEl = document.getElementById("insightDetailTitle");
  const metaEl = document.getElementById("insightDetailMeta");
  const snippetsEl = document.getElementById("insightDetailSnippets");
  const runSelect = document.getElementById("insightRunSelect");
  if (!wrapper || !detail || !runSelect) return;
  wrapper.classList.add("active");
  wrapper.dataset.activeBucket = bucketLabel;
  detail.hidden = false;
  if (titleEl) titleEl.textContent = item.claim || "";
  if (metaEl) metaEl.textContent = `${bucketLabel} • Support ${item.support_count || 0}`;
  if (snippetsEl) {
    snippetsEl.innerHTML = "";
    const snippets = Array.isArray(item.example_snippets) ? item.example_snippets : [];
    if (!snippets.length) {
      snippetsEl.textContent = "No example snippets available.";
    } else {
      snippets.forEach((snippet) => {
        const line = document.createElement("div");
        line.textContent = snippet;
        snippetsEl.appendChild(line);
      });
    }
  }

  const runIds = Array.isArray(item.example_run_ids) ? item.example_run_ids : [];
  runSelect.innerHTML = "";
  if (!runIds.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No example runs";
    runSelect.appendChild(option);
    runSelect.disabled = true;
    renderInsightConversation([]);
    return;
  }
  runSelect.disabled = false;
  runIds.forEach((runId, idx) => {
    const option = document.createElement("option");
    option.value = runId;
    option.textContent = `Run ${idx + 1} · ${runId.slice(0, 8)}`;
    runSelect.appendChild(option);
  });
  runSelect.onchange = () => {
    if (runSelect.value) {
      loadInsightConversation(runSelect.value);
    }
  };
  loadInsightConversation(runIds[0]);
}

function closeInsightDetail() {
  const wrapper = document.getElementById("insightsBuckets");
  const detail = document.getElementById("insightDetail");
  const runSelect = document.getElementById("insightRunSelect");
  if (wrapper) {
    wrapper.classList.remove("active");
    delete wrapper.dataset.activeBucket;
  }
  if (detail) detail.hidden = true;
  if (runSelect) runSelect.onchange = null;
  renderInsightConversation([]);
}

async function loadInsightConversation(runId) {
  const container = document.getElementById("insightConversation");
  if (!container) return;
  container.textContent = "Loading conversation...";
  try {
    const res = await fetch(`/runs/${runId}/trace`);
    if (!res.ok) throw new Error(await res.text());
    const trace = await res.json();
    const turns = trace?.turn_traces || [];
    renderInsightConversation(turns);
  } catch (err) {
    try {
      const runRes = await fetch(`/runs/${runId}`);
      if (!runRes.ok) throw new Error(await runRes.text());
      const runData = await runRes.json();
      const turns = runData?.run?.turns || [];
      if (turns.length) {
        renderInsightConversation(turns);
        return;
      }
    } catch (runErr) {
      // fall through to error message below
    }
    container.textContent = `Unable to load conversation: ${err.message}`;
  }
}

function renderInsightConversation(turns) {
  const container = document.getElementById("insightConversation");
  if (!container) return;
  container.innerHTML = "";
  if (!turns || !turns.length) {
    container.textContent = "No conversation available.";
    return;
  }
  turns.forEach((turn) => {
    const speaker = turn.speaker;
    if (speaker !== "USER" && speaker !== "COUNTERPARTY") return;
    const bubble = document.createElement("div");
    bubble.className = `bubble ${speaker === "USER" ? "user" : "counterparty"}`;
    bubble.textContent = turn.message_text || "";
    container.appendChild(bubble);
  });
}

function populateDebugRuns(runs = []) {
  if (!debugRunSelect) return;
  debugRunSelect.innerHTML = "";
  if (!runs.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No runs yet";
    debugRunSelect.appendChild(option);
    return;
  }
  runs.forEach((run, index) => {
    const option = document.createElement("option");
    option.value = run.run_id;
    const label = `${index + 1}. ${run.outcome} · ${run.run_id.slice(0, 8)}`;
    option.textContent = label;
    debugRunSelect.appendChild(option);
  });
}

async function refreshDebugRuns() {
  if (!debugRunSelect) return;
  if (!state.caseId) {
    populateDebugRuns([]);
    if (debugStatus) debugStatus.textContent = "Create a case and run simulations to see traces.";
    return;
  }
  if (debugStatus) debugStatus.textContent = "Loading runs...";
  try {
    const res = await fetch(`/cases/${state.caseId}/runs`);
    if (!res.ok) throw new Error(await res.text());
    const runs = await res.json();
    state.runs = runs || [];
    state.debugRunsAll = state.runs;
    debugTraceCache.clear();
    populateDebugRuns(state.debugRunsAll);
    if (debugStatus) debugStatus.textContent = `Loaded ${state.runs.length} run(s).`;
  } catch (err) {
    if (debugStatus) debugStatus.textContent = `Error loading runs: ${err.message}`;
  }
}

async function searchDebugTraces() {
  if (!debugRunSelect || !state.caseId) {
    if (debugStatus) debugStatus.textContent = "Run a simulation first.";
    return;
  }
  const query = (debugSearchInput?.value || "").trim().toLowerCase();
  if (!query) {
    populateDebugRuns(state.debugRunsAll || state.runs);
    if (debugStatus) debugStatus.textContent = "Search cleared.";
    return;
  }
  if (debugStatus) debugStatus.textContent = `Searching for "${query}"...`;
  const runs = state.debugRunsAll || state.runs || [];
  const matches = [];
  for (const run of runs) {
    if (!run?.run_id) continue;
    let haystack = debugTraceCache.get(run.run_id);
    if (!haystack) {
      try {
        const res = await fetch(`/runs/${run.run_id}/trace`);
        if (!res.ok) throw new Error(await res.text());
        const trace = await res.json();
        haystack = JSON.stringify(trace).toLowerCase();
        debugTraceCache.set(run.run_id, haystack);
      } catch (err) {
        continue;
      }
    }
    if (haystack.includes(query)) {
      matches.push(run);
    }
  }
  populateDebugRuns(matches);
  if (debugStatus) {
    debugStatus.textContent = matches.length
      ? `Found ${matches.length} run(s) matching "${query}".`
      : `No runs matched "${query}".`;
  }
}

async function autoloadCaseData(caseId) {
  if (!caseId) return;
  await Promise.all([loadRunsForCase(caseId), loadInsightsForCase(caseId)]);
}

async function loadRunsForCase(caseId) {
  const runStatus = document.getElementById("runProgress");
  const runMeta = document.getElementById("runProgressMeta");
  if (runStatus) runStatus.textContent = "Loading runs...";
  if (runMeta) runMeta.textContent = "";
  try {
    const res = await fetch(`/cases/${caseId}/runs`);
    if (!res.ok) throw new Error(await res.text());
    const runs = await res.json();
    state.runs = runs || [];
    const sessionCandidate = [...state.runs].reverse().find((run) => run.session_id);
    state.sessionId = sessionCandidate?.session_id || null;
    renderRuns();
    if (runStatus) runStatus.textContent = `Loaded ${state.runs.length} runs.`;
    if (runMeta) runMeta.textContent = "";
    refreshDebugRuns();
    await fetchPendingQuestion();
    updateAskInfoBudgetStatus(parseInt(maxQuestionsInput?.value, 10) || 0);
  } catch (err) {
    if (runStatus) runStatus.textContent = `Error loading runs: ${err.message}`;
  }
}

async function loadInsightsForCase(caseId) {
  const status = document.getElementById("insightsStatus");
  if (status) status.textContent = "Loading insights...";
  try {
    const res = await fetch(`/cases/${caseId}/insights`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    document.getElementById("insightsOutput").textContent = formatJson(data);
    renderInsights(data);
    if (status) status.textContent = `Loaded ${data?.turns_to_termination?.length || 0} runs.`;
  } catch (err) {
    if (status) status.textContent = `Error: ${err.message}`;
  }
}

async function filterRunsByFallback(expectFallback) {
  if (!debugRunSelect || !state.caseId) {
    if (debugStatus) debugStatus.textContent = "Run a simulation first.";
    return;
  }
  const runs = state.debugRunsAll || state.runs || [];
  if (!runs.length) {
    populateDebugRuns([]);
    if (debugStatus) debugStatus.textContent = "No runs available.";
    return;
  }
  if (debugStatus) {
    debugStatus.textContent = expectFallback ? "Filtering runs with fallback..." : "Filtering runs without fallback...";
  }
  const matches = [];
  for (const run of runs) {
    if (!run?.run_id) continue;
    let haystack = debugTraceCache.get(run.run_id);
    if (!haystack) {
      try {
        const res = await fetch(`/runs/${run.run_id}/trace`);
        if (!res.ok) throw new Error(await res.text());
        const trace = await res.json();
        haystack = JSON.stringify(trace).toLowerCase();
        debugTraceCache.set(run.run_id, haystack);
      } catch (err) {
        continue;
      }
    }
    const hasFallback = haystack.includes("\"fallback_used\": true");
    if (hasFallback === expectFallback) {
      matches.push(run);
    }
  }
  populateDebugRuns(matches);
  if (debugStatus) {
    debugStatus.textContent = matches.length
      ? `Found ${matches.length} run(s).`
      : "No runs matched the fallback filter.";
  }
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
    if (parsed.fallback_used) {
      const fallbackBadge = document.createElement("div");
      fallbackBadge.className = "trace-action";
      const reason = parsed.fallback_reason ? ` (${parsed.fallback_reason})` : "";
      fallbackBadge.textContent = `Fallback used${reason}`;
      message.appendChild(fallbackBadge);
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
