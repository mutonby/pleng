import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Globe, Rocket } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import SitesPage from './pages/SitesPage'
import SiteDetailPage from './pages/SiteDetailPage'
import DeployPage from './pages/DeployPage'
import { cn } from './lib/utils'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/sites', label: 'Sites', icon: Globe },
  { path: '/deploy', label: 'Deploy', icon: Rocket },
]

export default function App() {
  const location = useLocation()

  return (
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
      </aside>

      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sites" element={<SitesPage />} />
          <Route path="/sites/:id" element={<SiteDetailPage />} />
          <Route path="/deploy" element={<DeployPage />} />
        </Routes>
      </main>
    </div>
  )
}
