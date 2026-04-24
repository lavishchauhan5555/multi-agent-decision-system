// src/components/ConfidenceBar.jsx

function getColor(score) {
  if (score >= 0.85) return 'var(--green)'
  if (score >= 0.55) return 'var(--amber)'
  return 'var(--red)'
}

function getLabel(score) {
  if (score >= 0.85) return 'EXCELLENT'
  if (score >= 0.70) return 'GOOD'
  if (score >= 0.55) return 'MODERATE'
  if (score >= 0.40) return 'WEAK'
  return 'POOR'
}

export default function ConfidenceBar({ score = 0, best = 0, round = 0 }) {
  const pct     = Math.round(score * 100)
  const bestPct = Math.round(best * 100)
  const color   = getColor(score)

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-label">Confidence Meter</span>
        <span className="data-dim" style={{ marginLeft: 'auto', fontSize: 10 }}>
          ROUND {round}
        </span>
      </div>
      <div className="panel-body">

        {/* Score display */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
          <span style={{
            fontFamily: 'var(--mono)',
            fontSize: 36,
            fontWeight: 600,
            color,
            lineHeight: 1,
            transition: 'color 0.4s ease',
          }}>
            {pct}<span style={{ fontSize: 18, color: 'var(--text-2)' }}>%</span>
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: '0.15em',
              color,
              transition: 'color 0.4s ease',
            }}>
              {getLabel(score)}
            </span>
            <span className="data-dim" style={{ fontSize: 10 }}>
              BEST: {bestPct}%
            </span>
          </div>
        </div>

        {/* Main bar */}
        <div style={{
          height: 6,
          background: 'var(--bg-3)',
          borderRadius: 3,
          overflow: 'hidden',
          position: 'relative',
          marginBottom: 6,
        }}>
          {/* Best score ghost */}
          <div style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: `${bestPct}%`,
            background: 'var(--border-lit)',
            borderRadius: 3,
            transition: 'width 0.6s ease',
          }} />
          {/* Live score */}
          <div style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: `${pct}%`,
            background: color,
            borderRadius: 3,
            transition: 'width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.4s ease',
            boxShadow: `0 0 10px ${color}55`,
          }} />
        </div>

        {/* Threshold markers */}
        <div style={{ position: 'relative', height: 16 }}>
          {[40, 55, 70, 85].map(t => (
            <div key={t} style={{
              position: 'absolute',
              left: `${t}%`,
              top: 0,
              transform: 'translateX(-50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
            }}>
              <div style={{ width: 1, height: 4, background: 'var(--text-3)' }} />
              <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
                {t}
              </span>
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}