import { useState, useEffect } from 'react'
import { Routes, Route, Link, useLocation, Navigate } from 'react-router-dom'
import { LayoutDashboard, Globe, MessageCircle } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import SitesPage from './pages/SitesPage'
import SiteDetailPage from './pages/SiteDetailPage'
import LoginPage from './pages/LoginPage'
import { cn } from './lib/utils'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/sites', label: 'Sites', icon: Globe },
]

function isAuthenticated() {
  return !!localStorage.getItem('pleng_auth')
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) return <Navigate to="/login" />
  return <>{children}</>
}

export default function App() {
  const location = useLocation()
  const [setup, setSetup] = useState<any>(null)

  useEffect(() => {
    fetch('/api/setup-status').then(r => r.json()).then(setSetup).catch(() => {})
  }, [])

  if (location.pathname === '/login') {
    return <LoginPage />
  }

  const botName = setup?.telegram_bot || ''

  return (
    <ProtectedRoute>
      <div className="flex h-screen">
        <aside className="w-52 bg-surface-850/80 backdrop-blur-xl border-r border-border flex flex-col">
          <div className="p-4 border-b border-border">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-mono font-extrabold tracking-tight text-primary-400">pleng</h1>
              <span className="w-2 h-2 rounded-full bg-primary-400 animate-pulse-dot" />
            </div>
            <p className="text-[0.65rem] font-mono uppercase tracking-[0.15em] text-gray-500 mt-0.5">AI Platform Engineer</p>
          </div>
          <nav className="flex-1 p-2 space-y-1">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link key={path} to={path}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-mono transition-all duration-200',
                  location.pathname === path
                    ? 'bg-primary-500/15 text-primary-400 border border-primary-500/20'
                    : 'text-gray-500 hover:bg-surface-700/50 hover:text-gray-300 border border-transparent'
                )}>
                <Icon size={16} />
                {label}
              </Link>
            ))}
          </nav>

          {botName && (
            <div className="p-3 border-t border-border">
              <a href={`https://t.me/${botName}`} target="_blank" rel="noreferrer"
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono text-primary-400/70 hover:text-primary-400 hover:bg-primary-500/10 transition-all duration-200">
                <MessageCircle size={14} />
                @{botName}
              </a>
            </div>
          )}

          <div className="p-3 border-t border-border">
            <button
              onClick={() => { localStorage.removeItem('pleng_auth'); window.location.href = '/login' }}
              className="text-[0.7rem] font-mono uppercase tracking-wider text-gray-600 hover:text-gray-400 transition-colors"
            >
              Logout
            </button>
          </div>
        </aside>

        <main className="flex-1 overflow-auto p-6 bg-surface-900">
          <Routes>
            <Route path="/" element={<Dashboard setup={setup} />} />
            <Route path="/sites" element={<SitesPage />} />
            <Route path="/sites/:id" element={<SiteDetailPage />} />
          </Routes>
        </main>
      </div>
    </ProtectedRoute>
  )
}
