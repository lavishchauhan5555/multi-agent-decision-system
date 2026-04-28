// src/components/DecisionPanel.jsx

const REC_CONFIG = {
  PROCEED: {
    color: 'var(--green)',
    bg: 'var(--green-glow)',
    label: '✓ PROCEED',
  },
  'DO NOT PROCEED': {
    color: 'var(--red)',
    bg: 'var(--red-dim)',
    label: '✕ DO NOT PROCEED',
  },
  'CONDITIONAL PROCEED': {
    color: 'var(--amber)',
    bg: 'var(--amber-glow)',
    label: '◈ CONDITIONAL',
  },
}

function normalizeDecision(decision) {
  if (!decision) return null

  if (typeof decision === 'string') {
    return {
      recommendation: extractRecommendation(decision) ?? 'UNKNOWN',
      summary: decision,
      confidence: null,
    }
  }

  return {
    recommendation:
      decision.recommendation ??
      decision.decision ??
      extractRecommendation(JSON.stringify(decision)) ??
      'UNKNOWN',

    confidence:
      decision.confidence ??
      decision.confidence_score ??
      (decision.confidence_percent != null
        ? decision.confidence_percent / 100
        : null),

    summary:
      decision.summary ??
      decision.reasoning ??
      decision.reasoning_summary ??
      decision.final_summary ??
      '',

    raw: decision,
  }
}

function extractRecommendation(text) {
  if (!text || typeof text !== 'string') return null

  const upper = text.toUpperCase()

  if (upper.includes('DO NOT PROCEED')) return 'DO NOT PROCEED'
  if (upper.includes('CONDITIONAL PROCEED') || upper.includes('CONDITIONAL')) {
    return 'CONDITIONAL PROCEED'
  }
  if (upper.includes('PROCEED')) return 'PROCEED'

  return null
}

export default function DecisionPanel({ decision, confidence, reasoning }) {
  const normalized = normalizeDecision(decision)

  if (!normalized) return null

  const rec = normalized.recommendation
  const recCfg = REC_CONFIG[rec] ?? null

  const finalConfidence =
    normalized.confidence != null
      ? normalized.confidence
      : confidence

  return (
    <div
      className="panel animate-in"
      style={{ borderColor: recCfg?.color ?? 'var(--border)' }}
    >
      <div
        className="panel-header"
        style={{
          background: recCfg?.bg ?? 'var(--bg-2)',
          borderBottomColor: recCfg?.color ?? 'var(--border)',
          justifyContent: 'space-between',
        }}
      >
        <span
          className="panel-label"
          style={{ color: recCfg?.color ?? 'var(--text-2)' }}
        >
          CEO Final Decision
        </span>

        {recCfg && (
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: recCfg.color,
            }}
          >
            {recCfg.label}
          </span>
        )}
      </div>

      <div className="panel-body">
        {finalConfidence != null && finalConfidence > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 12px',
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              marginBottom: 14,
            }}
          >
            <span className="data-dim" style={{ fontSize: 10 }}>
              AGENT CONFIDENCE
            </span>

            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 18,
                fontWeight: 600,
                color: recCfg?.color ?? 'var(--amber)',
              }}
            >
              {(finalConfidence * 100).toFixed(1)}%
            </span>
          </div>
        )}

        <div
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: 12,
            color: 'var(--text-1)',
            lineHeight: 1.7,
            maxHeight: 400,
            overflowY: 'auto',
            fontFamily: 'var(--mono)',
          }}
        >
          <div>
            <div>
              Decision: {normalized.recommendation}
            </div>

            {finalConfidence != null && (
              <div>
                Confidence: {Math.round(finalConfidence * 100)}%
              </div>
            )}

            {normalized.summary && (
              <p>{normalized.summary}</p>
            )}

            {!normalized.summary && normalized.raw && (
              <pre style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(normalized.raw, null, 2)}
              </pre>
            )}
          </div>
        </div>

        {reasoning && (
          <div
            style={{
              marginTop: 14,
              paddingTop: 14,
              borderTop: '1px solid var(--border)',
              fontSize: 11,
              color: 'var(--text-2)',
              fontStyle: 'italic',
            }}
          >
            {reasoning}
          </div>
        )}
      </div>
    </div>
  )
}