// src/api/client.js
//
// Architecture:
//   React :5173  →  Node.js :3001  →  FastAPI :8000  →  LangGraph agents
//
// The frontend NEVER talks to FastAPI directly.
// Every request goes to Node.js, which proxies/relays to FastAPI.
//
// Set in your frontend .env:
//   VITE_API_URL=http://localhost:3001

import axios from 'axios'

const api = axios.create({
  baseURL:         import.meta.env.VITE_API_URL ?? 'https://multi-agent-decision-system.onrender.com',
  timeout:         15_000,
  headers:         { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// ── Dev error logger ──────────────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (import.meta.env.DEV) {
      console.error(
        `[api] ${err.config?.method?.toUpperCase()} ${err.config?.url}`,
        err.response?.status,
        err.response?.data,
      )
    }
    return Promise.reject(err)
  },
)


// ─────────────────────────────────────────────────────────────────────────────
// Run endpoints
//   React → Node.js /api/query/* → FastAPI /run | /stream | /status
// ─────────────────────────────────────────────────────────────────────────────

/**
 * POST /api/query
 * Start a new agent run. Node.js forwards this to FastAPI POST /run.
 * @param {{ query: string, max_rounds?: number, threshold?: number }} payload
 * @returns {{ session_id, status, stream_url }}
 */
export async function startRun(payload) {
  const { data } = await api.post('/api/query', payload)
  return data
}

/**
 * GET /api/query/status/:sessionId
 * Node.js forwards to FastAPI GET /status/:sessionId.
 * @returns {{ session_id, active, status, queue_size }}
 */
export async function getStatus(sessionId) {
  const { data } = await api.get(`/api/query/status/${sessionId}`)
  return data
}

/**
 * GET /api/query/history
 * Run history stored in MongoDB — Node.js serves this directly, no FastAPI call.
 * @returns {Array<{ session_id, query, status, created_at }>}
 */
export async function getHistory() {
  const { data } = await api.get('/api/query/history')
  return data
}


// ─────────────────────────────────────────────────────────────────────────────
// SSE stream
//   React EventSource → Node.js /api/query/stream/:id → FastAPI /stream/:id
//
//  Node.js pipes the FastAPI SSE byte-for-byte to the browser,
//  so the React store receives the same event format as before.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns the SSE URL the browser EventSource should connect to.
 * This is Node.js, NOT FastAPI.
 */
export function sseUrl(sessionId) {
  const base = import.meta.env.VITE_API_URL ?? 'https://multi-agent-decision-system.onrender.com'
  return `${base}/api/query/stream/${sessionId}`
}


// ─────────────────────────────────────────────────────────────────────────────
// Knowledge endpoints
//   React → Node.js /api/knowledge/* → FastAPI /knowledge/*
// ─────────────────────────────────────────────────────────────────────────────

/** GET /api/knowledge/notes — CORAL memory notes */
export async function getNotes(params = {}) {
  const { data } = await api.get('/api/knowledge/notes', { params })
  return data
}

/** GET /api/knowledge/skills — CORAL reusable skills */
export async function getSkills() {
  const { data } = await api.get('/api/knowledge/skills')
  return data
}

/** GET /api/knowledge/leaderboard — top-scoring past attempts */
export async function getLeaderboard(topK = 5) {
  const { data } = await api.get('/api/knowledge/leaderboard', { params: { top_k: topK } })
  return data
}


// ─────────────────────────────────────────────────────────────────────────────
// Session endpoints
//   React → Node.js /api/session/* (MongoDB only — FastAPI not involved)
// ─────────────────────────────────────────────────────────────────────────────

/** GET /api/session/:id */
export async function getSession(sessionId) {
  const { data } = await api.get(`/api/session/${sessionId}`)
  return data
}

/** PATCH /api/session/:id */
export async function updateSession(sessionId, patch) {
  const { data } = await api.patch(`/api/session/${sessionId}`, patch)
  return data
}

/** DELETE /api/session/:id */
export async function deleteSession(sessionId) {
  const { data } = await api.delete(`/api/session/${sessionId}`)
  return data
}


// ─────────────────────────────────────────────────────────────────────────────
// Health
// ─────────────────────────────────────────────────────────────────────────────

/** GET /health — Node.js health (also reports FastAPI target status) */
export async function healthNode() {
  const { data } = await api.get('/health')
  return data
}

export default api