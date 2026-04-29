// middleware/auth.js
import jwt from 'jsonwebtoken'
import { User } from '../models/auth.js'

// ── CRASH if secrets missing in production ────────────────────────────────
if (process.env.NODE_ENV === 'production') {
  if (!process.env.ACCESS_TOKEN_SECRET) {
    throw new Error('ACCESS_TOKEN_SECRET is not set')
  }

  if (!process.env.REFRESH_TOKEN_SECRET) {
    throw new Error('REFRESH_TOKEN_SECRET is not set')
  }
}

const ACCESS_SECRET = process.env.ACCESS_TOKEN_SECRET || 'access-secret-dev-only'
const REFRESH_SECRET = process.env.REFRESH_TOKEN_SECRET || 'refresh-secret-dev-only'
const IS_PROD = process.env.NODE_ENV === 'production'

export const ACCESS_EXPIRY = '15m'
export const REFRESH_EXPIRY = '7d'
export const ACCESS_EXPIRY_MS = 15 * 60 * 1000
export const REFRESH_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000

// ── Token signing ─────────────────────────────────────────────────────────
export function signAccessToken(userId) {
  return jwt.sign(
    {
      sub: userId.toString(),
      type: 'access',
    },
    ACCESS_SECRET,
    { expiresIn: ACCESS_EXPIRY }
  )
}

export function signRefreshToken(userId) {
  return jwt.sign(
    {
      sub: userId.toString(),
      type: 'refresh',
    },
    REFRESH_SECRET,
    { expiresIn: REFRESH_EXPIRY }
  )
}

// ── Token verify ──────────────────────────────────────────────────────────
export function verifyAccessToken(token) {
  return jwt.verify(token, ACCESS_SECRET)
}

export function verifyRefreshToken(token) {
  return jwt.verify(token, REFRESH_SECRET)
}

// ── Cookies ───────────────────────────────────────────────────────────────
export function setAccessCookie(res, token) {
  res.cookie('vantage_access', token, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/',
    maxAge: ACCESS_EXPIRY_MS,
  })
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

export function clearAccessCookie(res) {
  res.clearCookie('vantage_access', {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/',
  })
}

export function clearRefreshCookie(res) {
  res.clearCookie('vantage_refresh', {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/',
  })

  res.clearCookie('vantage_refresh', {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    path: '/api/auth',
  })
}

export function clearAuthCookies(res) {
  clearAccessCookie(res)
  clearRefreshCookie(res)
}

// ── Helper: get access token from header OR cookie ────────────────────────
function getAccessTokenFromReq(req) {
  const header = req.headers.authorization

  if (header?.startsWith('Bearer ')) {
    return header.slice(7)
  }

  if (req.cookies?.vantage_access) {
    return req.cookies.vantage_access
  }

  return null
}

// ── Required auth middleware ──────────────────────────────────────────────
export async function requireAuth(req, res, next) {
  const token = getAccessTokenFromReq(req)

  if (!token) {
    return res.status(401).json({
      error: 'No access token provided',
    })
  }

  try {
    const payload = verifyAccessToken(token)

    if (payload.type !== 'access') {
      return res.status(401).json({
        error: 'Invalid token type',
      })
    }

    const user = await User.findById(payload.sub).select('-passwordHash')

    if (!user) {
      return res.status(401).json({
        error: 'User not found',
      })
    }

    req.user = user
    next()
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: 'Access token expired',
        code: 'TOKEN_EXPIRED',
      })
    }

    return res.status(401).json({
      error: 'Invalid access token',
    })
  }
}

// ── Optional auth middleware ──────────────────────────────────────────────
export async function optionalAuth(req, res, next) {
  const token = getAccessTokenFromReq(req)

  if (!token) {
    return next()
  }

  try {
    const payload = verifyAccessToken(token)

    if (payload.type !== 'access') {
      return next()
    }

    const user = await User.findById(payload.sub).select('-passwordHash')

    if (user) {
      req.user = user
    }

    return next()
  } catch (err) {
    console.log('[optionalAuth] ignored:', err.message)
    return next()
  }
}