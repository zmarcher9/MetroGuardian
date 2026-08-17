import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/useAuth'

export default function ProtectedRoute(props: Readonly<{ children: ReactNode }>) {
  const { user, loading } = useAuth()

  if (loading) return <div className="px-4 py-16 text-center text-sm text-slate-400">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{props.children}</>
}
