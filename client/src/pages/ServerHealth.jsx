// src/pages/ServerHealth.jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const API = import.meta.env.VITE_API_URL || 'https://multi-agent-decision-system.onrender.com'
const FASTAPI = import.meta.env.VITE_FASTAPI_URL || 'http://localhost:8000'
const POLL_INTERVAL = 10_000  // re-check every 10s

// ── individual service check ───────────────────────────────────────────────
async function checkEndpoint(url, timeout = 5000) {
  const start = Date.now()
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), timeout)
    const res   = await fetch(url, { signal: ctrl.signal, credentials: 'include' })
    clearTimeout(timer)
    const latency = Date.now() - start
    const data    = await res.json().catch(() => ({}))
    return { status: res.ok ? 'ok' : 'degraded', latency, data, code: res.status }
  } catch (err) {
    return { status: 'down', latency: Date.now() - start, error: err.name === 'AbortError' ? 'timeout' : err.message }
  }
}

function StatusDot({ status }) {
  const color = status === 'ok' ? 'var(--green)' : status === 'degraded' ? 'var(--amber)' : 'var(--red)'
  const pulse = status === 'ok'
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: color, flexShrink: 0,
      boxShadow: pulse ? `0 0 6px ${color}` : 'none',
      animation: pulse ? 'pulse 2s infinite' : 'none',
    }} />
  )
}

function StatusBadge({ status }) {
  const map = { ok: ['ONLINE', 'var(--green)'], degraded: ['DEGRADED', 'var(--amber)'], down: ['OFFLINE', 'var(--red)'], checking: ['CHECKING', 'var(--text-3)'] }
  const [label, color] = map[status] ?? map.checking
  return (
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', color, fontFamily: 'var(--mono)' }}>
      {label}
    </span>
  )
}

function ServiceRow({ name, desc, result }) {
  const latencyColor = !result?.latency ? 'var(--text-3)'
    : result.latency < 200 ? 'var(--green)'
    : result.latency < 600 ? 'var(--amber)'
    : 'var(--red)'

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '16px 1fr auto auto',
      alignItems: 'center',
      gap: 12,
      padding: '12px 16px',
      borderBottom: '1px solid var(--border)',
    }}>
      <StatusDot status={result?.status ?? 'checking'} />
      <div>
        <div style={{ fontSize: 12, color: 'var(--text-1)', fontFamily: 'var(--mono)', fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{desc}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        {result?.latency != null && (
          <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: latencyColor }}>
            {result.latency}ms
          </span>
        )}
      </div>
      <div style={{ minWidth: 70, textAlign: 'right' }}>
        <StatusBadge status={result?.status ?? 'checking'} />
      </div>
    </div>
  )
}

function MetricBox({ label, value, unit, color }) {
  return (
    <div className="panel" style={{ flex: '1 1 120px' }}>
      <div className="panel-body" style={{ padding: '14px 16px' }}>
        <div className="data-dim" style={{ fontSize: 9, marginBottom: 6 }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: color || 'var(--text-0)', fontFamily: 'var(--mono)' }}>
          {value ?? '—'}
          {unit && <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 3 }}>{unit}</span>}
        </div>
      </div>
    </div>
  )
}

