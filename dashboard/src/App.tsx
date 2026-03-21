import { useState } from 'react'
import { Routes, Route, Link, useLocation, Navigate } from 'react-router-dom'
import { LayoutDashboard, Globe } from 'lucide-react'
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

  if (location.pathname === '/login') {
    return <LoginPage />
  }

  return (
    <ProtectedRoute>
      <div className="flex h-screen">
        <aside className="w-52 bg-surface-800 border-r border-gray-700/50 flex flex-col">
          <div className="p-4 border-b border-gray-700/50">
            <h1 className="text-lg font-bold text-primary-400">Pleng</h1>
            <p className="text-xs text-gray-500">AI-Native PaaS</p>
          </div>
          <nav className="flex-1 p-2 space-y-1">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link key={path} to={path}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  location.pathname === path
                    ? 'bg-primary-600/20 text-primary-400'
                    : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'
                )}>
                <Icon size={18} />
                {label}
              </Link>
            ))}
          </nav>
          <div className="p-3 border-t border-gray-700/50">
            <button
              onClick={() => { localStorage.removeItem('pleng_auth'); window.location.href = '/login' }}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Logout
            </button>
          </div>
        </aside>

        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sites" element={<SitesPage />} />
            <Route path="/sites/:id" element={<SiteDetailPage />} />
          </Routes>
        </main>
      </div>
    </ProtectedRoute>
  )
}
