import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate  = useNavigate()
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  const handleSubmit = async e => {
    e?.preventDefault?.()
    if (!email || !password || loading) return
    setLoading(true)
    setError(null)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleKey = e => {
    if (e.key === 'Enter') handleSubmit()
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-0)',
      padding: '24px',
    }}>
      {/* Grid background decoration */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `
          linear-gradient(rgba(245,158,11,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(245,158,11,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
      }} />

      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 400 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontSize: 10,
            letterSpacing: '0.4em',
            color: 'var(--amber)',
            textTransform: 'uppercase',
            marginBottom: 10,
          }}>◈ Autonomous Decision Lab</div>
          <div style={{
            fontSize: 32,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            color: 'var(--text-0)',
          }}>VANTAGE</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
            multi-agent decision system
          </div>
        </div>

        {/* Card */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-label">Authentication</span>
            <span className="data-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>SECURE SESSION</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>EMAIL</label>
              <input
                className="input"
                type="email"
                placeholder="operator@lab.ai"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={handleKey}
                autoFocus
                style={{ padding: '10px 12px' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>PASSWORD</label>
              <input
                className="input"
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={handleKey}
                style={{ padding: '10px 12px' }}
              />
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

            <button
              className="btn btn-primary"
              disabled={!email || !password || loading}
              onClick={handleSubmit}
              style={{ width: '100%', padding: '10px', marginTop: 4 }}
            >
              {loading ? '◉ authenticating…' : '▶ access system'}
            </button>

            <div style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
              No account?{' '}
              <Link to="/signup" style={{ color: 'var(--amber)', textDecoration: 'none' }}>
                request access →
              </Link>
            </div>
          </div>
        </div>

        {/* Demo hint */}
        <div style={{
          marginTop: 16,
          padding: '8px 14px',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          fontSize: 10,
          color: 'var(--text-3)',
          fontFamily: 'var(--mono)',
          display: 'flex',
          gap: 8,
          alignItems: 'center',
        }}>
          <span style={{ color: 'var(--amber)' }}>◈</span>
          <span>demo: demo@vantage.ai / password</span>
        </div>
      </div>
    </div>
  )
}