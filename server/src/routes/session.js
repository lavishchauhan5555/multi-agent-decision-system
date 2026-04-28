// routes/session.js
import { Router } from 'express'
import { Session } from '../models/auth.js'
import { optionalAuth } from '../middleware/auth.js'

const router = Router()

// GET /api/session/:id
router.get('/:id', optionalAuth, async (req, res) => {
  try {
    const session = await Session.findById(req.params.id).lean()
    if (!session) return res.status(404).json({ error: 'Session not found' })
    res.json(session)
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

// PATCH /api/session/:id  — update metadata (label, notes, etc.)
router.patch('/:id', optionalAuth, async (req, res) => {
  try {
    const allowed = ['status', 'errorMsg', 'finalDecision', 'confidenceScore', 'currentRound', 'heartbeatAction']
    const update  = {}
    for (const key of allowed) {
      if (req.body[key] !== undefined) update[key] = req.body[key]
    }
    const session = await Session.findByIdAndUpdate(req.params.id, update, { new: true }).lean()
    if (!session) return res.status(404).json({ error: 'Session not found' })
    res.json(session)
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

// DELETE /api/session/:id
router.delete('/:id', optionalAuth, async (req, res) => {
  try {
    const session = await Session.findByIdAndDelete(req.params.id)
    if (!session) return res.status(404).json({ error: 'Session not found' })
    res.json({ ok: true, deleted: req.params.id })
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

export default router