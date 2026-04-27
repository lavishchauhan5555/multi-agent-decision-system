// src/store/useRunStore.js
import { create } from 'zustand'
import { startRun, sseUrl } from '../api/client'

const AGENT_NODES = [
  'cache_check_node',
  'research_node',
  'finance_node',
  'competitor_node',
  'critic_node',
  'heartbeat_node',
  'ceo_node',
  'meta_eval_node',
]

const AGENT_LABELS = {
  cache_check_node: 'Cache',
  research_node:    'Research',
  finance_node:     'Finance',
  competitor_node:  'Competitor',
  critic_node:      'Critic',
  heartbeat_node:   'Heartbeat',
  ceo_node:         'CEO',
  meta_eval_node:   'Meta-Eval',
}

// ── Maps SSE node names → the one field we want to show ──────────────────────
// Handles both "cache_check_node" and "cache_check" (backend may send either)
const CONTENT_KEY_MAP = {
  // with _node suffix
  cache_check_node: d => d?.cached_result ?? (d?.cache_score != null ? `Cache score: ${d.cache_score}` : null),
  fanout_node:      d => d?.query ?? null,
  research_node:    d => d?.research_output ?? null,
  finance_node:     d => d?.finance_output ?? null,
  competitor_node:  d => d?.competitor_output ?? null,
  critic_node:      d => Array.isArray(d?.critiques) ? d.critiques.join('\n\n') : d?.critiques ?? null,
  heartbeat_node:   d => d?.heartbeat_action ?? null,
  ceo_node:         d => d?.final_decision ?? null,
  meta_eval_node:   d => d?.reasoning_summary ?? null,

  // without _node suffix (backend sends short names)
  cache_check: d => d?.cached_result ?? (d?.cache_score != null ? `Cache score: ${d.cache_score}` : null),
  fanout:      d => d?.query ?? null,
  research:    d => d?.research_output ?? null,
  finance:     d => d?.finance_output ?? null,
  competitor:  d => d?.competitor_output ?? null,
  critic:      d => Array.isArray(d?.critiques) ? d.critiques.join('\n\n') : d?.critiques ?? null,
  heartbeat:   d => d?.heartbeat_action ?? null,
  ceo:         d => d?.final_decision ?? null,
  meta_eval:   d => d?.reasoning_summary ?? null,
}

// Normalise short node name → full _node name for AGENT_NODES lookup
const NORMALISE_NODE = {
  cache_check: 'cache_check_node',
  fanout:      null,               // fanout has no agent card
  research:    'research_node',
  finance:     'finance_node',
  competitor:  'competitor_node',
  critic:      'critic_node',
  heartbeat:   'heartbeat_node',
  ceo:         'ceo_node',
  meta_eval:   'meta_eval_node',
}

function toAgentKey(node) {
  if (AGENT_NODES.includes(node)) return node
  return NORMALISE_NODE[node] ?? null
}

function extractContent(node, data) {
  if (data == null) return '[no data]'

  const extractor = CONTENT_KEY_MAP[node]
  let content = extractor ? extractor(data) : null

  // Fallbacks if extractor returned nothing useful
  if (content == null) {
    content = data?.output ?? data?.result ?? data?.message ?? data?.error ?? null
  }

  // fanout sends the whole state — just show the query
  if (content == null && data?.query) {
    content = `Query: ${data.query}`
  }

  // Last resort: stringify
  if (content == null) {
    content = JSON.stringify(data, null, 2)
  }

  // Normalise to string
  if (Array.isArray(content))      content = content.join('\n\n')
  if (typeof content !== 'string') content = JSON.stringify(content, null, 2)

  return content
}

function initialAgentState() {
  return Object.fromEntries(
    AGENT_NODES.map(n => [n, { status: 'idle', round: 0, output: null, ts: null }])
  )
}

// ─────────────────────────────────────────────────────────────────────────────

