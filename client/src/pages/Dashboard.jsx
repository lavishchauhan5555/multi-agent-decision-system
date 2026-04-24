// src/pages/Dashboard.jsx
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import useRunStore, { AGENT_NODES, AGENT_LABELS } from '../store/useRunStore'
import AgentCard       from '../components/AgentCard'
import ConfidenceBar   from '../components/ConfidenceBar'
import TranscriptFeed  from '../components/TranscriptFeed'
import DecisionPanel   from '../components/DecisionPanel'

const STATUS_LABEL = {
  idle:     { text: 'IDLE',     color: 'var(--text-3)' },
  starting: { text: 'INIT',     color: 'var(--amber)' },
  running:  { text: 'LIVE',     color: 'var(--green)' },
  done:     { text: 'COMPLETE', color: 'var(--green)' },
  error:    { text: 'FAULT',    color: 'var(--red)' },
}

export default function Dashboard() {
  const navigate = useNavigate()

  const runStatus      = useRunStore(s => s.runStatus)
  const query          = useRunStore(s => s.query)
  const sessionId      = useRunStore(s => s.sessionId)
  const agents         = useRunStore(s => s.agents)
  const transcript     = useRunStore(s => s.transcript)
  const confidenceScore= useRunStore(s => s.confidenceScore)
  const bestScore      = useRunStore(s => s.bestScore)
  const currentRound   = useRunStore(s => s.currentRound)
  const finalDecision  = useRunStore(s => s.finalDecision)
  const heartbeatAction= useRunStore(s => s.heartbeatAction)
  const errorMsg       = useRunStore(s => s.errorMsg)
  const reset          = useRunStore(s => s.reset)

  // Redirect if no active session
  useEffect(() => {
    if (runStatus === 'idle') navigate('/')
  }, [runStatus])

  const handleNewRun = () => {
    reset()
    navigate('/')
  }

  const sc = STATUS_LABEL[runStatus] ?? STATUS_LABEL.idle
  const isLive = runStatus === 'running' || runStatus === 'starting'

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* Top bar */}
      <div className="topbar">
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub" style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {query || 'no query'}
        </span>

        {/* Status pill */}
        <span style={{
          marginLeft: 'auto',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.15em',
          color: sc.color,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}>
          <span className={`topbar-dot ${isLive ? 'live' : ''}`} style={{ background: sc.color }} />
          {sc.text}
        </span>

        {/* Session ID */}
        {sessionId && (
          <span className="data-dim" style={{ fontSize: 10, marginLeft: 16 }}>
            {sessionId.slice(0, 8)}
          </span>
        )}

        <button className="btn" style={{ marginLeft: 12, padding: '6px 14px', fontSize: 11 }} onClick={handleNewRun}>
          ↩ new run
        </button>
      </div>

      {/* Error banner */}
      {runStatus === 'error' && (
        <div style={{
          background: 'var(--red-dim)',
          border: '1px solid var(--red)',
          borderRadius: 0,
          padding: '10px 24px',
          fontSize: 11,
          color: 'var(--red)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}>
          <span>✕ FAULT:</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main grid */}
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: '280px 1fr 320px',
        gridTemplateRows: 'auto 1fr',
        gap: 12,
        padding: '12px 16px',
        minHeight: 0,
      }}>

        {/* ── LEFT COL: agent stations ────────────────────────────────── */}
        <div style={{
          gridRow: '1 / 3',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflowY: 'auto',
        }}>
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

        {/* ── CENTRE TOP: confidence + heartbeat ─────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          <ConfidenceBar
            score={confidenceScore}
            best={bestScore}
            round={currentRound}
          />

          {/* Heartbeat action */}
          <div className="panel">
            <div className="panel-header" style={{ justifyContent: 'space-between' }}>
              <span className="panel-label">Heartbeat</span>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.12em',
                color: heartbeatAction === 'exit'   ? 'var(--green)'
                     : heartbeatAction === 'pivot'  ? 'var(--red)'
                     : 'var(--amber)',
              }}>
                {heartbeatAction.toUpperCase()}
              </span>
            </div>
            <div className="panel-body" style={{ padding: '10px 16px' }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 6,
              }}>
                {['refine', 'pivot', 'exit'].map(action => (
                  <div key={action} style={{
                    padding: '6px 10px',
                    background: heartbeatAction === action ? 'var(--bg-3)' : 'transparent',
                    border: `1px solid ${heartbeatAction === action ? 'var(--border-lit)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 10,
                    fontWeight: heartbeatAction === action ? 700 : 400,
                    color: heartbeatAction === action ? 'var(--text-0)' : 'var(--text-3)',
                    textAlign: 'center',
                    letterSpacing: '0.1em',
                    textTransform: 'uppercase',
                  }}>
                    {action}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT COL: transcript ───────────────────────────────────── */}
        <div style={{ gridRow: '1 / 3', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <TranscriptFeed events={transcript} />
        </div>

        {/* ── CENTRE BOTTOM: decision panel ──────────────────────────── */}
        <div style={{ overflowY: 'auto' }}>
          {finalDecision ? (
            <DecisionPanel
              decision={finalDecision}
              confidence={confidenceScore}
            />
          ) : (
            <div className="panel" style={{ height: '100%' }}>
              <div className="panel-header">
                <span className="panel-label">CEO Decision</span>
              </div>
              <div className="panel-body" style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '40px 16px',
                color: 'var(--text-3)',
                fontSize: 12,
              }}>
                {isLive
                  ? <span className="cursor">Awaiting final decision</span>
                  : 'No decision yet'}
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}