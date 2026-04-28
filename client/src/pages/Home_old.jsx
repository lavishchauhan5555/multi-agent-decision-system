// src/pages/Home.jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useRunStore from '../store/useRunStore'

const EXAMPLES = [
  'AI-powered resume builder for technical professionals',
  'B2B SaaS platform for construction project management',
  'Sustainable food delivery marketplace for tier-2 cities',
]

export default function Home() {
  const navigate   = useNavigate()
  const launch     = useRunStore(s => s.launch)
  const setQuery   = useRunStore(s => s.setQuery)

  const [query,     setLocalQuery]  = useState('')
  const [maxRounds, setMaxRounds]   = useState(3)
  const [threshold, setThreshold]   = useState(0.85)
  const [loading,   setLoading]     = useState(false)
  const [error,     setError]       = useState(null)

  const handleSubmit = async () => {
    if (!query.trim() || loading) return
    setLoading(true)
    setError(null)
    setQuery(query)
    try {
      await launch({ query: query.trim(), maxRounds, threshold })
      navigate('/dashboard')
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* Top bar */}
      <div className="topbar">
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub">multi-agent decision system</span>
        <div className="topbar-dot" />
      </div>

      {/* Hero */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '60px 24px',
      }}>

        {/* Wordmark */}
        <div style={{ textAlign: 'center', marginBottom: 52 }}>
          <div style={{
            fontSize: 11,
            letterSpacing: '0.4em',
            color: 'var(--amber)',
            textTransform: 'uppercase',
            marginBottom: 14,
          }}>
            ◈ Autonomous Business Intelligence
          </div>
          <h1 style={{
            fontSize: 'clamp(28px, 5vw, 48px)',
            fontWeight: 600,
            letterSpacing: '-0.03em',
            color: 'var(--text-0)',
            lineHeight: 1.15,
          }}>
            Submit a business idea.
            <br />
            <span style={{ color: 'var(--amber)' }}>Let the agents decide.</span>
          </h1>
        </div>

        {/* Input card */}
        <div style={{ width: '100%', maxWidth: 680 }}>
          <div className="panel">
            <div className="panel-header">
              <span className="panel-label">Mission Brief</span>
              <span className="data-dim" style={{ marginLeft: 'auto', fontSize: 10 }}>
                ⌘+ENTER to launch
              </span>
            </div>
            <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

              <textarea
                className="input"
                rows={4}
                placeholder="Describe the business idea to evaluate…"
                value={query}
                onChange={e => setLocalQuery(e.target.value)}
                onKeyDown={handleKey}
                autoFocus
              />

              {/* Config row */}
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span className="data-dim" style={{ fontSize: 10 }}>MAX ROUNDS</span>
                  <select
                    value={maxRounds}
                    onChange={e => setMaxRounds(Number(e.target.value))}
                    style={{
                      background: 'var(--bg-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--text-0)',
                      fontFamily: 'var(--mono)',
                      fontSize: 12,
                      padding: '6px 10px',
                      cursor: 'pointer',
                      outline: 'none',
                    }}
                  >
                    {[1, 2, 3, 4, 5].map(n => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </label>

                <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span className="data-dim" style={{ fontSize: 10 }}>THRESHOLD</span>
                  <select
                    value={threshold}
                    onChange={e => setThreshold(Number(e.target.value))}
                    style={{
                      background: 'var(--bg-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--text-0)',
                      fontFamily: 'var(--mono)',
                      fontSize: 12,
                      padding: '6px 10px',
                      cursor: 'pointer',
                      outline: 'none',
                    }}
                  >
                    {[0.70, 0.75, 0.80, 0.85, 0.90].map(t => (
                      <option key={t} value={t}>{(t * 100).toFixed(0)}%</option>
                    ))}
                  </select>
                </label>

                <button
                  className="btn btn-primary"
                  style={{ marginLeft: 'auto', minWidth: 120 }}
                  disabled={!query.trim() || loading}
                  onClick={handleSubmit}
                >
                  {loading ? '◉ launching…' : '▶ launch run'}
                </button>
              </div>

              {error && (
                <div style={{
                  padding: '8px 12px',
                  background: 'var(--red-dim)',
                  border: '1px solid var(--red)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 11,
                  color: 'var(--red)',
                }}>
                  ✕ {error}
                </div>
              )}
            </div>
          </div>

          {/* Examples */}
          <div style={{ marginTop: 20 }}>
            <div className="data-dim" style={{ fontSize: 10, marginBottom: 8 }}>
              EXAMPLE QUERIES
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {EXAMPLES.map(ex => (
                <button
                  key={ex}
                  onClick={() => setLocalQuery(ex)}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-2)',
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    padding: '7px 12px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => {
                    e.target.style.borderColor = 'var(--border-lit)'
                    e.target.style.color = 'var(--text-1)'
                  }}
                  onMouseLeave={e => {
                    e.target.style.borderColor = 'var(--border)'
                    e.target.style.color = 'var(--text-2)'
                  }}
                >
                  ↳ {ex}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}