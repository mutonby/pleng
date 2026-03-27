import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      const data = await res.json()
      if (data.api_key) {
        localStorage.setItem('pleng_auth', data.api_key)
        navigate('/')
      } else {
        setError(data.detail || 'Wrong password')
      }
    } catch {
      setError('Connection failed')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-900 relative">
      {/* Background glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-primary-400/5 blur-[120px] pointer-events-none" />

      <form onSubmit={handleSubmit} className="relative bg-surface-800 p-8 rounded-xl w-80 space-y-5 border border-border-bright shadow-glow-sm">
        <div className="text-center">
          <h1 className="text-2xl font-mono font-extrabold tracking-tight text-primary-400">pleng</h1>
          <p className="text-[0.7rem] font-mono uppercase tracking-[0.15em] text-gray-600 mt-1">Dashboard Access</p>
        </div>
        {error && <p className="text-red-400 text-xs font-mono text-center">{error}</p>}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full px-3 py-2.5 bg-surface-900 border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-primary-500 transition-colors"
        />
        <button type="submit"
          className="w-full py-2.5 bg-primary-400 hover:bg-primary-300 text-surface-900 rounded-md text-sm font-mono font-bold tracking-wide transition-all duration-200 hover:-translate-y-0.5 hover:shadow-glow">
          Login
        </button>
      </form>
    </div>
  )
}
