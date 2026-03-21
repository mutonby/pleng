const BASE = '/api'

function getKey(): string | null {
  return localStorage.getItem('pleng_auth')
}

async function request(method: string, path: string, body?: unknown) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const key = getKey()
  if (key) headers['X-API-Key'] = key

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    localStorage.removeItem('pleng_auth')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  return res.json()
}

export const api = {
  get: (path: string) => request('GET', path),
  post: (path: string, body?: unknown) => request('POST', path, body),
}
