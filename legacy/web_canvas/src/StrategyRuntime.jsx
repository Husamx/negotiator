
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiBase, apiGet, apiPatch, apiPost } from './api.js';

const RUNTIME_PHASES = [
  'Load and validate',
  'Check applicability',
  'Acquire inputs',
  'Execute tools',
  'Resolve branches',
  'Evaluate and gate',
  'Package artifacts'
];

const ACTION_TYPES = [
  { id: 'RESPOND', label: 'Respond', fields: ['Response summary', 'Tone cue'] },
  { id: 'ASK_QUESTION', label: 'Ask question', fields: ['Question intent', 'Question text'] },
  { id: 'COUNTER_ANCHOR', label: 'Counter anchor', fields: ['Counter value', 'Justification'] },
  { id: 'TRADE_REQUEST', label: 'Trade request', fields: ['Give', 'Get'] },
  { id: 'STALL_DEFER', label: 'Stall / defer', fields: ['Reason', 'Next step'] },
  { id: 'WALK_AWAY', label: 'Walk away', fields: ['Boundary statement', 'Exit line'] }
];

const composeActionMessage = (actionId, fieldsByAction) => {
  const action = ACTION_TYPES.find((item) => item.id === actionId);
  if (!action) return '';
  const fields = fieldsByAction?.[actionId] || {};
  const lines = action.fields
    .map((field) => {
      const value = fields[field];
      if (!value) return null;
      return `- ${field}: ${value}`;
    })
    .filter(Boolean);
  if (lines.length === 0) return '';
  return `${action.label}\\n${lines.join('\\n')}`;
};

const EMPTY_STRATEGY = {
  strategy_id: '',
  name: 'Select a strategy',
  summary: 'Choose a strategy to view its inputs and prerequisites.',
  goal: '',
  inputs: [],
  applicability: { prerequisites: [] },
  branches: [],
  steps: [],
  tags: [],
  category: ''
};

const formatDateTime = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const getPathValue = (obj, path) => {
  if (!obj || !path) return undefined;
  const normalized = path.startsWith('/') ? path.slice(1) : path;
  if (!normalized) return obj;
  const parts = normalized.split('/').map((part) => part.replace(/~1/g, '/').replace(/~0/g, '~'));
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    if (Array.isArray(current)) {
      if (part === '-') {
        current = current[current.length - 1];
        continue;
      }
      const index = Number(part);
      if (Number.isNaN(index)) return undefined;
      current = current[index];
      continue;
    }
    current = current[part];
  }
  return current;
};

const evaluatePredicate = (predicate, context) => {
  if (!predicate || !predicate.op) return false;
  const op = predicate.op;
  const value = getPathValue(context, predicate.path);
  if (op === 'EXISTS') {
    return value !== undefined && value !== null && value !== '';
  }
  if (op === 'EQ') {
    return value === predicate.value;
  }
  if (op === 'NEQ') {
    return value !== predicate.value;
  }
  if (op === 'GT') {
    return Number(value) > Number(predicate.value);
  }
  if (op === 'GTE') {
    return Number(value) >= Number(predicate.value);
  }
  if (op === 'LT') {
    return Number(value) < Number(predicate.value);
  }
  if (op === 'LTE') {
    return Number(value) <= Number(predicate.value);
  }
  if (op === 'IN') {
    const values = predicate.values || [];
    if (Array.isArray(value)) {
      return value.some((item) => values.includes(item));
    }
    return values.includes(value);
  }
  if (op === 'CONTAINS') {
    if (typeof value === 'string') {
      return value.toLowerCase().includes(String(predicate.value || '').toLowerCase());
    }
    if (Array.isArray(value)) {
      return value.includes(predicate.value);
    }
  }
  if (op === 'MATCHES') {
    if (!predicate.regex) return false;
    try {
      const regex = new RegExp(predicate.regex, 'i');
      return regex.test(String(value || ''));
    } catch {
      return false;
    }
  }
  return false;
};

const evaluateCondition = (condition, context) => {
  if (!condition || !condition.type) return false;
  if (condition.type === 'PREDICATE') {
    return evaluatePredicate(condition.predicate, context);
  }
  if (condition.type === 'ALL') {
    return (condition.all || []).every((item) => evaluateCondition(item, context));
  }
  if (condition.type === 'ANY') {
    return (condition.any || []).some((item) => evaluateCondition(item, context));
  }
  if (condition.type === 'NOT') {
    return !evaluateCondition(condition.not, context);
  }
  return false;
};

const normalizeScore = (score) => {
  if (score === null || score === undefined) return null;
  const numeric = Number(score);
  if (Number.isNaN(numeric)) return null;
  if (numeric <= 1) return Math.round(numeric * 100);
  return Math.round(numeric);
};

