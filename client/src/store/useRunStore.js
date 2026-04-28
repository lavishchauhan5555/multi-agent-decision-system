// src/store/useRunStore.js

import { create } from 'zustand'
import { startRun } from '../api/client'

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
  research_node: 'Research',
  finance_node: 'Finance',
  competitor_node: 'Competitor',
  critic_node: 'Critic',
  heartbeat_node: 'Heartbeat',
  ceo_node: 'CEO',
  meta_eval_node: 'Meta-Eval',
}

const CONTENT_KEY_MAP = {
  cache_check_node: d =>
    d?.cached_result ??
    (d?.cache_score != null ? `Cache score: ${d.cache_score}` : null),

  research_node: d => d?.research_output ?? null,
  finance_node: d => d?.finance_output ?? null,
  competitor_node: d => d?.competitor_output ?? null,

  critic_node: d =>
    Array.isArray(d?.critiques)
      ? d.critiques.join('\n\n')
      : d?.critiques ?? null,

  heartbeat_node: d => d?.heartbeat_action ?? null,
  ceo_node: d => d?.final_decision ?? null,
  meta_eval_node: d => d?.reasoning_summary ?? null,

  cache_check: d =>
    d?.cached_result ??
    (d?.cache_score != null ? `Cache score: ${d.cache_score}` : null),

  research: d => d?.research_output ?? null,
  finance: d => d?.finance_output ?? null,
  competitor: d => d?.competitor_output ?? null,

  critic: d =>
    Array.isArray(d?.critiques)
      ? d.critiques.join('\n\n')
      : d?.critiques ?? null,

  heartbeat: d => d?.heartbeat_action ?? null,
  ceo: d => d?.final_decision ?? null,
  meta_eval: d => d?.reasoning_summary ?? null,

  transcript: d => d?.text ?? null,
  snapshot: d => d?.query ?? null,
}

const NORMALISE_NODE = {
  cache_check: 'cache_check_node',
  research: 'research_node',
  finance: 'finance_node',
  competitor: 'competitor_node',
  critic: 'critic_node',
  heartbeat: 'heartbeat_node',
  ceo: 'ceo_node',
  meta_eval: 'meta_eval_node',

  cache_check_node: 'cache_check_node',
  research_node: 'research_node',
  finance_node: 'finance_node',
  competitor_node: 'competitor_node',
  critic_node: 'critic_node',
  heartbeat_node: 'heartbeat_node',
  ceo_node: 'ceo_node',
  meta_eval_node: 'meta_eval_node',
}

function toAgentKey(node) {
  if (!node) return null
  return NORMALISE_NODE[node] ?? null
}

function safeString(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value, null, 2)
}

function extractContent(node, data) {
  if (data == null) return '[no data]'

  const extractor = CONTENT_KEY_MAP[node]
  let content = extractor ? extractor(data) : null

  if (content == null) {
    content =
      data?.output ??
      data?.result ??
      data?.message ??
      data?.error ??
      data?.summary ??
      null
  }

  if (content == null && data?.query) {
    content = `Query: ${data.query}`
  }

  if (content == null) {
    content = data
  }

  if (Array.isArray(content)) {
    content = content.join('\n\n')
  }

  return safeString(content)
}

function initialAgentState() {
  return Object.fromEntries(
    AGENT_NODES.map(n => [
      n,
      {
        status: 'idle',
        round: 0,
        output: null,
        ts: null,
      },
    ])
  )
}

function buildSseUrl(streamUrlOrSessionId) {
  const BASE =
    import.meta.env.VITE_API_URL ??
    'https://multi-agent-decision-system.onrender.com'

  if (!streamUrlOrSessionId || typeof streamUrlOrSessionId !== 'string') {
    return null
  }

  if (streamUrlOrSessionId.startsWith('http')) {
    return streamUrlOrSessionId
  }

  if (streamUrlOrSessionId.startsWith('/')) {
    return `${BASE}${streamUrlOrSessionId}`
  }

  return `${BASE}/api/query/stream/${streamUrlOrSessionId}`
}

