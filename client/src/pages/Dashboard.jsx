// src/pages/Dashboard.jsx  — RESPONSIVE VERSION
import { useEffect, useState } from 'react'
import { useNavigate, Link }   from 'react-router-dom'
import useRunStore, { AGENT_NODES, AGENT_LABELS } from '../store/useRunStore'
import AgentCard       from '../components/AgentCard'
import ConfidenceBar   from '../components/ConfidenceBar'
import TranscriptFeed  from '../components/TranscriptFeed'
import DecisionPanel   from '../components/DecisionPanel'
import { useAuth }     from '../context/AuthContext'

const STATUS_LABEL = {
  idle:     { text: 'IDLE',     color: 'var(--text-3)' },
  starting: { text: 'INIT',     color: 'var(--amber)' },
  running:  { text: 'LIVE',     color: 'var(--green)' },
  done:     { text: 'COMPLETE', color: 'var(--green)' },
  error:    { text: 'FAULT',    color: 'var(--red)' },
}

const MOBILE_TABS = ['agents', 'monitor', 'transcript', 'decision']

export default function Dashboard() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [mobileTab, setMobileTab] = useState('monitor')
  const [menuOpen,  setMenuOpen]  = useState(false)

  const runStatus       = useRunStore(s => s.runStatus)
  const query           = useRunStore(s => s.query)
  const sessionId       = useRunStore(s => s.sessionId)
  const agents          = useRunStore(s => s.agents)
  const transcript      = useRunStore(s => s.transcript)
  const confidenceScore = useRunStore(s => s.confidenceScore)
  const bestScore       = useRunStore(s => s.bestScore)
  const currentRound    = useRunStore(s => s.currentRound)
  const finalDecision   = useRunStore(s => s.finalDecision)
  const heartbeatAction = useRunStore(s => s.heartbeatAction)
  const errorMsg        = useRunStore(s => s.errorMsg)
  const reset           = useRunStore(s => s.reset)

  useEffect(() => {
    if (runStatus === 'idle') navigate('/')
  }, [runStatus])

  const handleNewRun = () => { reset(); navigate('/') }
  const sc    = STATUS_LABEL[runStatus] ?? STATUS_LABEL.idle
  const isLive = runStatus === 'running' || runStatus === 'starting'

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-0)' }}>

      {/* Top bar */}
      <div className="topbar" style={{ flexWrap: 'wrap', gap: 8, position: 'relative' }}>
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub" style={{
          maxWidth: 'clamp(100px, 30vw, 400px)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {query || 'no query'}
        </span>

        {/* Status pill */}
        <span style={{
          marginLeft: 'auto', fontSize: 10, fontWeight: 700, letterSpacing: '0.15em',
          color: sc.color, display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <span className={`topbar-dot ${isLive ? 'live' : ''}`} style={{ background: sc.color }} />
          {sc.text}
        </span>

        {sessionId && (
          <span className="data-dim" style={{ fontSize: 10, marginLeft: 8 }}>
            {sessionId.slice(0, 8)}
          </span>
        )}

        {/* Nav links (hidden on very small screens) */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <Link to="/knowledge" style={{ color: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--mono)', textDecoration: 'none' }}>
            knowledge
          </Link>
          <Link to="/history" style={{ color: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--mono)', textDecoration: 'none' }}>
            history
          </Link>
          <button className="btn" style={{ padding: '5px 12px', fontSize: 10 }} onClick={handleNewRun}>
            ↩ new run
          </button>
          <button className="btn" style={{ padding: '5px 12px', fontSize: 10, color: 'var(--text-3)' }} onClick={logout}>
            sign out
          </button>
        </div>
      </div>

      {/* Error banner */}
      {runStatus === 'error' && (
        <div style={{
          background: 'var(--red-dim)', border: '1px solid var(--red)', padding: '10px 16px',
          fontSize: 11, color: 'var(--red)', display: 'flex', gap: 10,
        }}>
          <span>✕ FAULT:</span><span>{errorMsg}</span>
        </div>
      )}

      {/* Mobile tab bar */}
      <div style={{
        display: 'none',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-1)',
      }} className="mobile-tabs">
        {MOBILE_TABS.map(t => (
          <button key={t} onClick={() => setMobileTab(t)} style={{
            flex: 1, background: 'none', border: 'none',
            borderBottom: `2px solid ${mobileTab === t ? 'var(--amber)' : 'transparent'}`,
            color: mobileTab === t ? 'var(--amber)' : 'var(--text-3)',
            fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.1em',
            textTransform: 'uppercase', padding: '10px 4px', cursor: 'pointer',
          }}>
            {t}
          </button>
        ))}
      </div>

      {/* ── DESKTOP GRID / MOBILE TABS ─────────────────────────────────────── */}
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: 'clamp(200px, 22%, 280px) 1fr clamp(240px, 26%, 320px)',
        gridTemplateRows:    'auto 1fr',
        gap: 10,
        padding: '10px 14px',
        minHeight: 0,
      }} className="dashboard-grid">

        {/* ── LEFT: agent stations ──────────────────────────────────────── */}
        <div style={{
          gridRow: '1 / 3',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflowY: 'auto',
        }} className={`dash-col-left ${mobileTab !== 'agents' ? 'desktop-only' : ''}`}>
          <div className="data-dim" style={{ fontSize: 10, padding: '4px 0', letterSpacing: '0.15em' }}>
            AGENT STATIONS
          </div>
          {AGENT_NODES.map(nodeKey => (
            <AgentCard
              key={nodeKey}
              nodeKey={nodeKey}
              label={AGENT_LABELS[nodeKey]}
              agentState={agents[nodeKey]}
            />
          ))}
        </div>

        {/* ── CENTRE TOP: confidence + heartbeat ───────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}
             className={mobileTab !== 'monitor' ? 'desktop-only' : ''}>
          <ConfidenceBar score={confidenceScore} best={bestScore} round={currentRound} />

          <div className="panel">
            <div className="panel-header" style={{ justifyContent: 'space-between' }}>
              <span className="panel-label">Heartbeat</span>
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                color: heartbeatAction === 'exit' ? 'var(--green)' : heartbeatAction === 'pivot' ? 'var(--red)' : 'var(--amber)',
              }}>
                {heartbeatAction.toUpperCase()}
              </span>
            </div>
            <div className="panel-body" style={{ padding: '10px 14px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {['refine', 'pivot', 'exit'].map(action => (
                  <div key={action} style={{
                    padding: '8px 6px',
                    background: heartbeatAction === action ? 'var(--bg-3)' : 'transparent',
                    border: `1px solid ${heartbeatAction === action ? 'var(--border-lit)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 10, fontWeight: heartbeatAction === action ? 700 : 400,
                    color: heartbeatAction === action ? 'var(--text-0)' : 'var(--text-3)',
                    textAlign: 'center', letterSpacing: '0.1em', textTransform: 'uppercase',
                  }}>
                    {action}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT: transcript ─────────────────────────────────────────── */}
        <div style={{ gridRow: '1 / 3', minHeight: 0, display: 'flex', flexDirection: 'column' }}
             className={mobileTab !== 'transcript' ? 'desktop-only' : ''}>
          <TranscriptFeed events={transcript} />
        </div>

        {/* ── CENTRE BOTTOM: decision ───────────────────────────────────── */}
        <div style={{ overflowY: 'auto' }}
             className={mobileTab !== 'decision' ? 'desktop-only' : ''}>
          {finalDecision ? (
            <DecisionPanel decision={finalDecision} confidence={confidenceScore} />
          ) : (
            <div className="panel" style={{ height: '100%' }}>
              <div className="panel-header">
                <span className="panel-label">CEO Decision</span>
              </div>
              <div className="panel-body" style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '40px 16px', color: 'var(--text-3)', fontSize: 12,
              }}>
                {isLive ? <span className="cursor">Awaiting final decision</span> : 'No decision yet'}
              </div>
            </div>
          )}
        </div>

      </div>

      {/* Responsive CSS */}
      <style>{`
        @media (max-width: 768px) {
          .dashboard-grid {
            display: block !important;
            padding: 10px 10px !important;
          }
          .mobile-tabs {
            display: flex !important;
          }
          .desktop-only {
            display: none !important;
          }
          .dash-col-left {
            display: flex !important;
          }
        }
      `}</style>
    </div>
  )
}