const normalizeInputValue = (value, type) => {
  if (value === null || value === undefined) return '';
  if (type === 'STRING_LIST' || type === 'ISSUE_LIST' || type === 'PACKAGE_LIST') {
    if (Array.isArray(value)) {
      return value.join('\n');
    }
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
};

const coerceInputValue = (value, type) => {
  if (type === 'STRING_LIST' || type === 'ISSUE_LIST' || type === 'PACKAGE_LIST') {
    const raw = String(value || '').trim();
    if (!raw) return [];
    return raw.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
  }
  if (type === 'NUMBER' || type === 'MONEY') {
    const numeric = Number(value);
    return Number.isNaN(numeric) ? value : numeric;
  }
  if (type === 'BOOLEAN') {
    return Boolean(value);
  }
  return value;
};

const buildInputsPayload = (inputDefs, inputValues) => {
  const payload = {};
  const missing = [];
  (inputDefs || []).forEach((definition) => {
    const key = definition.key;
    const rawValue = inputValues[key];
    const isEmpty =
      rawValue === undefined ||
      rawValue === null ||
      rawValue === '' ||
      (Array.isArray(rawValue) && rawValue.length === 0);
    if (isEmpty) {
      if (definition.required) {
        missing.push(definition.label || definition.key);
      }
      return;
    }
    payload[key] = coerceInputValue(rawValue, definition.type);
  });
  return { payload, missing };
};

const formatArtifactText = (artifact) => {
  const content = artifact.content || {};
  if (typeof content.text === 'string') return content.text;
  if (typeof content.draft_text === 'string') return content.draft_text;
  return JSON.stringify(content, null, 2);
};

const summarizePayload = (payload) => {
  if (!payload) return '';
  if (payload.strategy_id) return `Strategy: ${payload.strategy_id}`;
  if (payload.selected_strategy_id) return `Selected: ${payload.selected_strategy_id}`;
  if (payload.content) return String(payload.content).slice(0, 120);
  return JSON.stringify(payload).slice(0, 140);
};

const formatJson = (value) => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const deriveExecutionSummary = (execution) => {
  const artifacts = execution?.artifacts || [];
  const messageDrafts = artifacts.filter((artifact) => artifact.type === 'MESSAGE_DRAFT');
  const checklists = artifacts.filter((artifact) => artifact.type === 'CHECKLIST');
  const otherArtifacts = artifacts.filter(
    (artifact) => artifact.type !== 'MESSAGE_DRAFT' && artifact.type !== 'CHECKLIST'
  );
  const judgeOutputs = execution?.judge_outputs || [];
  const scoreboard = judgeOutputs.map((output) => ({
    label: output.rubric_id || 'Rubric',
    score: normalizeScore(output.overall_score)
  }));
  const flags = judgeOutputs.flatMap((output) => output.flags || []);
  return { messageDrafts, checklists, otherArtifacts, scoreboard, flags };
};

function StrategyLibraryDetail({ strategy, caseSnapshot }) {
  const activeStrategy = strategy || EMPTY_STRATEGY;
  const prerequisites = activeStrategy?.applicability?.prerequisites || [];
  const context = caseSnapshot?.payload || null;
  const prereqStatuses = prerequisites.map((prereq) => {
    if (!context) {
      return { ...prereq, status: 'unknown' };
    }
    const ok = evaluateCondition(prereq.condition, context);
    return { ...prereq, status: ok ? 'ok' : 'missing' };
  });

  const toolChain = useMemo(() => {
    const tools = new Set();
    (activeStrategy.steps || []).forEach((step) => {
      (step.agent_actions || []).forEach((action) => {
        if (action.tool) tools.add(action.tool);
      });
    });
    return Array.from(tools);
  }, [activeStrategy]);

  return (
    <div className="runtime-panel runtime-detail">
      <div className="runtime-panel-title">Strategy details</div>
      <div className="runtime-detail-title">{activeStrategy.name || 'Select a strategy'}</div>
      {activeStrategy.strategy_id && (
        <div className="runtime-detail-meta">{activeStrategy.strategy_id}</div>
      )}
      <p className="runtime-detail-text">{activeStrategy.summary || 'No summary yet.'}</p>
      {activeStrategy.goal && (
        <div className="runtime-detail-section">
          <div className="runtime-detail-label">Goal</div>
          <div className="runtime-detail-text">{activeStrategy.goal}</div>
        </div>
      )}
      {activeStrategy.tags?.length > 0 && (
        <div className="runtime-detail-section">
          <div className="runtime-detail-label">Tags</div>
          <div className="runtime-chip-row">
            {activeStrategy.tags.map((tag) => (
              <span key={tag} className="runtime-chip subtle">{tag}</span>
            ))}
          </div>
        </div>
      )}
      <div className="runtime-detail-section">
        <div className="runtime-detail-label">Inputs</div>
        {activeStrategy.inputs?.length ? (
          <div className="runtime-chip-row">
            {activeStrategy.inputs.map((input) => (
              <span key={input.key} className="runtime-chip">
                {input.label || input.key}
              </span>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No inputs defined.</div>
        )}
      </div>
      <div className="runtime-detail-section">
        <div className="runtime-detail-label">Prerequisites</div>
        {prereqStatuses.length ? (
          <div className="runtime-checklist">
            {prereqStatuses.map((item) => (
              <div key={item.id} className={`runtime-check ${item.status === 'ok' ? 'ok' : item.status === 'missing' ? 'missing' : ''}`}>
                <span>{item.description}</span>
                <span>{item.status === 'unknown' ? 'Unknown' : item.status === 'ok' ? 'Ready' : 'Missing'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No prerequisites listed.</div>
        )}
      </div>
      <div className="runtime-detail-section">
        <div className="runtime-detail-label">Tool chain</div>
        {toolChain.length ? (
          <div className="runtime-tool-list">
            {toolChain.map((tool) => (
              <span key={tool}>{tool}</span>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No tool actions yet.</div>
        )}
      </div>
      {activeStrategy.branches?.length ? (
        <div className="runtime-detail-section">
          <div className="runtime-detail-label">Branches</div>
          <div className="runtime-branch-list">
            {activeStrategy.branches.map((branch) => (
              <div key={branch.branch_id} className="runtime-branch-card">
                <div className="runtime-card-label">{branch.label}</div>
                {branch.recommended_move?.move_type && (
                  <div className="runtime-card-meta">{branch.recommended_move.move_type}</div>
                )}
                {branch.risk_notes && (
                  <div className="runtime-card-text">{branch.risk_notes}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InputField({ definition, value, onChange }) {
  if (!definition) return null;
  const label = definition.label || definition.key;
  const required = definition.required;
  const type = definition.type;
  const help = definition.help;

  if (type === 'BOOLEAN') {
    return (
      <div className="runtime-input-group">
        <label>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) => onChange(definition.key, event.target.checked)}
          />
          {` ${label}${required ? ' *' : ''}`}
        </label>
        {help && <div className="runtime-input-help">{help}</div>}
      </div>
    );
  }

  if (type === 'ENUM' && Array.isArray(definition.enum_values)) {
    return (
      <div className="runtime-input-group">
        <label>{label}{required ? ' *' : ''}</label>
        <select
          value={value || ''}
          onChange={(event) => onChange(definition.key, event.target.value)}
        >
          <option value="">Select...</option>
          {definition.enum_values.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        {help && <div className="runtime-input-help">{help}</div>}
      </div>
    );
  }

  if (type === 'STRING_LIST' || type === 'ISSUE_LIST' || type === 'PACKAGE_LIST') {
    return (
      <div className="runtime-input-group">
        <label>{label}{required ? ' *' : ''}</label>
        <textarea
          rows={3}
          placeholder="Enter one item per line"
          value={value || ''}
          onChange={(event) => onChange(definition.key, event.target.value)}
        />
        {help && <div className="runtime-input-help">{help}</div>}
      </div>
    );
  }

  if (type === 'NUMBER' || type === 'MONEY') {
    return (
      <div className="runtime-input-group">
        <label>{label}{required ? ' *' : ''}</label>
        <input
          type="number"
          value={value || ''}
          onChange={(event) => onChange(definition.key, event.target.value)}
        />
        {help && <div className="runtime-input-help">{help}</div>}
      </div>
    );
  }

  return (
    <div className="runtime-input-group">
      <label>{label}{required ? ' *' : ''}</label>
      <input
        type="text"
        value={value || ''}
        onChange={(event) => onChange(definition.key, event.target.value)}
      />
      {help && <div className="runtime-input-help">{help}</div>}
    </div>
  );
}

function StrategyCanvasScreen({
  strategy,
  caseSnapshot,
  inputValues,
  onInputChange,
  onRunBuild,
  execution,
  running,
  onOpenDecisionLog
}) {
  const prerequisites = strategy?.applicability?.prerequisites || [];
  const context = caseSnapshot?.payload || null;
  const prereqStatuses = prerequisites.map((item) => {
    if (!context) {
      return { ...item, status: 'unknown' };
    }
    const ok = evaluateCondition(item.condition, context);
    return { ...item, status: ok ? 'ok' : 'missing' };
  });

  const { messageDrafts, checklists, otherArtifacts, scoreboard, flags } = deriveExecutionSummary(execution);

  return (
    <div className="runtime-screen runtime-canvas">
      <div className="runtime-column runtime-canvas-left">
        <div className="runtime-panel">
          <div className="runtime-panel-title">Prerequisites</div>
          {prereqStatuses.length ? (
            <div className="runtime-checklist">
              {prereqStatuses.map((item) => (
                <div key={item.id} className={`runtime-check ${item.status === 'ok' ? 'ok' : item.status === 'missing' ? 'missing' : ''}`}>
                  <span>{item.description}</span>
                  <span>{item.status === 'unknown' ? 'Unknown' : item.status === 'ok' ? 'Ready' : 'Missing'}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="runtime-empty">No prerequisites listed.</div>
          )}
          {execution?.trace?.blocked && (
            <div className="runtime-alert">
              <div className="runtime-alert-title">Execution blocked</div>
              <div className="runtime-alert-text">Complete the required prerequisites before running BUILD mode.</div>
            </div>
          )}
        </div>
        <div className="runtime-panel">
          <div className="runtime-panel-title">Runtime phases</div>
          <div className="runtime-phase-list">
            {RUNTIME_PHASES.map((phase, idx) => (
              <div key={phase} className="runtime-phase">
                <span className="runtime-phase-index">{idx + 1}</span>
                <span>{phase}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="runtime-column runtime-canvas-center">
        <div className="runtime-panel">
          <div className="runtime-panel-title">Strategy inputs</div>
          {strategy?.inputs?.length ? (
            <div className="runtime-input-grid">
              {strategy.inputs.map((input) => (
                <InputField
                  key={input.key}
                  definition={input}
                  value={inputValues[input.key]}
                  onChange={onInputChange}
                />
              ))}
            </div>
          ) : (
            <div className="runtime-empty">No inputs configured for this strategy.</div>
          )}
          <div className="runtime-input-footer">
            <button
              className="runtime-primary"
              onClick={onRunBuild}
              disabled={running || !strategy?.strategy_id}
            >
              {running ? 'Running...' : 'Run BUILD mode'}
            </button>
            <span>{caseSnapshot ? `Case updated ${formatDateTime(caseSnapshot.updated_at)}` : 'No case snapshot loaded.'}</span>
          </div>
        </div>
        <div className="runtime-panel">
          <div className="runtime-panel-title">Artifacts</div>
          {messageDrafts.length === 0 && checklists.length === 0 && otherArtifacts.length === 0 && (
            <div className="runtime-empty">Run BUILD mode to generate artifacts.</div>
          )}
          {messageDrafts.length > 0 && (
            <div className="runtime-artifact-grid">
              {messageDrafts.map((draft) => (
                <div key={draft.artifact_id} className="runtime-card runtime-artifact">
                  <div className="runtime-card-label">{draft.title || 'Message draft'}</div>
                  <div className="runtime-card-meta">{draft.metadata?.tone || 'Draft'}</div>
                  <div className="runtime-card-text">{formatArtifactText(draft)}</div>
                </div>
              ))}
            </div>
          )}
          {checklists.length > 0 && (
            <div className="runtime-checklist">
              {checklists.map((checklist) => (
                <div key={checklist.artifact_id} className="runtime-check missing">
                  <span>{checklist.title}</span>
                  <span>{(checklist.content?.items || []).length} items</span>
                </div>
              ))}
            </div>
          )}
          {otherArtifacts.length > 0 && (
            <div className="runtime-checklist">
              {otherArtifacts.map((artifact) => (
                <div key={artifact.artifact_id} className="runtime-check">
                  <span>{artifact.title}</span>
                  <span>{artifact.type}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="runtime-column runtime-canvas-right">
        <div className="runtime-panel">
          <div className="runtime-panel-title">Scoreboard</div>
          {scoreboard.length ? (
            <div className="runtime-scoreboard">
              {scoreboard.map((item) => (
                <div key={item.label} className="runtime-score-item">
                  <div className="runtime-score-label">
                    <span>{item.label}</span>
                    <span>{item.score ?? '--'}</span>
                  </div>
                  <div className="runtime-score-bar">
                    <div className="runtime-score-fill" style={{ width: `${item.score || 0}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="runtime-empty">No judge scores yet.</div>
          )}
        </div>
        <div className="runtime-panel">
          <div className="runtime-panel-title">Safety gates</div>
          {flags.length ? (
            <div className="runtime-gate-list">
              {flags.map((flag, index) => (
                <div key={`${flag.flag_id}-${index}`} className={`runtime-gate ${flag.severity === 'BLOCK_SEND' ? 'blocked' : ''}`}>
                  <div>
                    <div className="runtime-gate-label">{flag.flag_id}</div>
                    <div className="runtime-gate-detail">{flag.message}</div>
                  </div>
                  <span className="runtime-gate-status">{flag.severity}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="runtime-empty">No gate violations.</div>
          )}
          <button className="runtime-secondary" onClick={onOpenDecisionLog}>Review decision log</button>
        </div>
        {execution?.case_patches?.length ? (
          <div className="runtime-panel">
            <div className="runtime-panel-title">Case patches</div>
            <div className="runtime-checklist">
              {execution.case_patches.map((patch, index) => (
                <div key={`${patch.op}-${index}`} className="runtime-check">
                  <span>{patch.op || 'patch'}</span>
                  <span>{patch.path || ''}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function GuidedFlowScreen({
  sessionId,
  selection,
  selectionLoading,
  strategy,
  caseSnapshot,
  sessionDetail,
  manualStrategyId,
  objectiveDraft,
  onObjectiveChange,
  onSaveObjectives,
  objectiveSaving,
  inputValues,
  onInputChange,
  onRunSelection,
  onRunBuild,
  execution,
  running,
  onOpenDecisionLog,
  onSwitchToAdvanced,
  actionType,
  fieldValues,
  onFieldChange,
  onSendAction,
  sending,
  streamingText,
  pendingMessage
}) {
  const prerequisites = strategy?.applicability?.prerequisites || [];
  const context = caseSnapshot?.payload || null;
  const prereqStatuses = prerequisites.map((item) => {
    if (!context) {
      return { ...item, status: 'unknown' };
    }
    const ok = evaluateCondition(item.condition, context);
    return { ...item, status: ok ? 'ok' : 'missing' };
  });
  const hasMissingPrereq = prereqStatuses.some((item) => item.status === 'missing');

  const { messageDrafts, checklists, otherArtifacts, scoreboard, flags } = deriveExecutionSummary(execution);
  const { missing } = buildInputsPayload(strategy?.inputs || [], inputValues);
  const requiredInputs = (strategy?.inputs || []).filter((input) => input.required);
  const optionalInputs = (strategy?.inputs || []).filter((input) => !input.required);

  const ranked = selection?.selection_payload?.response?.ranked_strategies || [];
  const topRanked = ranked[0];
  const recommendationReason =
    topRanked?.why ||
    topRanked?.reason ||
    topRanked?.rationale ||
    selection?.selection_payload?.response?.summary ||
    '';

  const hasSession = Boolean(sessionId);
  const hasSelection = Boolean(selection && (selection.selected_strategy_id || ranked.length));
  const hasStrategy = Boolean(strategy?.strategy_id);
  const hasExecution = Boolean(execution);
  const canRunBuild = hasSession && hasStrategy && missing.length === 0 && !hasMissingPrereq && !running;

  const messages = sessionDetail?.messages || [];
  const lastCounterparty = messages.filter((msg) => msg.role === 'counterparty').slice(-1)[0];
  const activeAction = ACTION_TYPES.find((action) => action.id === actionType) || ACTION_TYPES[0];

  const [showOptionalInputs, setShowOptionalInputs] = useState(false);

  let nextStepText = 'Select a session to begin.';
  if (hasSession) {
    if (!hasSelection && selectionLoading) {
      nextStepText = 'Selecting the best strategy for this case.';
    } else if (!hasSelection) {
      nextStepText = 'Run strategy selection to pick the best move.';
    } else if (!hasStrategy) {
      nextStepText = 'Loading the strategy details.';
    } else if (hasMissingPrereq) {
      nextStepText = 'Complete the missing prerequisites in the CaseSnapshot.';
    } else if (missing.length) {
      nextStepText = `Fill required inputs: ${missing.slice(0, 3).join(', ')}${missing.length > 3 ? '...' : ''}`;
    } else if (!hasExecution) {
      nextStepText = 'Run BUILD mode to generate a draft.';
    } else {
      nextStepText = 'Send a roleplay response when you are ready.';
    }
  }

  return (
    <div className="runtime-screen runtime-guided">
      <div className="runtime-panel runtime-guided-callout">
        <div className="runtime-panel-title">Guided mode</div>
        <div className="runtime-guided-summary">
          <div>{nextStepText}</div>
          <div className="runtime-guided-actions">
            <button className="runtime-secondary" onClick={onSwitchToAdvanced}>
              Switch to advanced view
            </button>
            <button className="runtime-secondary" onClick={onOpenDecisionLog}>
              View decision log
            </button>
          </div>
        </div>
      </div>

      <div className="runtime-guided-grid">
        <div className="runtime-guided-column">
          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 1: Session</div>
            <div className="runtime-step">
              <div>{hasSession ? `Session #${sessionId}` : 'Select a session from the left panel.'}</div>
              <span className={`runtime-step-status ${hasSession ? 'ok' : 'missing'}`}>
                {hasSession ? 'Ready' : 'Missing'}
              </span>
            </div>
            <div className="runtime-guided-note">
              The session anchors the CaseSnapshot and decides what the runtime can pull.
            </div>
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 2: Strategy (auto-selected)</div>
            <div className="runtime-step">
              <div>{hasSelection ? 'Recommendation ready.' : 'No recommendation yet.'}</div>
              <span className={`runtime-step-status ${hasSelection ? 'ok' : 'missing'}`}>
                {hasSelection ? 'Ready' : 'Missing'}
              </span>
            </div>
            {hasSelection ? (
              <div className="runtime-guided-strategy">
                <div className="runtime-card">
                  <div className="runtime-card-label">{strategy?.name || 'Strategy'}</div>
                  <div className="runtime-card-meta">{strategy?.strategy_id || topRanked?.strategy_id || '--'}</div>
                  <div className="runtime-card-text">{strategy?.summary || 'Auto-selected for this case.'}</div>
                  <div className="runtime-chip-row">
                    {typeof topRanked?.score === 'number' && (
                      <span className="runtime-chip subtle">Fit {Math.round(topRanked.score * 100)}%</span>
                    )}
                    {strategy?.category && <span className="runtime-chip subtle">{strategy.category}</span>}
                    {manualStrategyId && manualStrategyId === strategy?.strategy_id && (
                      <span className="runtime-chip subtle">Manual override</span>
                    )}
                  </div>
                </div>
                {recommendationReason && (
                  <div className="runtime-guided-note">{recommendationReason}</div>
                )}
              </div>
            ) : (
              <div className="runtime-empty">Run selection to let the agent choose a strategy.</div>
            )}
            <div className="runtime-guided-actions">
              <button
                className="runtime-secondary"
                onClick={onRunSelection}
                disabled={!hasSession || selectionLoading}
              >
                {selectionLoading ? 'Selecting...' : 'Re-run selection'}
              </button>
            </div>
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 3: Set objectives</div>
            <div className="runtime-guided-note">
              Most strategies require target, acceptable range, and walk-away. These drive gating and critiques.
            </div>
            <div className="runtime-input-grid">
              <div className="runtime-input-group">
                <label>Target (ideal outcome)</label>
                <input
                  type="text"
                  value={objectiveDraft?.target || ''}
                  onChange={(event) => onObjectiveChange('target', event.target.value)}
                  placeholder="Example: $120k base salary"
                />
              </div>
              <div className="runtime-input-group">
                <label>Acceptable (range or floor)</label>
                <input
                  type="text"
                  value={objectiveDraft?.acceptable || ''}
                  onChange={(event) => onObjectiveChange('acceptable', event.target.value)}
                  placeholder="Example: $105k base"
                />
              </div>
              <div className="runtime-input-group">
                <label>Walk-away (no-go)</label>
                <input
                  type="text"
                  value={objectiveDraft?.walk_away || ''}
                  onChange={(event) => onObjectiveChange('walk_away', event.target.value)}
                  placeholder="Example: below $95k"
                />
              </div>
              <div className="runtime-input-group">
                <label>Notes (optional)</label>
                <input
                  type="text"
                  value={objectiveDraft?.notes || ''}
                  onChange={(event) => onObjectiveChange('notes', event.target.value)}
                  placeholder="Any nuance or priorities."
                />
              </div>
            </div>
            <div className="runtime-guided-actions">
              <button className="runtime-secondary" onClick={onSaveObjectives} disabled={!sessionId || objectiveSaving}>
                {objectiveSaving ? 'Saving...' : 'Save objectives'}
              </button>
              <span className="runtime-guided-note">Saved objectives immediately update prerequisites.</span>
            </div>
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 4: Confirm inputs</div>
            <div className="runtime-guided-note">
              Inputs are prefilled from the CaseSnapshot and strategy defaults. Edit anything that looks off.
            </div>
            {requiredInputs.length ? (
              <div className="runtime-input-grid">
                {requiredInputs.map((input) => (
                  <InputField
                    key={input.key}
                    definition={input}
                    value={inputValues[input.key]}
                    onChange={onInputChange}
                  />
                ))}
              </div>
            ) : (
              <div className="runtime-empty">No required inputs for this strategy.</div>
            )}
            {optionalInputs.length > 0 && (
              <button
                className="runtime-secondary"
                onClick={() => setShowOptionalInputs((prev) => !prev)}
              >
                {showOptionalInputs ? 'Hide optional inputs' : 'Show optional inputs'}
              </button>
            )}
            {showOptionalInputs && optionalInputs.length > 0 && (
              <div className="runtime-input-grid">
                {optionalInputs.map((input) => (
                  <InputField
                    key={input.key}
                    definition={input}
                    value={inputValues[input.key]}
                    onChange={onInputChange}
                  />
                ))}
              </div>
            )}
            {missing.length > 0 && (
              <div className="runtime-alert">
                <div className="runtime-alert-title">Missing required inputs</div>
                <div className="runtime-alert-text">{missing.join(', ')}</div>
              </div>
            )}
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 5: Run BUILD</div>
            {prereqStatuses.length > 0 && (
              <div className="runtime-checklist">
                {prereqStatuses.map((item) => (
                  <div key={item.id} className={`runtime-check ${item.status === 'ok' ? 'ok' : item.status === 'missing' ? 'missing' : ''}`}>
                    <span>{item.description}</span>
                    <span>{item.status === 'unknown' ? 'Unknown' : item.status === 'ok' ? 'Ready' : 'Missing'}</span>
                  </div>
                ))}
              </div>
            )}
            {hasMissingPrereq && (
              <div className="runtime-alert">
                <div className="runtime-alert-title">Execution blocked</div>
                <div className="runtime-alert-text">Complete the missing prerequisites before running BUILD.</div>
              </div>
            )}
            <div className="runtime-guided-actions">
              <button className="runtime-primary" onClick={onRunBuild} disabled={!canRunBuild}>
                {running ? 'Running...' : 'Run BUILD mode'}
              </button>
              <span className="runtime-guided-note">
                {caseSnapshot ? `Case updated ${formatDateTime(caseSnapshot.updated_at)}` : 'No case snapshot loaded.'}
              </span>
            </div>
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Step 6: Send to roleplay</div>
            <div className="runtime-guided-note">
              This sends a standard response move. Switch to advanced view for other move types.
            </div>
            <div className="runtime-composer-fields">
              {activeAction.fields.map((field) => (
                <div key={field} className="runtime-input-group">
                  <label>{field}</label>
                  <input
                    type="text"
                    value={fieldValues?.[actionType]?.[field] || ''}
                    onChange={(event) => onFieldChange(actionType, field, event.target.value)}
                    placeholder={`Enter ${field.toLowerCase()}...`}
                  />
                </div>
              ))}
            </div>
            <div className="runtime-composer-footer">
              <button className="runtime-primary" onClick={onSendAction} disabled={sending || !hasSession}>
                {sending ? 'Sending...' : 'Send to roleplay'}
              </button>
              <span>Messages are sent to the roleplay engine.</span>
            </div>
          </div>
        </div>

        <div className="runtime-guided-column">
          <div className="runtime-panel">
            <div className="runtime-panel-title">Latest counterparty move</div>
            {streamingText && (
              <>
                <div className="runtime-move-type">Streaming reply</div>
                <div className="runtime-card-text">{streamingText}</div>
              </>
            )}
            {!streamingText && lastCounterparty && (
              <>
                <div className="runtime-move-type">Last message</div>
                <div className="runtime-card-text">{lastCounterparty.content}</div>
              </>
            )}
            {!streamingText && !lastCounterparty && (
              <div className="runtime-empty">No counterparty message yet.</div>
            )}
            {pendingMessage && (
              <div className="runtime-alert">
                <div className="runtime-alert-title">Last action sent</div>
                <div className="runtime-alert-text">{pendingMessage}</div>
              </div>
            )}
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Draft output</div>
            {messageDrafts.length === 0 && checklists.length === 0 && otherArtifacts.length === 0 && (
              <div className="runtime-empty">Run BUILD mode to generate artifacts.</div>
            )}
            {messageDrafts.length > 0 && (
              <div className="runtime-artifact-grid">
                {messageDrafts.map((draft) => (
                  <div key={draft.artifact_id} className="runtime-card runtime-artifact">
                    <div className="runtime-card-label">{draft.title || 'Message draft'}</div>
                    <div className="runtime-card-meta">{draft.metadata?.tone || 'Draft'}</div>
                    <div className="runtime-card-text">{formatArtifactText(draft)}</div>
                  </div>
                ))}
              </div>
            )}
            {checklists.length > 0 && (
              <div className="runtime-checklist">
                {checklists.map((checklist) => (
                  <div key={checklist.artifact_id} className="runtime-check missing">
                    <span>{checklist.title}</span>
                    <span>{(checklist.content?.items || []).length} items</span>
                  </div>
                ))}
              </div>
            )}
            {otherArtifacts.length > 0 && (
              <div className="runtime-checklist">
                {otherArtifacts.map((artifact) => (
                  <div key={artifact.artifact_id} className="runtime-check">
                    <span>{artifact.title}</span>
                    <span>{artifact.type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="runtime-panel">
            <div className="runtime-panel-title">Scoreboard and gates</div>
            {scoreboard.length ? (
              <div className="runtime-scoreboard">
                {scoreboard.map((item) => (
                  <div key={item.label} className="runtime-score-item">
                    <div className="runtime-score-label">
                      <span>{item.label}</span>
                      <span>{item.score ?? '--'}</span>
                    </div>
                    <div className="runtime-score-bar">
                      <div className="runtime-score-fill" style={{ width: `${item.score || 0}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="runtime-empty">No judge scores yet.</div>
            )}
            {flags.length ? (
              <div className="runtime-gate-list">
                {flags.map((flag, index) => (
                  <div key={`${flag.flag_id}-${index}`} className={`runtime-gate ${flag.severity === 'BLOCK_SEND' ? 'blocked' : ''}`}>
                    <div>
                      <div className="runtime-gate-label">{flag.flag_id}</div>
                      <div className="runtime-gate-detail">{flag.message}</div>
                    </div>
                    <span className="runtime-gate-status">{flag.severity}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="runtime-empty">No gate violations.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function RoleplayArenaScreen({
  caseSnapshot,
  sessionDetail,
  actionType,
  onActionTypeChange,
  fieldValues,
  onFieldChange,
  onSendAction,
  sending,
  streamingText,
  pendingMessage
}) {
  const timeline = caseSnapshot?.payload?.timeline?.recent_events || [];
  const issues = caseSnapshot?.payload?.issues || [];
  const messages = sessionDetail?.messages || [];
  const lastCounterparty = messages.filter((msg) => msg.role === 'counterparty').slice(-1)[0];
  const activeAction = ACTION_TYPES.find((action) => action.id === actionType) || ACTION_TYPES[0];

  return (
    <div className="runtime-screen runtime-arena">
      <div className="runtime-panel runtime-timeline">
        <div className="runtime-panel-title">Timeline</div>
        {timeline.length ? (
          <div className="runtime-timeline-list">
            {timeline.map((event) => (
              <div key={event.event_id} className="runtime-card runtime-timeline-card">
                <div className="runtime-card-meta">{formatDateTime(event.ts)}</div>
                <div className="runtime-card-text">{event.summary || event.raw_text}</div>
                <div className="runtime-chip-row">
                  <span className="runtime-chip subtle">{event.type}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No timeline events yet.</div>
        )}
      </div>
      <div className="runtime-panel runtime-move-card">
        <div className="runtime-panel-title">Counterparty move</div>
        {streamingText && (
          <>
            <div className="runtime-move-type">Streaming reply</div>
            <div className="runtime-card-text">{streamingText}</div>
          </>
        )}
        {!streamingText && lastCounterparty && (
          <>
            <div className="runtime-move-type">Last message</div>
            <div className="runtime-card-text">{lastCounterparty.content}</div>
          </>
        )}
        {!streamingText && !lastCounterparty && (
          <div className="runtime-empty">No counterparty message yet.</div>
        )}
        {pendingMessage && (
          <div className="runtime-alert">
            <div className="runtime-alert-title">Last action sent</div>
            <div className="runtime-alert-text">{pendingMessage}</div>
          </div>
        )}
      </div>
      <div className="runtime-panel runtime-deal-board">
        <div className="runtime-panel-title">Deal board</div>
        {issues.length ? (
          <div className="runtime-deal-table">
            {issues.map((issue) => (
              <div key={issue.issue_id} className="runtime-deal-row">
                <div>
                  <div className="runtime-deal-label">{issue.name}</div>
                  <div className="runtime-deal-meta">Priority {issue.priority}</div>
                </div>
                <div className="runtime-deal-target">
                  Mine: {issue.my_position ?? 'N/A'} | Theirs: {issue.their_position ?? 'N/A'}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No issues captured yet.</div>
        )}
      </div>
      <div className="runtime-panel runtime-composer">
        <div className="runtime-panel-title">Typed action composer</div>
        <div className="runtime-action-row">
          {ACTION_TYPES.map((action) => (
            <button
              key={action.id}
              className={`runtime-chip-button ${actionType === action.id ? 'active' : ''}`}
              onClick={() => onActionTypeChange(action.id)}
            >
              {action.label}
            </button>
          ))}
        </div>
        <div className="runtime-composer-fields">
          {activeAction.fields.map((field) => (
            <div key={field} className="runtime-input-group">
              <label>{field}</label>
              <input
                type="text"
                value={fieldValues?.[actionType]?.[field] || ''}
                onChange={(event) => onFieldChange(actionType, field, event.target.value)}
                placeholder={`Enter ${field.toLowerCase()}...`}
              />
            </div>
          ))}
        </div>
        <div className="runtime-composer-footer">
          <button className="runtime-primary" onClick={onSendAction} disabled={sending}>
            {sending ? 'Sending...' : 'Send to roleplay'}
          </button>
          <span>Messages are sent to the roleplay engine.</span>
        </div>
      </div>
    </div>
  );
}

function CriteriaVaultScreen({ caseSnapshot }) {
  const benchmarks = caseSnapshot?.payload?.benchmarks || {};
  const sources = benchmarks.sources || [];
  const claims = benchmarks.claims || [];
  const constraints = caseSnapshot?.payload?.constraints || [];

  return (
    <div className="runtime-screen runtime-vault">
      <div className="runtime-panel">
        <div className="runtime-panel-title">Sources</div>
        {sources.length ? (
          <div className="runtime-source-list">
            {sources.map((source, index) => (
              <div key={`${source.title || source.name}-${index}`} className="runtime-source-card">
                <div>
                  <div className="runtime-source-name">{source.title || source.name || 'Source'}</div>
                  <div className="runtime-source-meta">{source.type || 'Reference'}</div>
                </div>
                <span className="runtime-source-status ok">{source.credibility || 'Captured'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No benchmark sources yet.</div>
        )}
      </div>
      <div className="runtime-panel">
        <div className="runtime-panel-title">Claims</div>
        {claims.length ? (
          <div className="runtime-claim-list">
            {claims.map((claim, index) => (
              <div key={`${claim.claim || claim.text}-${index}`} className="runtime-claim-card">
                <div className="runtime-card-text">{claim.claim || claim.text || 'Claim'}</div>
                <div className="runtime-claim-meta">Source: {claim.source || 'Unknown'}</div>
                <span className="runtime-claim-status ok">{claim.status || 'OK'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No benchmark claims captured.</div>
        )}
        {constraints.length > 0 && (
          <div className="runtime-alert">
            <div className="runtime-alert-title">Constraints observed</div>
            <div className="runtime-alert-text">
              {constraints.slice(0, 3).map((constraint) => constraint.description).join(' | ')}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StakeholderBoardScreen({ caseSnapshot }) {
  const parties = caseSnapshot?.payload?.parties || {};
  const stakeholders = caseSnapshot?.payload?.stakeholders || [];
  const cards = [...stakeholders];
  if (parties.me) {
    cards.push({ name: parties.me.name, role: parties.me.role || 'You', status: 'Primary' });
  }
  if (parties.counterpart) {
    cards.push({ name: parties.counterpart.name, role: parties.counterpart.role || 'Counterparty', status: 'Primary' });
  }

  return (
    <div className="runtime-screen runtime-stakeholders">
      <div className="runtime-panel">
        <div className="runtime-panel-title">Stakeholders</div>
        {cards.length ? (
          <div className="runtime-stakeholder-grid">
            {cards.map((person, index) => (
              <div key={`${person.name}-${index}`} className="runtime-card runtime-stakeholder">
                <div className="runtime-card-label">{person.name || 'Stakeholder'}</div>
                <div className="runtime-card-meta">{person.role || 'Role'}</div>
                <div className="runtime-card-text">Influence: {person.influence || 'Unknown'}</div>
                <span className="runtime-pill ok">{person.status || 'Active'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="runtime-empty">No stakeholders captured.</div>
        )}
      </div>
      <div className="runtime-panel">
        <div className="runtime-panel-title">Sequencing plan</div>
        <div className="runtime-empty">Sequencing is managed in the planner (not yet wired).</div>
      </div>
    </div>
  );
}

function DecisionLogModal({ events, onClose }) {
  const entries = Array.isArray(events) ? events : [];

  return (
    <div className="runtime-modal-backdrop" onClick={onClose}>
      <div className="runtime-modal" onClick={(event) => event.stopPropagation()}>
        <div className="runtime-modal-header">
          <div>
            <div className="runtime-modal-title">Decision log</div>
            <div className="runtime-modal-subtitle">Session events and strategy actions.</div>
          </div>
          <button className="runtime-secondary" onClick={onClose}>Close</button>
        </div>
        <div className="runtime-log-list">
          {entries.length ? (
            entries.map((event) => (
              <div key={event.id} className="runtime-log-entry">
                <div className="runtime-log-meta">
                  <span>{formatDateTime(event.created_at)}</span>
                  <span>{event.event_type}</span>
                </div>
                <div className="runtime-log-detail">{summarizePayload(event.payload)}</div>
                {(event.payload?.model_request || event.payload?.model_response || event.payload?.model_output_raw) && (
                  <details className="runtime-log-details">
                    <summary>Model input/output</summary>
                    {event.payload?.model_request && (
                      <div className="runtime-log-section">
                        <div className="runtime-log-label">Model request</div>
                        <pre className="runtime-log-json">{formatJson(event.payload.model_request)}</pre>
                      </div>
                    )}
                    {event.payload?.model_response && (
                      <div className="runtime-log-section">
                        <div className="runtime-log-label">Model response</div>
                        <pre className="runtime-log-json">{formatJson(event.payload.model_response)}</pre>
                      </div>
                    )}
                    {event.payload?.model_output_raw && (
                      <div className="runtime-log-section">
                        <div className="runtime-log-label">Model output (raw)</div>
                        <pre className="runtime-log-json">{String(event.payload.model_output_raw)}</pre>
                      </div>
                    )}
                  </details>
                )}
              </div>
            ))
          ) : (
            <div className="runtime-empty">No decision log events yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function RuntimeNotice({ message, onDismiss, tone = 'info' }) {
  if (!message) {
    return null;
  }

  return (
    <div className={`runtime-notice ${tone}`}>
      <span>{message}</span>
      <button className="runtime-secondary" onClick={onDismiss}>Dismiss</button>
    </div>
  );
}

function SessionPanel({
  userId,
  onUserIdChange,
  sessions,
  sessionId,
  onSelectSession,
  onRefreshSessions,
  selection,
  onRunSelection,
  selectionLoading,
  guidedMode,
  onSelectStrategy
}) {
  const ranked = selection?.selection_payload?.response?.ranked_strategies || [];

  return (
    <div className="runtime-panel">
      <div className="runtime-panel-title">Session</div>
      <label className="runtime-input-group">
        <span>User ID</span>
        <input
          type="text"
          value={userId}
          onChange={(event) => onUserIdChange(event.target.value)}
          placeholder="1"
        />
      </label>
      <button className="runtime-secondary" onClick={onRefreshSessions}>Reload sessions</button>
      {guidedMode && (
        <div className="runtime-input-help">
          Guided mode auto-selects a strategy when you pick a session.
        </div>
      )}
      <div className="runtime-session-list">
        {sessions.length === 0 && <div className="runtime-empty">No sessions yet.</div>}
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`runtime-session-chip ${sessionId === String(session.id) ? 'active' : ''}`}
            onClick={() => onSelectSession(String(session.id))}
          >
            <div>{session.title || 'Session'}</div>
            <small>{session.template_id}</small>
          </button>
        ))}
      </div>
      <div className="runtime-panel-title">Strategy selection</div>
      {ranked.length ? (
        <div className="runtime-checklist">
          {ranked.slice(0, 3).map((item) => (
            <button
              key={item.strategy_id}
              type="button"
              className="runtime-check ok runtime-check-button"
              onClick={() => onSelectStrategy?.(item.strategy_id)}
            >
              <span>{item.strategy_id}</span>
              <span>{Math.round(item.score * 100)}%</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="runtime-empty">No selection yet.</div>
      )}
      <button className="runtime-secondary" onClick={onRunSelection} disabled={selectionLoading || !sessionId}>
        {selectionLoading ? 'Running...' : 'Run selection'}
      </button>
    </div>
  );
}

function StrategyLibraryScreen({
  categories,
  strategies,
  activeCategory,
  onSelectCategory,
  selectedStrategyId,
  onSelectStrategy,
  detailStrategy,
  caseSnapshot
}) {
  return (
    <div className="runtime-screen runtime-library">
      <div className="runtime-library-main">
        <div className="runtime-hero">
          <div>
            <div className="runtime-hero-title">Strategy library</div>
            <div className="runtime-hero-subtitle">
              Strategy packs loaded from the backend with real inputs and execution.
            </div>
            <div className="runtime-hero-stats">
              <div>
                <div className="runtime-hero-label">Selected strategy</div>
                <div className="runtime-hero-value">{detailStrategy?.name || 'None'}</div>
              </div>
              <div>
                <div className="runtime-hero-label">Case stage</div>
                <div className="runtime-hero-value">{caseSnapshot?.payload?.stage || 'Unknown'}</div>
              </div>
              <div>
                <div className="runtime-hero-label">Tool chain</div>
                <div className="runtime-hero-value">Retrieve to Draft to Critique</div>
              </div>
            </div>
          </div>
          <div className="runtime-panel runtime-hero-panel">
            <div className="runtime-panel-title">Runtime core</div>
            <div className="runtime-phase-list">
              {RUNTIME_PHASES.map((phase, idx) => (
                <div key={phase} className="runtime-phase">
                  <span className="runtime-phase-index">{idx + 1}</span>
                  <span>{phase}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="runtime-filter-row">
          {categories.map((category) => (
            <button
              key={category.id}
              className={`runtime-chip-button ${activeCategory === category.id ? 'active' : ''}`}
              onClick={() => onSelectCategory(category.id)}
            >
              {category.label} ({category.count})
            </button>
          ))}
        </div>
        <div className="runtime-card-grid">
          {strategies.map((strategy, index) => (
            <button
              key={strategy.strategy_id}
              className={`runtime-card runtime-strategy-card ${selectedStrategyId === strategy.strategy_id ? 'active' : ''}`}
              onClick={() => onSelectStrategy(strategy.strategy_id)}
              style={{ '--delay': `${index * 0.02}s` }}
            >
              <div className="runtime-card-label">{strategy.name}</div>
              <div className="runtime-card-meta">{strategy.category || 'Strategy'}</div>
              <div className="runtime-card-text">{strategy.summary}</div>
              <div className="runtime-chip-row">
                {(strategy.tags || []).slice(0, 3).map((tag) => (
                  <span key={tag} className="runtime-chip subtle">{tag}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>
      <StrategyLibraryDetail strategy={detailStrategy} caseSnapshot={caseSnapshot} />
    </div>
  );
}

export default function StrategyRuntimePage({ onSwitchView, currentView }) {
  const params = new URLSearchParams(window.location.search);
  const [userId, setUserId] = useState(params.get('user_id') || '1');
  const [sessionId, setSessionId] = useState(params.get('session_id') || '');
  const [sessions, setSessions] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [strategyDetail, setStrategyDetail] = useState(EMPTY_STRATEGY);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [manualStrategyId, setManualStrategyId] = useState('');
  const [selection, setSelection] = useState(null);
  const [caseSnapshot, setCaseSnapshot] = useState(null);
  const [sessionDetail, setSessionDetail] = useState(null);
  const [execution, setExecution] = useState(null);
  const [events, setEvents] = useState([]);
  const [inputValues, setInputValues] = useState({});
  const [objectiveDraft, setObjectiveDraft] = useState({
    target: '',
    acceptable: '',
    walk_away: '',
    notes: ''
  });
  const [objectiveSaving, setObjectiveSaving] = useState(false);
  const [inputSeedVersion, setInputSeedVersion] = useState(0);
  const [composerActionType, setComposerActionType] = useState(ACTION_TYPES[0].id);
  const [composerFields, setComposerFields] = useState({});
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [pendingMessage, setPendingMessage] = useState('');
  const [guidedMode, setGuidedMode] = useState(true);
  const [activeScreen, setActiveScreen] = useState('guided');
  const [lastAdvancedScreen, setLastAdvancedScreen] = useState('library');
  const [activeCategory, setActiveCategory] = useState('ALL');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [showDecisionLog, setShowDecisionLog] = useState(false);
  const selectionAttemptRef = useRef({});
  const [loading, setLoading] = useState({
    sessions: false,
    strategies: false,
    selection: false,
    execution: false,
    strategyDetail: false
  });
  const rankedStrategies = selection?.selection_payload?.response?.ranked_strategies || [];
  const recommendedStrategyId =
    selection?.selected_strategy_id || rankedStrategies[0]?.strategy_id || '';
  useEffect(() => {
    const nextParams = new URLSearchParams(window.location.search);
    if (userId) {
      nextParams.set('user_id', userId);
    } else {
      nextParams.delete('user_id');
    }
    if (sessionId) {
      nextParams.set('session_id', sessionId);
    } else {
      nextParams.delete('session_id');
    }
    const search = nextParams.toString();
    const nextUrl = `${window.location.pathname}${search ? `?${search}` : ''}`;
    window.history.replaceState(null, '', nextUrl);
  }, [userId, sessionId]);

  const handleSetActiveScreen = useCallback((screen) => {
    setActiveScreen(screen);
    if (screen !== 'guided') {
      setLastAdvancedScreen(screen);
    }
  }, []);

  const handleSelectStrategy = useCallback((strategyId) => {
    if (!strategyId) return;
    setSelectedStrategyId(strategyId);
    setManualStrategyId(strategyId);
  }, []);

  useEffect(() => {
    if (guidedMode) {
      setActiveScreen('guided');
    } else if (activeScreen === 'guided') {
      setActiveScreen(lastAdvancedScreen);
    }
  }, [guidedMode, activeScreen, lastAdvancedScreen]);

  const refreshStrategies = useCallback(async () => {
    setLoading((prev) => ({ ...prev, strategies: true }));
    setError('');
    try {
      const data = await apiGet('/strategies', userId);
      setStrategies(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading((prev) => ({ ...prev, strategies: false }));
    }
  }, [userId]);

  const refreshSessions = useCallback(async () => {
    setLoading((prev) => ({ ...prev, sessions: true }));
    setError('');
    try {
      const data = await apiGet('/sessions', userId);
      setSessions(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading((prev) => ({ ...prev, sessions: false }));
    }
  }, [userId]);

  const refreshCaseSnapshot = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}/case-snapshot`, userId);
      setCaseSnapshot(data);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  const refreshSelection = useCallback(async () => {
    if (!sessionId) return;
    setError('');
    try {
      const data = await apiGet(`/sessions/${sessionId}/strategy/selection`, userId);
      setSelection(data);
    } catch (err) {
      if (String(err.message).includes('Strategy selection not found')) {
        setSelection(null);
      } else {
        setError(err.message);
      }
    }
  }, [sessionId, userId]);

  const refreshSessionDetail = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}`, userId);
      setSessionDetail(data);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  const refreshEvents = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}/events`, userId);
      setEvents(data || []);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  const refreshLatestExecution = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}/strategy/executions/latest`, userId);
      setExecution(data);
    } catch (err) {
      if (String(err.message).includes('Strategy execution not found')) {
        setExecution(null);
      } else {
        setError(err.message);
      }
    }
  }, [sessionId, userId]);

  const fetchStrategyDetail = useCallback(async (strategyId) => {
    if (!strategyId) {
      setStrategyDetail(EMPTY_STRATEGY);
      return;
    }
    setLoading((prev) => ({ ...prev, strategyDetail: true }));
    setError('');
    try {
      const data = await apiGet(`/strategies/${strategyId}`, userId);
      setStrategyDetail(data || EMPTY_STRATEGY);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading((prev) => ({ ...prev, strategyDetail: false }));
    }
  }, [userId]);

  useEffect(() => {
    refreshStrategies();
  }, [refreshStrategies]);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    if (!sessionId) return;
    setExecution(null);
    setEvents([]);
    setSelection(null);
    setCaseSnapshot(null);
    setSessionDetail(null);
    setStreamingText('');
    setPendingMessage('');
    setComposerFields({});
    setSelectedStrategyId('');
    setManualStrategyId('');
    setStrategyDetail(EMPTY_STRATEGY);
    selectionAttemptRef.current = {};
    refreshCaseSnapshot();
    refreshSelection();
    refreshEvents();
    refreshLatestExecution();
    refreshSessionDetail();
  }, [sessionId, refreshCaseSnapshot, refreshSelection, refreshEvents, refreshLatestExecution, refreshSessionDetail]);

  useEffect(() => {
    if (!recommendedStrategyId) return;
    if (manualStrategyId) return;
    if (guidedMode || !selectedStrategyId) {
      if (recommendedStrategyId !== selectedStrategyId) {
        setSelectedStrategyId(recommendedStrategyId);
      }
    }
  }, [guidedMode, recommendedStrategyId, selectedStrategyId, manualStrategyId]);

  useEffect(() => {
    if (guidedMode) return;
    if (!selectedStrategyId && strategies.length) {
      setSelectedStrategyId(strategies[0].strategy_id);
    }
  }, [strategies, selectedStrategyId, guidedMode]);

  useEffect(() => {
    fetchStrategyDetail(selectedStrategyId);
    setInputValues({});
  }, [selectedStrategyId, fetchStrategyDetail]);

  useEffect(() => {
    if (!strategyDetail || !strategyDetail.inputs) return;
    const sessionTopic = sessionDetail?.topic_text || '';
    setInputValues((prev) => {
      const next = { ...prev };
      strategyDetail.inputs.forEach((input) => {
        const existing = next[input.key];
        const isEmpty = existing === undefined || existing === null || existing === '';
        if (!isEmpty) return;
        let value = input.default ?? '';
        if (input.bind_to_case_path && caseSnapshot?.payload) {
          const bound = getPathValue(caseSnapshot.payload, input.bind_to_case_path);
          if (bound !== undefined && bound !== null) {
            value = bound;
          }
        }
        if ((value === '' || value === undefined || value === null) && input.key === 'topic' && sessionTopic) {
          value = sessionTopic;
        }
        next[input.key] = normalizeInputValue(value, input.type);
      });
      return next;
    });
  }, [strategyDetail, caseSnapshot, sessionDetail, inputSeedVersion]);

  useEffect(() => {
    const objectives = caseSnapshot?.payload?.objectives || {};
    setObjectiveDraft({
      target: objectives.target ?? '',
      acceptable: objectives.acceptable ?? '',
      walk_away: objectives.walk_away ?? '',
      notes: objectives.notes ?? ''
    });
  }, [caseSnapshot]);

  useEffect(() => {
    if (guidedMode && composerActionType !== ACTION_TYPES[0].id) {
      setComposerActionType(ACTION_TYPES[0].id);
    }
  }, [guidedMode, composerActionType]);

  const handleInputChange = useCallback((key, value) => {
    setInputValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const reseedInputsFromSnapshot = useCallback((resetExisting) => {
    if (resetExisting) {
      setInputValues({});
    }
    setInputSeedVersion((prev) => prev + 1);
  }, []);

  const handleObjectiveChange = useCallback((key, value) => {
    setObjectiveDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleComposerFieldChange = useCallback((actionId, field, value) => {
    setComposerFields((prev) => ({
      ...prev,
      [actionId]: {
        ...(prev[actionId] || {}),
        [field]: value
      }
    }));
  }, []);

  const handleRunSelection = useCallback(async () => {
    if (!sessionId) return;
    setLoading((prev) => ({ ...prev, selection: true }));
    setError('');
    try {
      const data = await apiPost(`/sessions/${sessionId}/strategy/selection`, userId, {});
      setSelection(data);
      setNotice('Strategy selection updated.');
      if (guidedMode) {
        const nextId =
          data?.selected_strategy_id ||
          data?.selection_payload?.response?.ranked_strategies?.[0]?.strategy_id ||
          '';
        setManualStrategyId('');
        if (nextId && nextId !== selectedStrategyId) {
          setSelectedStrategyId(nextId);
        }
        reseedInputsFromSnapshot(true);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading((prev) => ({ ...prev, selection: false }));
    }
  }, [sessionId, userId, guidedMode, selectedStrategyId, reseedInputsFromSnapshot]);

  useEffect(() => {
    if (!guidedMode || !sessionId) return;
    if (loading.selection) return;
    if (selection) return;
    if (selectionAttemptRef.current[sessionId]) return;
    selectionAttemptRef.current[sessionId] = true;
    handleRunSelection();
  }, [guidedMode, sessionId, selection, loading.selection, handleRunSelection]);

  const handleRunBuild = useCallback(async () => {
    if (!sessionId) {
      setError('Select a session first.');
      return;
    }
    if (!selectedStrategyId) {
      setError('Select a strategy first.');
      return;
    }
    const { payload, missing } = buildInputsPayload(strategyDetail?.inputs || [], inputValues);
    if (missing.length) {
      setError(`Missing required inputs: ${missing.join(', ')}`);
      return;
    }
    setLoading((prev) => ({ ...prev, execution: true }));
    setError('');
    try {
      const data = await apiPost(`/sessions/${sessionId}/strategy/execute`, userId, {
        strategy_id: selectedStrategyId,
        inputs: payload
      });
      setExecution(data);
      setNotice('Strategy execution completed.');
      await refreshEvents();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading((prev) => ({ ...prev, execution: false }));
    }
  }, [sessionId, selectedStrategyId, strategyDetail, inputValues, userId, refreshEvents]);

  const handleSaveObjectives = useCallback(async () => {
    if (!sessionId) {
      setError('Select a session first.');
      return;
    }
    const cleanRequired = (value) => {
      const text = String(value ?? '').trim();
      return text ? text : null;
    };
    const notes = String(objectiveDraft?.notes ?? '').trim();
    const patches = [
      { op: 'replace', path: '/objectives/target', value: cleanRequired(objectiveDraft?.target) },
      { op: 'replace', path: '/objectives/acceptable', value: cleanRequired(objectiveDraft?.acceptable) },
      { op: 'replace', path: '/objectives/walk_away', value: cleanRequired(objectiveDraft?.walk_away) },
      { op: 'replace', path: '/objectives/notes', value: notes }
    ];
    setObjectiveSaving(true);
    setError('');
    try {
      const data = await apiPatch(`/sessions/${sessionId}/case-snapshot`, userId, { patches });
      setCaseSnapshot(data);
      setNotice('Objectives saved.');
    } catch (err) {
      setError(err.message);
    } finally {
      setObjectiveSaving(false);
    }
  }, [sessionId, userId, objectiveDraft]);

  const streamRoleplayMessage = useCallback(async (content) => {
    const url = new URL(`/sessions/${sessionId}/messages`, apiBase());
    const resp = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': String(userId)
      },
      body: JSON.stringify({
        content,
        channel: 'roleplay',
        enable_web_grounding: true,
        web_grounding_trigger: 'auto'
      })
    });
    if (!resp.ok || !resp.body) {
      const text = await resp.text();
      throw new Error(text || `Request failed: ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    let collected = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line) {
          currentEvent = '';
          continue;
        }
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim();
          continue;
        }
        if (line.startsWith('data:')) {
          const data = line.slice(5).trim();
          let payload = data;
          try {
            payload = JSON.parse(data);
          } catch {
            // ignore
          }
          if (currentEvent === 'token') {
            const token = typeof payload === 'string' ? payload : '';
            collected += token;
            setStreamingText((prev) => prev + token);
          }
          if (currentEvent === 'done') {
            if (typeof payload === 'object' && payload?.counterparty_message && !collected) {
              collected = payload.counterparty_message;
              setStreamingText(payload.counterparty_message);
            }
          }
          if (currentEvent === 'error') {
            const detail = typeof payload === 'object' ? payload.detail : payload;
            setError(detail || 'Streaming error');
          }
        }
      }
    }
  }, [sessionId, userId]);

  const handleSendAction = useCallback(async () => {
    if (!sessionId) {
      setError('Select a session first.');
      return;
    }
    const composed = composeActionMessage(composerActionType, composerFields);
    if (!composed) {
      setError('Fill in the action fields before sending.');
      return;
    }
    setSending(true);
    setStreamingText('');
    setPendingMessage(composed);
    setError('');
    try {
      await streamRoleplayMessage(composed);
      await refreshSessionDetail();
      await refreshCaseSnapshot();
      await refreshEvents();
      setNotice('Roleplay response received.');
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }, [
    sessionId,
    composerActionType,
    composerFields,
    refreshSessionDetail,
    refreshCaseSnapshot,
    refreshEvents,
    streamRoleplayMessage
  ]);

  const categories = useMemo(() => {
    const counts = strategies.reduce((acc, strategy) => {
      const category = strategy.category || 'OTHER';
      acc[category] = (acc[category] || 0) + 1;
      return acc;
    }, {});
    return [
      { id: 'ALL', label: 'All', count: strategies.length },
      ...Object.keys(counts).sort().map((key) => ({
        id: key,
        label: key.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
        count: counts[key]
      }))
    ];
  }, [strategies]);

  const filteredStrategies = useMemo(() => {
    if (activeCategory === 'ALL') return strategies;
    return strategies.filter((strategy) => (strategy.category || 'OTHER') === activeCategory);
  }, [strategies, activeCategory]);

  const detailStrategy = strategyDetail || EMPTY_STRATEGY;

  return (
    <div className="runtime-shell">
      <aside className="runtime-sidebar">
        <div className="runtime-brand">
          <div className="runtime-brand-title">Strategy Runtime</div>
          <div className="runtime-brand-subtitle">Live backend data</div>
        </div>
        <SessionPanel
          userId={userId}
          onUserIdChange={setUserId}
          sessions={sessions}
          sessionId={sessionId}
          onSelectSession={setSessionId}
          onRefreshSessions={refreshSessions}
          selection={selection}
          onRunSelection={handleRunSelection}
          selectionLoading={loading.selection}
          guidedMode={guidedMode}
          onSelectStrategy={handleSelectStrategy}
        />
        <div className="runtime-panel">
          <div className="runtime-panel-title">Mode</div>
          <div className="runtime-mode-toggle">
            <button
              className={`runtime-chip-button ${guidedMode ? 'active' : ''}`}
              onClick={() => setGuidedMode(true)}
            >
              Guided
            </button>
            <button
              className={`runtime-chip-button ${!guidedMode ? 'active' : ''}`}
              onClick={() => setGuidedMode(false)}
            >
              Advanced
            </button>
          </div>
          <div className="runtime-input-help">
            Guided mode auto-selects a strategy and pre-fills inputs from the CaseSnapshot.
          </div>
        </div>
        <div className="runtime-nav">
          {guidedMode ? (
            <button
              className={`runtime-nav-item ${activeScreen === 'guided' ? 'active' : ''}`}
              onClick={() => handleSetActiveScreen('guided')}
            >
              Guided flow
            </button>
          ) : (
            [
              { id: 'library', label: 'Strategy library' },
              { id: 'canvas', label: 'Strategy canvas' },
              { id: 'arena', label: 'Roleplay arena' },
              { id: 'vault', label: 'Criteria vault' },
              { id: 'stakeholders', label: 'Stakeholder board' }
            ].map((item) => (
              <button
                key={item.id}
                className={`runtime-nav-item ${activeScreen === item.id ? 'active' : ''}`}
                onClick={() => handleSetActiveScreen(item.id)}
              >
                {item.label}
              </button>
            ))
          )}
        </div>
        <div className="runtime-panel runtime-case-card">
          <div className="runtime-panel-title">CaseSnapshot</div>
          <div className="runtime-case-row">
            <span>Case ID</span>
            <span>{caseSnapshot?.payload?.case_id || '--'}</span>
          </div>
          <div className="runtime-case-row">
            <span>Domain</span>
            <span>{caseSnapshot?.payload?.domain || '--'}</span>
          </div>
          <div className="runtime-case-row">
            <span>Channel</span>
            <span>{caseSnapshot?.payload?.channel || '--'}</span>
          </div>
          <div className="runtime-case-row">
            <span>Stage</span>
            <span>{caseSnapshot?.payload?.stage || '--'}</span>
          </div>
          <div className="runtime-case-row">
            <span>Updated</span>
            <span>{formatDateTime(caseSnapshot?.updated_at)}</span>
          </div>
        </div>
        <div className="runtime-panel">
          <div className="runtime-panel-title">View switch</div>
          <div className="view-toggle">
            <button
              className={`view-toggle-button ${currentView === 'canvas' ? 'active' : ''}`}
              onClick={() => onSwitchView('canvas')}
            >
              Canvas view
            </button>
            <button
              className={`view-toggle-button ${currentView === 'runtime' ? 'active' : ''}`}
              onClick={() => onSwitchView('runtime')}
            >
              Strategy runtime
            </button>
          </div>
        </div>
      </aside>
      <main className="runtime-main">
        <header className="runtime-topbar">
          <div>
            <div className="runtime-title">Strategy runtime</div>
            <div className="runtime-subtitle">
              Execute real strategies against the live CaseSnapshot.
            </div>
          </div>
          <div className="runtime-top-actions">
            <span className="runtime-pill">BUILD mode</span>
            <span className="runtime-pill subtle">{guidedMode ? 'Guided mode' : 'Advanced mode'}</span>
            {selection?.strategy_pack_id && (
              <span className="runtime-pill subtle">Pack {selection.strategy_pack_id}</span>
            )}
            <button className="runtime-secondary" onClick={() => setShowDecisionLog(true)}>
              Decision log
            </button>
          </div>
        </header>
        <RuntimeNotice message={notice} onDismiss={() => setNotice('')} />
        <RuntimeNotice message={error} onDismiss={() => setError('')} tone="error" />
        {activeScreen === 'guided' && (
          <GuidedFlowScreen
            sessionId={sessionId}
            selection={selection}
            selectionLoading={loading.selection}
            strategy={detailStrategy}
            caseSnapshot={caseSnapshot}
            sessionDetail={sessionDetail}
            manualStrategyId={manualStrategyId}
            objectiveDraft={objectiveDraft}
            onObjectiveChange={handleObjectiveChange}
            onSaveObjectives={handleSaveObjectives}
            objectiveSaving={objectiveSaving}
            inputValues={inputValues}
            onInputChange={handleInputChange}
            onRunSelection={handleRunSelection}
            onRunBuild={handleRunBuild}
            execution={execution}
            running={loading.execution}
            onOpenDecisionLog={() => setShowDecisionLog(true)}
            onSwitchToAdvanced={() => setGuidedMode(false)}
            actionType={composerActionType}
            fieldValues={composerFields}
            onFieldChange={handleComposerFieldChange}
            onSendAction={handleSendAction}
            sending={sending}
            streamingText={streamingText}
            pendingMessage={pendingMessage}
          />
        )}
        {activeScreen === 'library' && (
          <StrategyLibraryScreen
            categories={categories}
            strategies={filteredStrategies}
            activeCategory={activeCategory}
            onSelectCategory={setActiveCategory}
            selectedStrategyId={selectedStrategyId}
            onSelectStrategy={handleSelectStrategy}
            detailStrategy={detailStrategy}
            caseSnapshot={caseSnapshot}
          />
        )}
        {activeScreen === 'canvas' && (
          <StrategyCanvasScreen
            strategy={detailStrategy}
            caseSnapshot={caseSnapshot}
            inputValues={inputValues}
            onInputChange={handleInputChange}
            onRunBuild={handleRunBuild}
            execution={execution}
            running={loading.execution}
            onOpenDecisionLog={() => setShowDecisionLog(true)}
          />
        )}
        {activeScreen === 'arena' && (
          <RoleplayArenaScreen
            caseSnapshot={caseSnapshot}
            sessionDetail={sessionDetail}
            actionType={composerActionType}
            onActionTypeChange={setComposerActionType}
            fieldValues={composerFields}
            onFieldChange={handleComposerFieldChange}
            onSendAction={handleSendAction}
            sending={sending}
            streamingText={streamingText}
            pendingMessage={pendingMessage}
          />
        )}
        {activeScreen === 'vault' && <CriteriaVaultScreen caseSnapshot={caseSnapshot} />}
        {activeScreen === 'stakeholders' && <StakeholderBoardScreen caseSnapshot={caseSnapshot} />}
        {showDecisionLog && <DecisionLogModal events={events} onClose={() => setShowDecisionLog(false)} />}
      </main>
    </div>
  );
}