const useRunStore = create((set, get) => ({
  sessionId: null,
  runStatus: 'idle',
  query: '',
  errorMsg: null,

  agents: initialAgentState(),
  transcript: [],
  confidenceScore: 0,
  bestScore: 0,
  currentRound: 0,
  finalDecision: null,
  heartbeatAction: 'refine',

  _sse: null,

  setQuery: q => set({ query: q }),

  launch: async ({ query, maxRounds = 3, threshold = 0.85 }) => {
    get()._sse?.close()

    set({
      runStatus: 'starting',
      query,
      agents: initialAgentState(),
      transcript: [],
      confidenceScore: 0,
      bestScore: 0,
      currentRound: 0,
      finalDecision: null,
      heartbeatAction: 'refine',
      errorMsg: null,
      sessionId: null,
    })

    try {
      const result = await startRun({
        query,
        max_rounds: maxRounds,
        maxRounds,
        threshold,
      })

      const sessionId = result.sessionId
      const streamUrl = result.streamUrl ?? `/api/query/stream/${sessionId}`

      if (!sessionId) {
        throw new Error('No sessionId returned from server')
      }

      set({
        sessionId,
        runStatus: 'running',
      })

      get()._openStream(streamUrl)
    } catch (err) {
      set({
        runStatus: 'error',
        errorMsg: err.message,
      })
    }
  },

  _openStream: streamUrl => {
    const url = buildSseUrl(streamUrl)

    if (!url) {
      console.error('[SSE] invalid stream url:', streamUrl)
      set({
        runStatus: 'error',
        errorMsg: 'Invalid stream URL',
      })
      return
    }

    console.log('[SSE] connecting to', url)

    const sse = new EventSource(url, {
      withCredentials: false,
    })

    sse.onopen = () => {
      console.log('[SSE] connected')
    }

    sse.onmessage = e => {
      if (!e.data || !e.data.trim() || e.data.trim() === '{}') return

      let event
      try {
        event = JSON.parse(e.data)
      } catch {
        return
      }

      if (!event || typeof event !== 'object') return
      if (!Object.keys(event).length) return

      get()._handleEvent(event)
    }

    sse.onerror = err => {
      console.error('[SSE] error', err)

      if (get().runStatus === 'running') {
        set({
          runStatus: 'error',
          errorMsg: 'Stream connection lost',
        })
      }

      sse.close()
      set({ _sse: null })
    }

    set({ _sse: sse })
  },

  _handleEvent: event => {
    if (!event || typeof event !== 'object') return

    // Node SSE shape: { type, data }
    if ('type' in event && !('node' in event)) {
      get()._handleNodeEvent(event)
      return
    }

    // FastAPI direct shape: { node, round, timestamp, data }
    get()._handleGraphEvent(event)
  },

  _handleGraphEvent: event => {
    const { node, round, timestamp, data } = event

    if (!node) return

    if (node === '__done__') {
      get()._sse?.close()
      set({
        runStatus: 'done',
        _sse: null,
      })
      return
    }

    if (node === '__error__' || node === '__timeout__') {
      get()._sse?.close()
      set({
        runStatus: 'error',
        errorMsg: data?.error ?? 'Unknown graph error',
        _sse: null,
      })
      return
    }

    const content = extractContent(node, data)
    const agentKey = toAgentKey(node)

    set(s => ({
      transcript: [
        ...s.transcript,
        {
          node,
          round: round ?? s.currentRound,
          timestamp,
          content,
        },
      ],
      currentRound: Math.max(s.currentRound, round ?? 0),
    }))

    if (agentKey) {
      set(s => ({
        agents: {
          ...s.agents,
          [agentKey]: {
            status: 'done',
            round: round ?? s.currentRound,
            output: content,
            ts: timestamp,
          },
        },
      }))
    }

    if (data?.confidence_score != null) {
      set(s => ({
        confidenceScore: data.confidence_score,
        bestScore: Math.max(s.bestScore, data.confidence_score),
      }))
    }

    if (data?.best_score != null) {
      set(s => ({
        bestScore: Math.max(s.bestScore, data.best_score),
      }))
    }

    if (data?.heartbeat_action) {
      set({
        heartbeatAction: data.heartbeat_action,
      })
    }

    if (data?.final_decision) {
      set({
        finalDecision: data.final_decision,
      })
    }
  },

  _handleNodeEvent: event => {
    const { type, data } = event

    switch (type) {
      case 'snapshot': {
        if (data?.status) {
          set({
            runStatus: data.status,
            currentRound: data.currentRound ?? 0,
            confidenceScore: data.confidenceScore ?? 0,
            bestScore: data.bestScore ?? 0,
            heartbeatAction: data.heartbeatAction ?? 'refine',
            finalDecision: data.finalDecision ?? null,
          })
        }
        break
      }

      case 'state_update': {
        const patch = {}

        if (data?.status) patch.runStatus = data.status
        if (data?.currentRound != null) patch.currentRound = data.currentRound
        if (data?.confidenceScore != null) patch.confidenceScore = data.confidenceScore
        if (data?.bestScore != null) patch.bestScore = data.bestScore
        if (data?.heartbeatAction) patch.heartbeatAction = data.heartbeatAction
        if (data?.finalDecision) patch.finalDecision = data.finalDecision

        if (Object.keys(patch).length) set(patch)
        break
      }

      case 'graph_event': {
        get()._handleGraphEvent({
          node: data?.node,
          round: data?.round,
          timestamp: data?.timestamp,
          data: data?.data,
        })
        break
      }

      case 'agent_update': {
        const { agentId, status, output } = data ?? {}

        if (!agentId) break

        const agentKey = toAgentKey(agentId)
        if (!agentKey) break

        const content =
          output?.summary ??
          output?.recommendation ??
          safeString(output ?? '')

        set(s => ({
          agents: {
            ...s.agents,
            [agentKey]: {
              status:
                status === 'thinking'
                  ? 'running'
                  : status === 'done'
                    ? 'done'
                    : 'error',
              round: s.currentRound,
              output: safeString(content),
              ts: Date.now(),
            },
          },
        }))

        break
      }

      case 'transcript': {
        const { role, text, round, ts } = data ?? {}

        if (!text) break

        set(s => ({
          transcript: [
            ...s.transcript,
            {
              node: role ?? 'system',
              round: round ?? s.currentRound,
              timestamp: ts,
              content: safeString(text),
            },
          ],
          currentRound: Math.max(s.currentRound, round ?? 0),
        }))

        break
      }

      case 'done': {
        const { finalDecision, confidence } = data ?? {}

        get()._sse?.close()

        set({
          runStatus: 'done',
          _sse: null,
          finalDecision: finalDecision ?? get().finalDecision,
          confidenceScore: confidence ?? get().confidenceScore,
        })

        break
      }

      case 'error': {
        get()._sse?.close()

        set({
          runStatus: 'error',
          errorMsg: data?.message ?? 'Pipeline error',
          _sse: null,
        })

        break
      }

      default:
        break
    }
  },

  reset: () => {
    get()._sse?.close()

    set({
      sessionId: null,
      runStatus: 'idle',
      query: '',
      errorMsg: null,
      agents: initialAgentState(),
      transcript: [],
      confidenceScore: 0,
      bestScore: 0,
      currentRound: 0,
      finalDecision: null,
      heartbeatAction: 'refine',
      _sse: null,
    })
  },
}))

export { AGENT_NODES, AGENT_LABELS }
export default useRunStore