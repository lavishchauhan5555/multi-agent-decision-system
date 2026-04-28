// routes/knowledge.js
import { Router } from 'express'
import { Note, Skill, Leaderboard } from '../models/auth.js'
import { optionalAuth } from '../middleware/auth.js'

const router = Router()

// GET /api/knowledge/notes
router.get('/notes', optionalAuth, async (req, res) => {
  try {
    const filter = req.user ? { /* could scope to user */ } : {}
    const notes = await Note.find(filter).sort({ createdAt: -1 }).limit(200).lean()
    res.json(notes)
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

// GET /api/knowledge/skills
router.get('/skills', optionalAuth, async (req, res) => {
  try {
    const skills = await Skill.find({}).sort({ createdAt: -1 }).lean()
    res.json(skills)
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

// GET /api/knowledge/leaderboard
router.get('/leaderboard', optionalAuth, async (req, res) => {
  try {
    const topK = parseInt(req.query.limit) || 50
    const entries = await Leaderboard.find({})
      .sort({ score: -1 })
      .limit(topK)
      .lean()
    res.json(entries)
  } catch {
    res.status(500).json({ error: 'Internal server error' })
  }
})

export default router