const useRunStore = create((set, get) => ({
  // ── Run metadata ──────────────────────────────────────────────────────────
  sessionId:    null,
  runStatus:    'idle',   // idle | starting | running | done | error
  query:        '',
  errorMsg:     null,

  // ── Live state ────────────────────────────────────────────────────────────
  agents:          initialAgentState(),
  transcript:      [],
  confidenceScore: 0,
  bestScore:       0,
  currentRound:    0,
  finalDecision:   null,
  heartbeatAction: 'refine',

  // ── SSE handle ────────────────────────────────────────────────────────────
  _sse: null,

  // ── Actions ───────────────────────────────────────────────────────────────

  setQuery: (q) => set({ query: q }),

  launch: async ({ query, maxRounds = 3, threshold = 0.85 }) => {
    const { _sse } = get()
    if (_sse) _sse.close()

    set({
      runStatus:       'starting',
      query,
      agents:          initialAgentState(),
      transcript:      [],
      confidenceScore: 0,
      bestScore:       0,
      currentRound:    0,
      finalDecision:   null,
      heartbeatAction: 'refine',
      errorMsg:        null,
      sessionId:       null,
    })

    try {
      const { sessionId, streamUrl } = await startRun({
        query,
        max_rounds: maxRounds,
        threshold,
      })
      set({ sessionId, runStatus: 'running' })
      get()._openStream(streamUrl)
    } catch (err) {
      set({ runStatus: 'error', errorMsg: err.message })
    }
  },

  _openStream: (streamOrSession) => {
    const url = streamOrSession.startsWith('/api/')
      ? `${import.meta.env.VITE_API_URL ?? 'https://multi-agent-decision-system.onrender.com'}${streamOrSession}`
      : sseUrl(streamOrSession)

    const sse = new EventSource(url)

    sse.onmessage = (e) => {
      let event
      try { event = JSON.parse(e.data) } catch { return }
      get()._handleEvent(event)
    }

    sse.onerror = () => {
      if (get().runStatus === 'running') {
        set({ runStatus: 'error', errorMsg: 'Stream connection lost' })
      }
      sse.close()
    }

    set({ _sse: sse })
  },

  _handleEvent: (event) => {
    // Guard: event must be a plain object
    if (!event || typeof event !== 'object') return

    const { node, round, data, timestamp } = event

    // ── Terminal events ───────────────────────────────────────────────────
    if (node === '__done__') {
      get()._sse?.close()
      set({ runStatus: 'done', _sse: null })
      return
    }

    if (node === '__error__') {
      get()._sse?.close()
      const errMsg = data?.error ?? (typeof data === 'string' ? data : 'Unknown error')
      set({ runStatus: 'error', errorMsg: errMsg, _sse: null })
      return
    }

    // ── Extract clean content string ──────────────────────────────────────
    const content = extractContent(node, data)

    // ── Append to transcript ──────────────────────────────────────────────
    set(s => ({
      transcript:   [...s.transcript, { node, round: round ?? 0, timestamp, content }],
      currentRound: Math.max(s.currentRound, round ?? 0),
    }))

    // ── Update agent card ─────────────────────────────────────────────────
    const agentKey = toAgentKey(node)
    if (agentKey) {
      set(s => ({
        agents: {
          ...s.agents,
          [agentKey]: { status: 'done', round: round ?? 0, output: content, ts: timestamp },
        },
      }))
    }

    // ── Node-specific scalar state ────────────────────────────────────────
    if (data?.confidence_score != null) {
      set(s => ({
        confidenceScore: data.confidence_score,
        bestScore:       Math.max(s.bestScore, data.confidence_score),
      }))
    }

    if (data?.best_score != null) {
      set(s => ({ bestScore: Math.max(s.bestScore, data.best_score) }))
    }

    if (data?.heartbeat_action) {
      set({ heartbeatAction: data.heartbeat_action })
    }

    if (data?.final_decision) {
      set({ finalDecision: data.final_decision })
    }

    // ── Mark next agent card as running (heuristic) ───────────────────────
    const idx = agentKey ? AGENT_NODES.indexOf(agentKey) : -1
    if (idx !== -1 && idx + 1 < AGENT_NODES.length) {
      const nextNode = AGENT_NODES[idx + 1]
      set(s => {
        const next = s.agents[nextNode]
        if (next?.status === 'idle') {
          return { agents: { ...s.agents, [nextNode]: { ...next, status: 'running' } } }
        }
        return {}
      })
    }
  },

  reset: () => {
    get()._sse?.close()
    set({
      sessionId:       null,
      runStatus:       'idle',
      query:           '',
      errorMsg:        null,
      agents:          initialAgentState(),
      transcript:      [],
      confidenceScore: 0,
      bestScore:       0,
      currentRound:    0,
      finalDecision:   null,
      heartbeatAction: 'refine',
      _sse:            null,
    })
  },
}))

export { AGENT_NODES, AGENT_LABELS }
export default useRunStore