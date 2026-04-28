// middleware/auth.js
import jwt from 'jsonwebtoken'
import { User, RefreshToken } from '../models/auth.js'

// ── CRASH if secrets missing in production ────────────────────────────────
if (process.env.NODE_ENV === 'production') {
  if (!process.env.ACCESS_TOKEN_SECRET)  throw new Error('ACCESS_TOKEN_SECRET is not set')
  if (!process.env.REFRESH_TOKEN_SECRET) throw new Error('REFRESH_TOKEN_SECRET is not set')
}

const ACCESS_SECRET  = process.env.ACCESS_TOKEN_SECRET  || 'access-secret-dev-only'
const REFRESH_SECRET = process.env.REFRESH_TOKEN_SECRET || 'refresh-secret-dev-only'
const IS_PROD        = process.env.NODE_ENV === 'production'

export const ACCESS_EXPIRY     = '15m'
export const REFRESH_EXPIRY    = '7d'
export const REFRESH_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000

export function signAccessToken(userId) {
  return jwt.sign({ sub: userId.toString(), type: 'access' }, ACCESS_SECRET, { expiresIn: ACCESS_EXPIRY })
}

export function signRefreshToken(userId) {
  return jwt.sign({ sub: userId.toString(), type: 'refresh' }, REFRESH_SECRET, { expiresIn: REFRESH_EXPIRY })
}

export function verifyAccessToken(token) {
  return jwt.verify(token, ACCESS_SECRET)
}

export function verifyRefreshToken(token) {
  return jwt.verify(token, REFRESH_SECRET)
}

export function setRefreshCookie(res, token) {
  res.cookie('vantage_refresh', token, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/',
    maxAge: REFRESH_EXPIRY_MS,
  })
}

export function clearRefreshCookie(res) {
  res.clearCookie('vantage_refresh', {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/',
  })

  // also clear old cookie if it was created under /api/auth
  res.clearCookie('vantage_refresh', {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/api/auth',
  })
}

export async function requireAuth(req, res, next) {
  const header = req.headers.authorization
  if (!header?.startsWith('Bearer '))
    return res.status(401).json({ error: 'No access token provided' })

  const token = header.slice(7)
  try {
    const payload = verifyAccessToken(token)
    const user    = await User.findById(payload.sub).select('-passwordHash')
    if (!user) return res.status(401).json({ error: 'User not found' })
    req.user = user
    next()
  } catch (err) {
    if (err.name === 'TokenExpiredError')
      return res.status(401).json({ error: 'Access token expired', code: 'TOKEN_EXPIRED' })
    return res.status(401).json({ error: 'Invalid access token' })
  }
}

export function optionalAuth(req, res, next) {
  const header = req.headers.authorization
  if (!header?.startsWith('Bearer ')) return next()
  try {
    const payload = verifyAccessToken(header.slice(7))
    User.findById(payload.sub).select('-passwordHash')
      .then(user => { req.user = user; next() })
      .catch(() => next())
  } catch { next() }
}