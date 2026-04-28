// routes/query.js
import { Router }           from 'express'
import mongoose             from 'mongoose'
import { Session }          from '../models/auth.js'
import { optionalAuth }     from '../middleware/auth.js'
import { getIO }            from '../socket/io.js'
import { runAgentPipeline } from '../agents/pipeline.js'

const router = Router()

// Active SSE clients map: sessionId (string) → res
const sseClients = new Map()

// ── POST /api/query ────────────────────────────────────────────────────────
router.post('/', optionalAuth, async (req, res) => {
  try {
    // Accept both max_rounds (snake_case) and maxRounds (camelCase) from body
    const { query, max_rounds, maxRounds, threshold = 0.85 } = req.body
    const rounds = Number(max_rounds ?? maxRounds ?? 3)

    if (!query?.trim()) {
      return res.status(400).json({ error: 'query is required' })
    }

    // Pre-generate ObjectId so sessionId === _id.toString() from birth
    const _id       = new mongoose.Types.ObjectId()
    const sessionId = _id.toString()

    const session = await Session.create({
      _id,
      sessionId,
      userId:    req.user?._id ?? null,
      query:     query.trim(),
      maxRounds: rounds,           // always stored as camelCase to match schema
      threshold: Number(threshold),
      status:    'starting',
    })

    // Respond immediately so the frontend can open EventSource
    res.status(202).json({
      sessionId,
      status:    'starting',
      streamUrl: `/api/query/stream/${sessionId}`,
    })

    // Delay pipeline start so SSE client has time to connect.
    // Without this delay the first emits (state_update, transcript) fire
    // before sseClients.get(sessionId) is populated and are silently dropped.
    setTimeout(() => {
      const io = getIO()
      runAgentPipeline(session, { io, sseClients }).catch(err => {
        console.error('[pipeline] error:', err)
        Session.findByIdAndUpdate(session._id, {
          status:   'error',
          errorMsg: err.message,
        }).exec()
        emitToSession(sessionId, 'error', { message: err.message })
      })
    }, 300)

  } catch (err) {
    console.error('[query/post]', err)
    if (err.code === 11000) {
      return res.status(409).json({
        error:   'Duplicate session key — check your Session schema index',
        details: err.keyValue,
      })
    }
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── GET /api/query/stream/:sessionId ──────────────────────────────────────
router.get('/stream/:sessionId', async (req, res) => {
  const { sessionId } = req.params

  res.setHeader('Content-Type',      'text/event-stream')
  res.setHeader('Cache-Control',     'no-cache')
  res.setHeader('Connection',        'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no')
  res.flushHeaders()

  // Register client FIRST so no pipeline events are missed
  sseClients.set(sessionId, res)

  // Keep-alive — SSE comment lines are never parsed as data frames by EventSource
  const heartbeat = setInterval(() => res.write(': ping\n\n'), 15_000)

  // Send snapshot so frontend can hydrate current state immediately
  try {
    const session = await Session.findById(sessionId).lean()
    _write(res, session
      ? { type: 'snapshot', data: session }
      : { type: 'error',    data: { message: 'Session not found' } }
    )
  } catch {
    _write(res, { type: 'error', data: { message: 'Failed to load session snapshot' } })
  }

  req.on('close', () => {
    clearInterval(heartbeat)
    sseClients.delete(sessionId)
  })
})

// ── GET /api/query/status/:sessionId ──────────────────────────────────────
router.get('/status/:sessionId', async (req, res) => {
  try {
    const session = await Session.findById(req.params.sessionId).lean()
    if (!session) return res.status(404).json({ error: 'Session not found' })
    res.json(session)
  } catch (err) {
    console.error('[query/status]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── GET /api/query/history ─────────────────────────────────────────────────
router.get('/history', optionalAuth, async (req, res) => {
  try {
    const filter   = req.user ? { userId: req.user._id } : {}
    const sessions = await Session.find(filter).sort({ createdAt: -1 }).limit(100).lean()
    res.json(sessions)
  } catch (err) {
    console.error('[query/history]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── Internal: safely write one SSE data frame ─────────────────────────────
function _write(res, payload) {
  try { res.write(`data: ${JSON.stringify(payload)}\n\n`) } catch { /* client gone */ }
}

// ── Helper: broadcast event to SSE client + Socket.IO room ────────────────
export function emitToSession(sessionId, type, data) {
  const sseRes = sseClients.get(sessionId)
  if (sseRes) _write(sseRes, { type, data })

  try {
    getIO().to(sessionId).emit(type, data)
  } catch (err) {
    console.warn('[socket] io not ready:', err.message)
  }
}

export default router