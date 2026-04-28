import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import useRunStore from '../store/useRunStore'

const STATUS_COLOR = {
  done:    'var(--green)',
  running: 'var(--amber)',
  error:   'var(--red)',
  idle:    'var(--text-3)',
}

export default function History() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const launch   = useRunStore(s => s.launch)
  const setQuery = useRunStore(s => s.setQuery)

  const [sessions,  setSessions]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [deleting,  setDeleting]  = useState(null)
  const [filter,    setFilter]    = useState('')
  const [sortBy,    setSortBy]    = useState('date')

  const load = () => {
    setLoading(true)
    authFetch('/api/query/history')
      .then(r => r.json())
      .then(setSessions)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this session?')) return
    setDeleting(id)
    try {
      await authFetch(`/api/session/${id}`, { method: 'DELETE' })
      setSessions(prev => prev.filter(s => s._id !== id))
    } catch (e) {
      setError(e.message)
    } finally {
      setDeleting(null)
    }
  }

  const handleRerun = async (session) => {
    setQuery(session.query)
    await launch({ query: session.query, maxRounds: session.maxRounds || 3, threshold: session.threshold || 0.85 })
    navigate('/dashboard')
  }

  const filtered = sessions
    .filter(s => !filter || s.query?.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'score') return (b.confidenceScore || 0) - (a.confidenceScore || 0)
      return new Date(b.createdAt) - new Date(a.createdAt)
    })

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-0)' }}>
      {/* Topbar */}
      <div className="topbar">
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub">session history</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn" style={{ padding: '6px 14px', fontSize: 11 }} onClick={() => navigate('/')}>
            + new run
          </button>
        </div>
      </div>

      <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Controls */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            className="input"
            placeholder="filter by query…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            style={{ flex: 1, minWidth: 200, padding: '8px 12px', fontSize: 11 }}
          />
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            style={{
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-0)',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              padding: '8px 12px',
              cursor: 'pointer',
            }}
          >
            <option value="date">Sort: Latest</option>
            <option value="score">Sort: Top Score</option>
          </select>
          <button className="btn" style={{ padding: '8px 14px', fontSize: 11 }} onClick={load}>
            ↻ refresh
          </button>
        </div>

        {/* Stats */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            { label: 'TOTAL SESSIONS', value: sessions.length },
            { label: 'COMPLETED', value: sessions.filter(s => s.status === 'done').length },
            { label: 'AVG SCORE', value: sessions.length ? `${(sessions.reduce((a, s) => a + (s.confidenceScore || 0), 0) / sessions.length * 100).toFixed(0)}%` : '—' },
          ].map(stat => (
            <div key={stat.label} className="panel" style={{ flex: '1 1 120px' }}>
              <div className="panel-body" style={{ padding: '12px 16px' }}>
                <div className="data-dim" style={{ fontSize: 9, marginBottom: 4 }}>{stat.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-0)', fontFamily: 'var(--mono)' }}>
                  {stat.value}
                </div>
              </div>
            </div>
          ))}
        </div>

        {error && (
          <div style={{ padding: '10px', background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--red)' }}>
            ✕ {error}
          </div>
        )}

        {/* Session list */}
        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">
            <span className="panel-label">Sessions</span>
            <span className="data-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>
              {filtered.length} results
            </span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                <span className="cursor">Loading sessions</span>
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                {filter ? 'No sessions match your filter.' : 'No sessions yet. Launch your first run!'}
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'var(--mono)' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {['STATUS', 'QUERY', 'SCORE', 'ROUNDS', 'DECISION', 'DATE', 'ACTIONS'].map(h => (
                        <th key={h} style={{
                          padding: '8px 14px', textAlign: 'left',
                          color: 'var(--text-3)', fontSize: 10, letterSpacing: '0.12em', fontWeight: 600,
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(session => (
                      <tr key={session._id}
                        style={{ borderBottom: '1px solid var(--border)', transition: 'background 0.1s' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-2)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 5,
                            color: STATUS_COLOR[session.status] || 'var(--text-3)',
                            fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                          }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: STATUS_COLOR[session.status] || 'var(--text-3)', display: 'inline-block' }} />
                            {(session.status || 'unknown').toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-1)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {session.query}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{
                            color: session.confidenceScore >= 0.85 ? 'var(--green)'
                              : session.confidenceScore >= 0.7  ? 'var(--amber)' : 'var(--red)',
                            fontWeight: 700,
                          }}>
                            {session.confidenceScore ? `${(session.confidenceScore * 100).toFixed(0)}%` : '—'}
                          </span>
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-3)' }}>
                          {session.currentRound || '—'}
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-2)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {session.finalDecision?.recommendation || '—'}
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-3)', fontSize: 10 }}>
                          {session.createdAt ? new Date(session.createdAt).toLocaleDateString() : '—'}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              className="btn"
                              style={{ padding: '4px 10px', fontSize: 10 }}
                              onClick={() => handleRerun(session)}
                            >
                              ↺ rerun
                            </button>
                            <button
                              className="btn"
                              style={{ padding: '4px 10px', fontSize: 10, color: 'var(--red)', borderColor: 'var(--red)' }}
                              onClick={() => handleDelete(session._id)}
                              disabled={deleting === session._id}
                            >
                              {deleting === session._id ? '…' : '✕'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}