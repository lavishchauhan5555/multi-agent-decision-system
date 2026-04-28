import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider }    from './context/AuthContext'
import ProtectedRoute      from './components/ProtectedRoute'
import Home                from './pages/Home'
import Dashboard           from './pages/Dashboard'
import Login               from './pages/Login'
import Signup              from './pages/Signup'
import KnowledgeBrowser    from './pages/KnowledgeBrowser'
import History             from './pages/History'
import ServerHealth        from './pages/ServerHealth'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login"  element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          <Route path="/" element={
            <ProtectedRoute><Home /></ProtectedRoute>
          } />
          <Route path="/dashboard" element={
            <ProtectedRoute><Dashboard /></ProtectedRoute>
          } />
          <Route path="/knowledge" element={
            <ProtectedRoute><KnowledgeBrowser /></ProtectedRoute>
          } />
          <Route path="/history" element={
            <ProtectedRoute><History /></ProtectedRoute>
          } />
          <Route path="/server-health" element={
            <ProtectedRoute><ServerHealth /></ProtectedRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}