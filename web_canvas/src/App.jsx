import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  useEdgesState,
  useNodesState
} from 'reactflow';
import 'reactflow/dist/style.css';
import { apiBase, apiGet, apiPost, apiPatch, apiDelete } from './api.js';
import { layoutNodes } from './flowLayout.js';

const VARIANT_LABELS = {
  LIKELY: 'Likely',
  RISK: 'Risk',
  BEST: 'Best',
  ALT: 'Alt'
};

function MessageNode({ data }) {
  const isUser = data.kind === 'user';
  const isLoading = data.isLoading;
  const isRoute = data.kind === 'route';
  return (
    <div className={`node-card ${data.kind} ${data.isSelected ? 'selected' : ''} ${data.isActive ? 'active' : ''} ${data.isInactive ? 'inactive' : ''}`}>
      <Handle className="node-handle" type="target" position={Position.Left} />
      <div className="node-tag">{data.label}</div>
      <div className="node-text">{data.text}</div>
      {data.meta && <div className="node-meta">{data.meta}</div>}
      {isUser && (
        <button
          className="node-action"
          onClick={(event) => {
            event.stopPropagation();
            data.onSelect?.(data.messageId);
            data.onGenerateRoute?.(data.messageId);
          }}
          disabled={isLoading || data.isBranchDisabled}
        >
          {data.isBranchDisabled ? 'Complete intake' : isLoading ? 'Branching...' : 'Branch'}
        </button>
      )}
      {isRoute && (
        <>
          <button
            className="node-action"
            onClick={(event) => {
              event.stopPropagation();
              data.onActivateBranch?.(data.threadId);
            }}
            disabled={data.isActive || isLoading}
          >
            {data.isActive ? 'Active path' : isLoading ? 'Switching...' : 'Use this path'}
          </button>
          <div className="node-actions">
            <button
              className="node-action"
              onClick={(event) => {
                event.stopPropagation();
                data.onCopyBranch?.(data.threadId, data.branchLabel, data.text);
              }}
            >
              Copy
            </button>
            <button
              className="node-action"
              onClick={(event) => {
                event.stopPropagation();
                data.onRenameBranch?.(data.threadId, data.branchLabel);
              }}
            >
              Rename
            </button>
            <button
              className="node-action danger"
              onClick={(event) => {
                event.stopPropagation();
                data.onDeleteBranch?.(data.threadId);
              }}
            >
              Delete
            </button>
          </div>
        </>
      )}
      <Handle className="node-handle" type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { message: MessageNode };

function buildGraph(messages, branches, handlers, selectedUserMessageId, loadingMessageId, activatingThreadId, activeThreadId, intakeSubmitted) {
  const nodes = [];
  const edges = [];
  const nodeMap = new Map();
  let lastNodeId = null;

  messages.forEach((msg) => {
    if (msg.role === 'user') {
      const nodeId = `u-${msg.id}`;
      const node = {
        id: nodeId,
        type: 'message',
        data: {
          label: 'User move',
          text: msg.content,
          kind: 'user',
          messageId: msg.id,
          isSelected: Number(msg.id) === Number(selectedUserMessageId),
          isLoading: Number(msg.id) === Number(loadingMessageId),
          isBranchDisabled: !intakeSubmitted,
          onGenerateRoute: handlers?.onGenerateRoute,
          onSelect: handlers?.onSelect
        },
        position: { x: 0, y: 0 }
      };
      nodes.push(node);
      nodeMap.set(nodeId, node);
      if (lastNodeId) {
        edges.push({ id: `e-${lastNodeId}-${nodeId}`, source: lastNodeId, target: nodeId });
      }
      lastNodeId = nodeId;
    }
    if (msg.role === 'counterparty') {
      const nodeId = `c-${msg.id}`;
      const node = {
        id: nodeId,
        type: 'message',
        data: {
          label: 'Counterparty',
          text: msg.content,
          kind: 'counterparty',
          messageId: msg.id
        },
        position: { x: 0, y: 0 }
      };
      nodes.push(node);
      nodeMap.set(nodeId, node);
      if (lastNodeId) {
        edges.push({ id: `e-${lastNodeId}-${nodeId}`, source: lastNodeId, target: nodeId });
      }
      lastNodeId = nodeId;
    }
  });

  branches.forEach((branch) => {
    const parentId = `u-${branch.parent_message_id}`;
    if (!nodeMap.has(parentId)) {
      return;
    }
    const counterId = `brc-${branch.branch_id}`;
    const variantLabel = VARIANT_LABELS[branch.variant] || 'Route';

    const metaParts = [];
    if (branch.branch_label) {
      metaParts.push(branch.branch_label);
    }
    if (branch.action_label) {
      metaParts.push(branch.action_label);
    }
    if (branch.rationale) {
      metaParts.push(branch.rationale);
    }
    nodes.push({
      id: counterId,
      type: 'message',
      data: {
        label: `${variantLabel} route`,
        text: branch.counterparty_response,
        kind: 'route',
        meta: metaParts.join(' · '),
        branchId: branch.branch_id,
        threadId: branch.thread_id,
        branchLabel: branch.branch_label,
        isActive: Boolean(branch.is_active),
        isLoading: Number(branch.thread_id) === Number(activatingThreadId),
        isInactive: activeThreadId && Number(branch.thread_id) !== Number(activeThreadId),
        onActivateBranch: handlers?.onActivateBranch,
        onCopyBranch: handlers?.onCopyBranch,
        onRenameBranch: handlers?.onRenameBranch,
        onDeleteBranch: handlers?.onDeleteBranch
      },
      position: { x: 0, y: 0 }
    });

    edges.push({ id: `e-${parentId}-${counterId}`, source: parentId, target: counterId, type: 'smoothstep' });
  });

  return layoutNodes(nodes, edges, 'TB');
}

function CanvasHeader({ session, onRefresh, onActivateMainline, activeThreadId, rootThreadId }) {
  return (
    <div className="header">
      <div>
        <div className="title">{session?.title || 'Negotiation Canvas'}</div>
        <div className="subtitle">
          {session?.id ? `Session #${session.id}` : 'Select a session to begin.'}
          {session?.topic_text ? ` · ${session.topic_text}` : ''}
        </div>
      </div>
      <div className="header-actions">
        {rootThreadId && activeThreadId && rootThreadId !== activeThreadId && (
          <button className="secondary" onClick={onActivateMainline}>
            Switch to mainline
          </button>
        )}
        <button onClick={onRefresh} className="secondary">Refresh</button>
        <a className="secondary" href={apiBase()} target="_blank" rel="noreferrer">API</a>
      </div>
    </div>
  );
}

export default function App() {
  const params = new URLSearchParams(window.location.search);
  const [userId, setUserId] = useState(params.get('user_id') || '1');
  const [sessionId, setSessionId] = useState(params.get('session_id') || '');
  const [sessions, setSessions] = useState([]);
  const [session, setSession] = useState(null);
  const [branches, setBranches] = useState([]);
  const [snapshot, setSnapshot] = useState(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedUserMessageId, setSelectedUserMessageId] = useState(null);
  const [variant, setVariant] = useState('LIKELY');
  const [loading, setLoading] = useState(false);
  const [loadingMessageId, setLoadingMessageId] = useState(null);
  const [activatingThreadId, setActivatingThreadId] = useState(null);
  const [error, setError] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [sending, setSending] = useState(false);
  const [pendingUserMessage, setPendingUserMessage] = useState(null);
  const [streamingText, setStreamingText] = useState('');
  const [newTopic, setNewTopic] = useState('');
  const [newChannel, setNewChannel] = useState('DM');
  const [newStyle, setNewStyle] = useState('');
  const [creating, setCreating] = useState(false);
  const [intakeAnswers, setIntakeAnswers] = useState({});
  const [submittingIntake, setSubmittingIntake] = useState(false);
  const activeThreadId = session?.active_thread_id;
  const rootThreadId = session?.root_thread_id;

  const refreshSessions = useCallback(async () => {
    try {
      const data = await apiGet('/sessions', userId);
      setSessions(data || []);
    } catch (err) {
      setError(err.message);
    }
  }, [userId]);

  const refreshSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}`, userId);
      setSession(data);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  const refreshSnapshot = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}/case-snapshot`, userId);
      setSnapshot(data);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  const refreshBranches = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet(`/sessions/${sessionId}/routes`, userId);
      setBranches(data || []);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId]);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    refreshSession();
    refreshBranches();
    refreshSnapshot();
  }, [refreshSession, refreshBranches, refreshSnapshot]);

  useEffect(() => {
    setSelectedUserMessageId(null);
    setPendingUserMessage(null);
    setStreamingText('');
  }, [sessionId]);

  useEffect(() => {
    const intake = snapshot?.payload?.intake;
    if (intake?.answers) {
      setIntakeAnswers(intake.answers);
    }
  }, [snapshot]);

  const latestUserMessageId = useMemo(() => {
    if (!session || !session.messages) return null;
    for (let i = session.messages.length - 1; i >= 0; i -= 1) {
      if (session.messages[i].role === 'user') {
        return session.messages[i].id;
      }
    }
    return null;
  }, [session]);

  const activeParentMessageId = selectedUserMessageId || latestUserMessageId;

  const routesForMessage = useCallback((messageId) => {
    if (!messageId) return [];
    return (branches || []).filter((branch) => Number(branch.parent_message_id) === Number(messageId));
  }, [branches]);

  const existingRoutes = useMemo(() => {
    return routesForMessage(activeParentMessageId);
  }, [routesForMessage, activeParentMessageId]);

  const intakeQuestions = useMemo(() => {
    return snapshot?.payload?.intake?.questions || [];
  }, [snapshot]);

  const intakeComplete = useMemo(() => {
    if (!intakeQuestions.length) return true;
    return intakeQuestions.every((question) => {
      const answer = intakeAnswers?.[question];
      return Boolean(answer && String(answer).trim());
    });
  }, [intakeQuestions, intakeAnswers]);

  const intakeSubmitted = useMemo(() => {
    return Boolean(snapshot?.payload?.intake?.summary);
  }, [snapshot]);

  const activateThread = useCallback(async (threadId) => {
    if (!sessionId || !threadId) return;
    setActivatingThreadId(threadId);
    setError('');
    try {
      const data = await apiPost(`/sessions/${sessionId}/threads/${threadId}/activate`, userId, {});
      setSession(data);
      await refreshBranches();
    } catch (err) {
      setError(err.message);
    } finally {
      setActivatingThreadId(null);
    }
  }, [sessionId, userId, refreshBranches]);

  const handleRenameBranch = useCallback(async (threadId, currentLabel) => {
    const nextLabel = window.prompt('Rename branch', currentLabel || '');
    if (nextLabel === null) return;
    setError('');
    try {
      await apiPatch(`/sessions/${sessionId}/threads/${threadId}`, userId, {
        branch_label: nextLabel
      });
      await refreshBranches();
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId, refreshBranches]);

  const handleCopyBranch = useCallback(async (threadId, defaultLabel, defaultResponse) => {
    const nextLabel = window.prompt(
      'Label for copied branch',
      defaultLabel ? `Copy of ${defaultLabel}` : 'Copied branch'
    );
    if (nextLabel === null) return;
    const nextResponse = window.prompt('Edit the copied response', defaultResponse || '');
    if (nextResponse === null) return;
    setError('');
    try {
      const branch = await apiPost(`/sessions/${sessionId}/threads/${threadId}/copy`, userId, {
        branch_label: nextLabel,
        counterparty_response: nextResponse
      });
      await refreshBranches();
      if (branch?.thread_id) {
        await activateThread(branch.thread_id);
      }
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId, refreshBranches, activateThread]);

  const handleDeleteBranch = useCallback(async (threadId) => {
    const confirmed = window.confirm('Delete this branch? This cannot be undone.');
    if (!confirmed) return;
    setError('');
    try {
      await apiDelete(`/sessions/${sessionId}/threads/${threadId}`, userId);
      await refreshBranches();
      await refreshSession();
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, userId, refreshBranches, refreshSession]);

  const onNodeClick = useCallback((_, node) => {
    if (node?.data?.messageId && node?.data?.kind === 'user') {
      setSelectedUserMessageId(node.data.messageId);
    }
    if (node?.data?.kind === 'route' && node?.data?.threadId) {
      activateThread(node.data.threadId);
    }
  }, [activateThread]);

  const generateRouteFor = useCallback(async (messageId) => {
    if (!sessionId || !messageId) return;
    if (!intakeSubmitted) {
      setError('Submit intake questions before branching.');
      return;
    }
    setLoading(true);
    setLoadingMessageId(messageId);
    setError('');
    try {
      const branch = await apiPost(`/sessions/${sessionId}/routes/generate`, userId, {
        variant,
        parent_message_id: messageId,
        existing_routes: routesForMessage(messageId).map((branch) => ({
          counterparty_response: branch.counterparty_response,
          rationale: branch.rationale,
          action_label: branch.action_label
        }))
      });
      setSelectedUserMessageId(messageId);
      await refreshBranches();
      if (branch?.thread_id) {
        await activateThread(branch.thread_id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingMessageId(null);
    }
  }, [sessionId, userId, variant, routesForMessage, refreshBranches, intakeSubmitted]);

  const handlers = useMemo(() => ({
    onGenerateRoute: (messageId) => {
      generateRouteFor(messageId);
    },
    onSelect: (messageId) => setSelectedUserMessageId(messageId),
    onActivateBranch: (threadId) => {
      activateThread(threadId);
    },
    onRenameBranch: (threadId, label) => {
      handleRenameBranch(threadId, label);
    },
    onCopyBranch: (threadId, label, response) => {
      handleCopyBranch(threadId, label, response);
    },
    onDeleteBranch: (threadId) => {
      handleDeleteBranch(threadId);
    }
  }), [generateRouteFor, activateThread, handleRenameBranch, handleCopyBranch, handleDeleteBranch]);

  useEffect(() => {
    if (!session) return;
    const { nodes: layoutedNodes, edges: layoutedEdges } = buildGraph(
      session.messages || [],
      branches || [],
      handlers,
      selectedUserMessageId,
      loadingMessageId,
      activatingThreadId,
      activeThreadId,
      intakeSubmitted
    );
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [session, branches, setNodes, setEdges, handlers, selectedUserMessageId, loadingMessageId, activatingThreadId, activeThreadId, intakeComplete]);

  const generateRoute = async () => {
    if (!sessionId || !activeParentMessageId) return;
    if (!intakeSubmitted) {
      setError('Submit intake questions before branching.');
      return;
    }
    await generateRouteFor(activeParentMessageId);
  };

  const streamMessage = async (content) => {
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
  };

  const sendContent = async (content) => {
    if (!sessionId) return;
    if (!intakeSubmitted) {
      setError('Submit intake questions before roleplay.');
      return;
    }
    const trimmed = (content || '').trim();
    if (!trimmed) return;
    setChatInput('');
    setError('');
    setSending(true);
    setPendingUserMessage(trimmed);
    setStreamingText('');
    try {
      await streamMessage(trimmed);
      await refreshSession();
      await refreshBranches();
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
      setPendingUserMessage(null);
      setStreamingText('');
    }
  };

  const sendMessage = async () => {
    await sendContent(chatInput);
  };

  const chatMessages = useMemo(() => {
    if (!session || !session.messages) return [];
    return session.messages.filter((msg) => msg.role === 'user' || msg.role === 'counterparty');
  }, [session]);

  const showStartRoleplay = useMemo(() => {
    return intakeSubmitted && chatMessages.length === 0;
  }, [intakeSubmitted, chatMessages.length]);

  const submitIntake = useCallback(async () => {
    if (!sessionId || !intakeQuestions.length) return;
    setSubmittingIntake(true);
    setError('');
    const summaryParts = intakeQuestions.map((question) => {
      const answer = intakeAnswers?.[question] || '';
      return `${question} Answer: ${answer}`.trim();
    });
    const summary = summaryParts.join(' | ').slice(0, 1000);
    try {
      await apiPost(`/sessions/${sessionId}/intake`, userId, {
        questions: intakeQuestions,
        answers: intakeAnswers,
        summary
      });
      await refreshSnapshot();
      await refreshSession();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmittingIntake(false);
    }
  }, [sessionId, intakeQuestions, intakeAnswers, userId, refreshSnapshot, refreshSession]);

  const createSession = useCallback(async () => {
    const topic = newTopic.trim();
    if (!topic) return;
    setCreating(true);
    setError('');
    try {
      const payload = {
        topic_text: topic,
        channel: newChannel,
        counterparty_style: newStyle.trim() ? newStyle.trim() : null
      };
      const resp = await apiPost('/sessions', userId, payload);
      const newSessionId = String(resp?.session_id || '');
      if (newSessionId) {
        setSessionId(newSessionId);
        setNewTopic('');
        await refreshSessions();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }, [newTopic, newChannel, newStyle, userId, refreshSessions]);

  return (
    <div className="app-shell">
      <aside className="side-panel">
        <div className="panel-card">
          <div className="panel-title">User</div>
          <label className="field">
            User ID
            <input
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="1"
            />
          </label>
          <button className="secondary" onClick={refreshSessions}>Reload sessions</button>
        </div>
        <div className="panel-card">
          <div className="panel-title">New session</div>
          <label className="field">
            Topic
            <textarea
              rows={4}
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              placeholder="Describe the negotiation topic..."
            />
          </label>
          <label className="field">
            Channel
            <select value={newChannel} onChange={(e) => setNewChannel(e.target.value)}>
              <option value="DM">DM</option>
              <option value="EMAIL">Email</option>
              <option value="IN_PERSON_NOTES">In-person notes</option>
            </select>
          </label>
          <label className="field">
            Counterparty style
            <input
              type="text"
              value={newStyle}
              onChange={(e) => setNewStyle(e.target.value)}
              placeholder="neutral"
            />
          </label>
          <button className="primary" onClick={createSession} disabled={creating || !newTopic.trim()}>
            {creating ? 'Creating...' : 'Create session'}
          </button>
        </div>
        <div className="panel-card">
          <div className="panel-title">Sessions</div>
          {sessions.length === 0 && <div className="panel-muted">No sessions yet.</div>}
          {sessions.map((item) => (
            <button
              key={item.id}
              className={`session-chip ${sessionId === String(item.id) ? 'active' : ''}`}
              onClick={() => setSessionId(String(item.id))}
            >
              <div>{item.title || 'Session'}</div>
              <small>{item.template_id}</small>
            </button>
          ))}
        </div>
        <div className="panel-card">
          <div className="panel-title">Route controls</div>
          <div className="panel-muted">Generate one route at a time.</div>
          <label className="field">
            Variant
            <select value={variant} onChange={(e) => setVariant(e.target.value)}>
              <option value="LIKELY">Likely</option>
              <option value="RISK">Risk</option>
              <option value="BEST">Best</option>
              <option value="ALT">Alt</option>
            </select>
          </label>
          <div className="panel-muted">
            {activeParentMessageId
              ? `Branching from user message ${activeParentMessageId}`
              : 'No user message selected.'}
          </div>
          <button className="primary" onClick={generateRoute} disabled={loading || !activeParentMessageId || !intakeSubmitted}>
            {existingRoutes.length ? 'Generate another route' : 'Generate route'}
          </button>
          <div className="panel-muted">Existing routes: {existingRoutes.length}</div>
        </div>
        {error && <div className="error">{error}</div>}
      </aside>
      <main className="canvas-area">
        <CanvasHeader
          session={session || {}}
          onRefresh={() => { refreshSession(); refreshBranches(); refreshSnapshot(); }}
          onActivateMainline={() => {
            if (rootThreadId) {
              activateThread(rootThreadId);
            }
          }}
          activeThreadId={activeThreadId}
          rootThreadId={rootThreadId}
        />
        <div className="flow-shell">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background color="#e2d6c7" />
            <MiniMap />
            <Controls />
          </ReactFlow>
        </div>
        {intakeQuestions.length > 0 && !intakeSubmitted && (
          <div className="chat-panel">
            <div className="panel-title">Intake questions</div>
            <div className="panel-muted">
              {intakeComplete ? 'Ready to submit.' : 'Answer these to start roleplay.'}
            </div>
            <div className="intake-list">
              {intakeQuestions.map((question, idx) => (
                <label key={`${question}-${idx}`} className="field">
                  {question}
                  <input
                    type="text"
                    value={intakeAnswers?.[question] || ''}
                    onChange={(e) => {
                      const next = { ...intakeAnswers, [question]: e.target.value };
                      setIntakeAnswers(next);
                    }}
                  />
                </label>
              ))}
            </div>
            <button className="primary" onClick={submitIntake} disabled={submittingIntake || !intakeComplete}>
              {submittingIntake ? 'Submitting...' : 'Submit intake'}
            </button>
          </div>
        )}
        <div className="chat-panel">
          <div className="panel-title">Live roleplay</div>
          {showStartRoleplay && (
            <div className="panel-muted">
              Intake submitted. Start the roleplay when you’re ready.
              <div style={{ marginTop: '8px' }}>
                <button
                  className="secondary"
                  onClick={() => sendContent("Let's begin the roleplay.")}
                  disabled={sending}
                >
                  Start roleplay
                </button>
              </div>
            </div>
          )}
          <div className="chat-thread">
            {chatMessages.map((msg) => (
              <div key={`${msg.role}-${msg.id}`} className={`chat-message ${msg.role}`}>
                {msg.content}
              </div>
            ))}
            {pendingUserMessage && (
              <div className="chat-message user">{pendingUserMessage}</div>
            )}
            {streamingText && (
              <div className="chat-message counterparty">{streamingText}</div>
            )}
          </div>
          <div className="chat-input">
            <input
              type="text"
              value={chatInput}
              placeholder="Send a message..."
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  sendMessage();
                }
              }}
              disabled={!intakeSubmitted}
            />
            <button className="primary" onClick={sendMessage} disabled={sending || !chatInput.trim() || !intakeSubmitted}>
              {sending ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
