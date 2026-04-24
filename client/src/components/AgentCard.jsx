// src/components/AgentCard.jsx
import { useState } from 'react'

const STATUS_CONFIG = {
  idle:    { label: 'STANDBY', cls: 'badge-idle',    icon: '○' },
  running: { label: 'ACTIVE',  cls: 'badge-running', icon: '◉' },
  done:    { label: 'DONE',    cls: 'badge-done',    icon: '●' },
  error:   { label: 'FAULT',   cls: 'badge-error',   icon: '✕' },
}

const AGENT_ICONS = {
  cache_check_node:  '⬡',
  research_node:     '◈',
  finance_node:      '◎',
  competitor_node:   '◇',
  critic_node:       '◆',
  heartbeat_node:    '♦',
  ceo_node:          '★',
  meta_eval_node:    '◉',
}

export default function AgentCard({ nodeKey, label, agentState }) {
  const [expanded, setExpanded] = useState(false)
  const { status, round, output, ts } = agentState
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle

  const tsStr = ts
    ? new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false })
    : '--:--:--'

  // Pull a short preview from any string field in output
  const preview = output
    ? Object.values(output).find(v => typeof v === 'string' && v.length > 10)?.slice(0, 120)
    : null

  return (
    <div
      className={`panel agent-card agent-card--${status}`}
      style={{ cursor: preview ? 'pointer' : 'default' }}
      onClick={() => preview && setExpanded(e => !e)}
    >
      <div className="panel-header" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontSize: 16,
            color: status === 'running' ? 'var(--amber)'
                 : status === 'done'    ? 'var(--green)'
                 : 'var(--text-3)',
          }}>
            {AGENT_ICONS[nodeKey] ?? '○'}
          </span>
          <span className="panel-label">{label}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {round > 0 && (
            <span className="data-dim" style={{ fontSize: 10 }}>R{round}</span>
          )}
          <span className={`badge ${cfg.cls}`}>
            {status === 'running' && (
              <span style={{ animation: 'pulse-dot 1s infinite', display: 'inline-block' }}>
                {cfg.icon}
              </span>
            )}
            {status !== 'running' && cfg.icon}
            {cfg.label}
          </span>
        </div>
      </div>

      <div className="panel-body" style={{ padding: '10px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="data-dim" style={{ fontSize: 10 }}>{tsStr}</span>
          {preview && (
            <span className="data-dim" style={{ fontSize: 10 }}>
              {expanded ? '▲ collapse' : '▼ expand'}
            </span>
          )}
        </div>

        {status === 'running' && (
          <div className="agent-progress" style={{ marginTop: 8 }}>
            <div className="agent-progress-bar" />
          </div>
        )}

        {expanded && preview && (
          <div className="agent-output animate-in">
            <p className="data-value" style={{ marginTop: 10, whiteSpace: 'pre-wrap', fontSize: 11 }}>
              {preview}
              {preview.length >= 120 && <span className="data-dim">…</span>}
            </p>
          </div>
        )}
      </div>

      <style>{`
        .agent-card { transition: border-color 0.2s ease; }
        .agent-card--running { border-color: var(--amber-dim); }
        .agent-card--done    { border-color: var(--green-dim); }
        .agent-card--error   { border-color: var(--red-dim); }

        .agent-progress {
          height: 2px;
          background: var(--bg-3);
          border-radius: 1px;
          overflow: hidden;
        }
        .agent-progress-bar {
          height: 100%;
          width: 40%;
          background: var(--amber);
          border-radius: 1px;
          animation: progress-slide 1.4s ease-in-out infinite;
        }
        @keyframes progress-slide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  )
}