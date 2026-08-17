import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/useAuth'
import { Led } from './ui/Led'

export default function ProtectedRoute(props: Readonly<{ children: ReactNode }>) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex justify-center px-4 py-16">
        <Led status="connecting" label="Loading…" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{props.children}</>
}
