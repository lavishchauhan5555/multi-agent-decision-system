// src/components/DecisionPanel.jsx

const REC_CONFIG = {
  PROCEED:             { color: 'var(--green)', bg: 'var(--green-glow)', label: '✓ PROCEED' },
  'DO NOT PROCEED':    { color: 'var(--red)',   bg: 'var(--red-dim)',    label: '✕ DO NOT PROCEED' },
  'CONDITIONAL PROCEED':{ color: 'var(--amber)', bg: 'var(--amber-glow)', label: '◈ CONDITIONAL' },
}

function extractRecommendation(text) {
  if (!text) return null
  if (/\bPROCEED\b/.test(text) && !/DO NOT/.test(text)) return 'PROCEED'
  if (/DO NOT PROCEED/.test(text)) return 'DO NOT PROCEED'
  if (/CONDITIONAL/.test(text)) return 'CONDITIONAL PROCEED'
  return null
}

export default function DecisionPanel({ decision, confidence, reasoning }) {
  if (!decision) return null

  const rec    = extractRecommendation(decision)
  const recCfg = rec ? REC_CONFIG[rec] : null

  return (
    <div className="panel animate-in" style={{ borderColor: recCfg?.color ?? 'var(--border)' }}>
      <div className="panel-header" style={{
        background: recCfg?.bg ?? 'var(--bg-2)',
        borderBottomColor: recCfg?.color ?? 'var(--border)',
        justifyContent: 'space-between',
      }}>
        <span className="panel-label" style={{ color: recCfg?.color ?? 'var(--text-2)' }}>
          CEO Final Decision
        </span>
        {recCfg && (
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.12em',
            color: recCfg.color,
          }}>
            {recCfg.label}
          </span>
        )}
      </div>

      <div className="panel-body">
        {/* Confidence callout */}
        {confidence > 0 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '8px 12px',
            background: 'var(--bg-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            marginBottom: 14,
          }}>
            <span className="data-dim" style={{ fontSize: 10 }}>AGENT CONFIDENCE</span>
            <span style={{
              fontFamily: 'var(--mono)',
              fontSize: 18,
              fontWeight: 600,
              color: recCfg?.color ?? 'var(--amber)',
            }}>
              {(confidence * 100).toFixed(1)}%
            </span>
          </div>
        )}

        {/* Decision text */}
        <div style={{
          whiteSpace: 'pre-wrap',
          fontSize: 12,
          color: 'var(--text-1)',
          lineHeight: 1.7,
          maxHeight: 400,
          overflowY: 'auto',
          fontFamily: 'var(--mono)',
        }}>
          {decision}
        </div>

        {reasoning && (
          <div style={{
            marginTop: 14,
            paddingTop: 14,
            borderTop: '1px solid var(--border)',
            fontSize: 11,
            color: 'var(--text-2)',
            fontStyle: 'italic',
          }}>
            {reasoning}
          </div>
        )}
      </div>
    </div>
  )
}