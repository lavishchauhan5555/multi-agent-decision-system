// routes/auth.js
import { Router }      from 'express'
import bcrypt          from 'bcryptjs'
import crypto          from 'crypto'
import rateLimit       from 'express-rate-limit'
import { User, RefreshToken } from '../models/auth.js'
import {
  signAccessToken, signRefreshToken, verifyRefreshToken,
  setRefreshCookie, clearRefreshCookie,
  requireAuth, REFRESH_EXPIRY_MS,
} from '../middleware/auth.js'

const router    = Router()
const hashToken = raw => crypto.createHash('sha256').update(raw).digest('hex')

// ── Rate limiters ─────────────────────────────────────────────────────────
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,   // 15 min window
  max:      10,                // 10 attempts per IP
  message:  { error: 'Too many login attempts — try again in 15 minutes' },
  standardHeaders: true,
  legacyHeaders:   false,
})

const signupLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,   // 1 hour window
  max:      5,                 // 5 signups per IP per hour
  message:  { error: 'Too many accounts created from this IP' },
  standardHeaders: true,
  legacyHeaders:   false,
})

const refreshLimiter = rateLimit({
  windowMs: 60 * 1000,         // 1 min window
  max:      20,                // 20 refresh calls per min per IP (covers silent refresh)
  message:  { error: 'Too many refresh requests' },
  standardHeaders: true,
  legacyHeaders:   false,
})

// ── Issue both tokens ─────────────────────────────────────────────────────
async function issueTokens(res, user, req) {
  const accessToken  = signAccessToken(user._id)
  const refreshToken = signRefreshToken(user._id)

  await RefreshToken.create({
    userId:    user._id,
    tokenHash: hashToken(refreshToken),
    expiresAt: new Date(Date.now() + REFRESH_EXPIRY_MS),
    userAgent: req.headers['user-agent'],
    ip:        req.ip,
  })

  setRefreshCookie(res, refreshToken)
   // ✅ ADD THIS DEBUG HERE
  console.log('LOGIN set cookie token:', refreshToken.slice(0, 20))
  console.log('LOGIN response header:', res.getHeader('Set-Cookie'))
  return accessToken
}

// ── POST /api/auth/signup ──────────────────────────────────────────────────
router.post('/signup', signupLimiter, async (req, res) => {
  try {
    const { name, email, password } = req.body
    if (!name || !email || !password)
      return res.status(400).json({ error: 'name, email, and password are required' })
    if (password.length < 8)
      return res.status(400).json({ error: 'Password must be at least 8 characters' })

    const existing = await User.findOne({ email: email.toLowerCase() })
    if (existing) return res.status(409).json({ error: 'Email already registered' })

    const passwordHash = await bcrypt.hash(password, 12)
    const user         = await User.create({ name, email: email.toLowerCase(), passwordHash })
    const accessToken  = await issueTokens(res, user, req)

    res.status(201).json({
      accessToken,
      user: { _id: user._id, name: user.name, email: user.email, role: user.role },
    })
  } catch (err) {
    console.error('[auth/signup]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── POST /api/auth/login ───────────────────────────────────────────────────
router.post('/login', loginLimiter, async (req, res) => {
  try {
    const { email, password } = req.body
    if (!email || !password)
      return res.status(400).json({ error: 'email and password are required' })

    const user = await User.findOne({ email: email.toLowerCase() })

    // Always run bcrypt even if user not found — prevents timing attacks
    const dummyHash = '$2a$12$dummyhashfortimingattackprevention000000000000000000000'
    const valid     = user
      ? await bcrypt.compare(password, user.passwordHash)
      : await bcrypt.compare(password, dummyHash).then(() => false)

    if (!user || !valid)
      return res.status(401).json({ error: 'Invalid credentials' })

    const accessToken = await issueTokens(res, user, req)
    res.json({
      accessToken,
      user: { _id: user._id, name: user.name, email: user.email, role: user.role },
    })
  } catch (err) {
    console.error('[auth/login]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── POST /api/auth/refresh ─────────────────────────────────────────────────
// Returns 200 always — null tokens mean "not logged in", not an error.
// Proper errors (DB down etc.) return 503 so frontend can retry vs redirect.
router.post('/refresh', refreshLimiter, async (req, res) => {
   // ✅ ADD THIS
 
  try {
    const rawRefresh = req.cookies?.vantage_refresh

    if (!rawRefresh)
      return res.status(200).json({ accessToken: null, user: null })

    let payload
    try {
      payload = verifyRefreshToken(rawRefresh)
    } catch {
      clearRefreshCookie(res)
      return res.status(200).json({ accessToken: null, user: null })
    }

    const stored = await RefreshToken.findOne({ tokenHash: hashToken(rawRefresh) })
    if (!stored) {
      // Token not in DB — expired, logged out, or server was wiped.
      // Clear cookie so browser stops sending it.
      clearRefreshCookie(res)
      return res.status(200).json({ accessToken: null, user: null })
    }

    const user = await User.findById(payload.sub).select('-passwordHash')
    if (!user) {
      await RefreshToken.deleteOne({ _id: stored._id })
      clearRefreshCookie(res)
      return res.status(200).json({ accessToken: null, user: null })
    }

    // ── Token rotation — safe because we handle race with the limiter ──────
    // Delete old refresh token, issue new pair (access + refresh)
    await RefreshToken.deleteOne({ _id: stored._id })
    const newAccessToken  = signAccessToken(user._id)
    const newRefreshToken = signRefreshToken(user._id)

    await RefreshToken.create({
      userId:    user._id,
      tokenHash: hashToken(newRefreshToken),
      expiresAt: new Date(Date.now() + REFRESH_EXPIRY_MS),
      userAgent: req.headers['user-agent'],
      ip:        req.ip,
    })

    setRefreshCookie(res, newRefreshToken)

    return res.status(200).json({
      accessToken: newAccessToken,
      user: { _id: user._id, name: user.name, email: user.email, role: user.role },
    })
  } catch (err) {
    // DB error or unexpected — return 503 so frontend retries, not logs out
    console.error('[auth/refresh]', err)
    return res.status(503).json({ error: 'Service temporarily unavailable — retry shortly' })
  }
})

// ── POST /api/auth/logout ──────────────────────────────────────────────────
router.post('/logout', async (req, res) => {
  try {
    const rawRefresh = req.cookies?.vantage_refresh
    if (rawRefresh) {
      await RefreshToken.deleteOne({ tokenHash: hashToken(rawRefresh) })
    }
    clearRefreshCookie(res)
    res.json({ ok: true })
  } catch (err) {
    console.error('[auth/logout]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── POST /api/auth/logout-all ──────────────────────────────────────────────
router.post('/logout-all', requireAuth, async (req, res) => {
  try {
    await RefreshToken.deleteMany({ userId: req.user._id })
    clearRefreshCookie(res)
    res.json({ ok: true, message: 'Logged out from all devices' })
  } catch (err) {
    console.error('[auth/logout-all]', err)
    res.status(500).json({ error: 'Internal server error' })
  }
})

// ── GET /api/auth/me ───────────────────────────────────────────────────────
router.get('/me', requireAuth, (req, res) => {
  res.json({ user: req.user })
})

export default router