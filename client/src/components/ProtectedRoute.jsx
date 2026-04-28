import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-0)',
        color: 'var(--text-3)',
        fontFamily: 'var(--mono)',
        fontSize: 12,
      }}>
        <span className="cursor">Initializing system</span>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />

  return children
}