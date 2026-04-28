import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Signup() {
  const { signup } = useAuth()
  const navigate   = useNavigate()
  const [name,     setName]     = useState('')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [confirm,  setConfirm]  = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  const handleSubmit = async () => {
    if (!name || !email || !password || loading) return
    if (password !== confirm) { setError('Passwords do not match'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
    setLoading(true)
    setError(null)
    try {
      await signup(email, password, name)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const strength = password.length === 0 ? null
    : password.length < 8   ? 'weak'
    : password.length < 12  ? 'medium'
    : 'strong'

  const strengthColor = { weak: 'var(--red)', medium: 'var(--amber)', strong: 'var(--green)' }

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
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `
          linear-gradient(rgba(245,158,11,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(245,158,11,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
      }} />

      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 420 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontSize: 10,
            letterSpacing: '0.4em',
            color: 'var(--amber)',
            textTransform: 'uppercase',
            marginBottom: 10,
          }}>◈ Autonomous Decision Lab</div>
          <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text-0)' }}>
            VANTAGE
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
            request operator access
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-label">New Operator</span>
            <span className="data-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>REGISTER</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>OPERATOR NAME</label>
              <input
                className="input"
                placeholder="Jane Chen"
                value={name}
                onChange={e => setName(e.target.value)}
                autoFocus
                style={{ padding: '10px 12px' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>EMAIL</label>
              <input
                className="input"
                type="email"
                placeholder="operator@lab.ai"
                value={email}
                onChange={e => setEmail(e.target.value)}
                style={{ padding: '10px 12px' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>PASSWORD</label>
              <input
                className="input"
                type="password"
                placeholder="min. 8 characters"
                value={password}
                onChange={e => setPassword(e.target.value)}
                style={{ padding: '10px 12px' }}
              />
              {strength && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                  <div style={{ flex: 1, height: 2, background: 'var(--bg-3)', borderRadius: 2 }}>
                    <div style={{
                      height: '100%',
                      width: strength === 'weak' ? '33%' : strength === 'medium' ? '66%' : '100%',
                      background: strengthColor[strength],
                      borderRadius: 2,
                      transition: 'all 0.3s',
                    }} />
                  </div>
                  <span style={{ fontSize: 10, color: strengthColor[strength], textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    {strength}
                  </span>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="data-dim" style={{ fontSize: 10 }}>CONFIRM PASSWORD</label>
              <input
                className="input"
                type="password"
                placeholder="repeat password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                style={{
                  padding: '10px 12px',
                  borderColor: confirm && confirm !== password ? 'var(--red)' : undefined,
                }}
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
              }}>✕ {error}</div>
            )}

            <button
              className="btn btn-primary"
              disabled={!name || !email || !password || !confirm || loading}
              onClick={handleSubmit}
              style={{ width: '100%', padding: '10px', marginTop: 4 }}
            >
              {loading ? '◉ creating account…' : '▶ initialize operator'}
            </button>

            <div style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
              Already have access?{' '}
              <Link to="/login" style={{ color: 'var(--amber)', textDecoration: 'none' }}>
                sign in →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}