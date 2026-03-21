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
    <div className="min-h-screen flex items-center justify-center bg-surface-900">
      <form onSubmit={handleSubmit} className="bg-surface-800 p-8 rounded-xl w-80 space-y-4">
        <h1 className="text-xl font-bold text-primary-400 text-center">Pleng</h1>
        <p className="text-xs text-gray-500 text-center">Dashboard login</p>
        {error && <p className="text-red-400 text-sm text-center">{error}</p>}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500"
        />
        <button type="submit"
          className="w-full py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm font-medium transition-colors">
          Login
        </button>
      </form>
    </div>
  )
}
