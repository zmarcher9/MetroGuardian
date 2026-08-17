import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import { useAuth } from '../lib/useAuth'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export default function SignupPage() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await signup(email, password)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-16">
      <Card floating>
        <h1 className="text-emboss mb-4 text-lg font-bold text-text">Sign up</h1>
        <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
          <Input
            id="signup-email"
            label="Email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <div>
            <Input
              id="signup-password"
              label="Password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <span className="mt-1.5 block text-xs text-text-muted">At least 8 characters, with a letter and a digit.</span>
          </div>
          {error ? (
            <div className="rounded-lg border border-accent bg-[var(--accent-tint)] p-3 text-sm text-text">{error}</div>
          ) : null}
          <Button type="submit" disabled={loading}>
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {loading ? 'Signing up…' : 'Sign up'}
          </Button>
        </form>
      </Card>
      <div className="text-center text-sm text-text-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-text underline">
          Log in
        </Link>
      </div>
    </div>
  )
}