// Tiny sparkline using SVG
function Sparkline({ data, color = 'var(--amber)', height = 32 }) {
  if (!data?.length) return null
  const max = Math.max(...data, 1)
  const w   = 120
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = height - (v / max) * height
    return `${x},${y}`
  }).join(' ')
  return (
    <svg width={w} height={height} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

export default function ServerHealth() {
  const { authFetch } = useAuth()
  const navigate      = useNavigate()

  const [checks,     setChecks]     = useState({})
  const [serverData, setServerData] = useState(null)
  const [history,    setHistory]    = useState([])     // latency history for sparkline
  const [lastCheck,  setLastCheck]  = useState(null)
  const [checking,   setChecking]   = useState(false)
  const [countdown,  setCountdown]  = useState(POLL_INTERVAL / 1000)
  const timerRef    = useRef(null)
  const countRef    = useRef(null)

  const runChecks = useCallback(async () => {
    setChecking(true)
    setCountdown(POLL_INTERVAL / 1000)

    const [nodeHealth, fapiHealth, authCheck] = await Promise.all([
      checkEndpoint(`${API}/health`),
      checkEndpoint(`${FASTAPI}/health`),
      checkEndpoint(`${API}/health`)
    ])

    setChecks({ node: nodeHealth, fastapi: fapiHealth, auth: authCheck })
    setServerData(nodeHealth.data)
    setLastCheck(new Date())
    setHistory(prev => [...prev.slice(-29), nodeHealth.latency ?? 0])
    setChecking(false)
  }, [])

  // Poll every 10s
  useEffect(() => {
    runChecks()
    timerRef.current = setInterval(runChecks, POLL_INTERVAL)

    // Countdown ticker
    countRef.current = setInterval(() => {
      setCountdown(prev => prev <= 1 ? POLL_INTERVAL / 1000 : prev - 1)
    }, 1000)

    return () => {
      clearInterval(timerRef.current)
      clearInterval(countRef.current)
    }
  }, [runChecks])

  const allOk = Object.values(checks).every(c => c?.status === 'ok')
  const anyDown = Object.values(checks).some(c => c?.status === 'down')
  const overallStatus = Object.keys(checks).length === 0 ? 'checking'
    : anyDown ? 'down' : allOk ? 'ok' : 'degraded'

  const overallColor = overallStatus === 'ok' ? 'var(--green)'
    : overallStatus === 'degraded' ? 'var(--amber)' : 'var(--red)'

  const uptime = serverData?.uptime
  const uptimeStr = uptime == null ? '—'
    : uptime < 60 ? `${uptime}s`
    : uptime < 3600 ? `${Math.floor(uptime / 60)}m ${uptime % 60}s`
    : `${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m`

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-0)' }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes spin { to { transform: rotate(360deg) } }
      `}</style>

      {/* Topbar */}
      <div className="topbar">
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub">server health</span>

        {/* Overall status pill */}
        <span style={{
          marginLeft: 16, display: 'flex', alignItems: 'center', gap: 6,
          fontSize: 10, fontWeight: 700, letterSpacing: '0.15em', color: overallColor,
        }}>
          <StatusDot status={overallStatus} />
          {overallStatus.toUpperCase()}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="data-dim" style={{ fontSize: 10 }}>
            next check in {countdown}s
          </span>
          <button
            className="btn"
            style={{ padding: '6px 12px', fontSize: 11 }}
            onClick={runChecks}
            disabled={checking}
          >
            {checking
              ? <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>↻</span>
              : '↻ refresh'}
          </button>
          <Link to="/" style={{ textDecoration: 'none' }}>
            <button className="btn" style={{ padding: '6px 14px', fontSize: 11 }}>↩ home</button>
          </Link>
        </div>
      </div>

      <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Metrics row */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <MetricBox
            label="NODE LATENCY"
            value={checks.node?.latency ?? '—'}
            unit="ms"
            color={checks.node?.latency < 200 ? 'var(--green)' : 'var(--amber)'}
          />
          <MetricBox
            label="UPTIME"
            value={uptimeStr}
            color="var(--text-0)"
          />
          <MetricBox
            label="HEAP USED"
            value={serverData?.memMB ?? '—'}
            unit="MB"
            color={serverData?.memMB > 400 ? 'var(--amber)' : 'var(--green)'}
          />
          <MetricBox
            label="MONGO"
            value={serverData?.mongoState ?? '—'}
            color={serverData?.mongoState === 'connected' ? 'var(--green)' : 'var(--red)'}
          />
          <MetricBox
            label="FASTAPI LATENCY"
            value={checks.fastapi?.latency ?? '—'}
            unit="ms"
            color={checks.fastapi?.status === 'ok' ? 'var(--green)' : 'var(--red)'}
          />
        </div>

        {/* Services table */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-label">Services</span>
            {lastCheck && (
              <span className="data-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>
                last checked {lastCheck.toLocaleTimeString()}
              </span>
            )}
          </div>
          <ServiceRow
            name="Node.js API"
            desc={`${API}/health — Express + Socket.IO`}
            result={checks.node}
          />
          <ServiceRow
            name="FastAPI Agent Service"
            desc={`${FASTAPI}/health — LangGraph pipeline`}
            result={checks.fastapi}
          />
          {/* <ServiceRow
            name="Auth Endpoint"
            desc={`${API}/api/auth/me — session validation`}
            result={checks.auth}
          /> */}
          <ServiceRow
            name="MongoDB"
            desc="via Node.js health report"
            result={serverData?.mongoState === 'connected'
              ? { status: 'ok',  latency: null }
              : { status: 'down', latency: null }}
          />
        </div>

        {/* Latency sparkline */}
        {history.length > 1 && (
          <div className="panel">
            <div className="panel-header">
              <span className="panel-label">Node.js Latency History</span>
              <span className="data-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>
                last {history.length} checks · 10s intervals
              </span>
            </div>
            <div className="panel-body" style={{ padding: '16px', display: 'flex', alignItems: 'flex-end', gap: 16 }}>
              <Sparkline data={history} height={48} color="var(--amber)" />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                  avg <span style={{ color: 'var(--text-1)' }}>
                    {Math.round(history.reduce((a, b) => a + b, 0) / history.length)}ms
                  </span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                  max <span style={{ color: 'var(--amber)' }}>{Math.max(...history)}ms</span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                  min <span style={{ color: 'var(--green)' }}>{Math.min(...history)}ms</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Raw server response */}
        {serverData && (
          <div className="panel">
            <div className="panel-header">
              <span className="panel-label">Raw /health Response</span>
            </div>
            <div className="panel-body" style={{
              fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-2)',
              whiteSpace: 'pre', overflowX: 'auto', padding: '14px 16px',
            }}>
              {JSON.stringify(serverData, null, 2)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}