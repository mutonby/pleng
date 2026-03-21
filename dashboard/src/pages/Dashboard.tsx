import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function Dashboard() {
  const [sites, setSites] = useState<any[]>([])

  useEffect(() => {
    api.get('/sites').then((d) => setSites(Array.isArray(d) ? d : [])).catch(() => {})
    // Auto-refresh every 10s
    const interval = setInterval(() => {
      api.get('/sites').then((d) => setSites(Array.isArray(d) ? d : [])).catch(() => {})
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const staging = sites.filter(s => s.status === 'staging').length
  const production = sites.filter(s => s.status === 'production').length
  const errors = sites.filter(s => s.status === 'error').length

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      <div className="grid grid-cols-4 gap-4">
        <Stat label="Total" value={sites.length} color="text-primary-400" />
        <Stat label="Staging" value={staging} color="text-yellow-400" />
        <Stat label="Production" value={production} color="text-green-400" />
        <Stat label="Errors" value={errors} color="text-red-400" />
      </div>

      <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
        <h3 className="font-semibold flex items-center gap-2 mb-3"><Globe size={16} /> Sites</h3>
        {sites.length === 0 ? (
          <p className="text-sm text-gray-500 py-4 text-center">
            No sites yet. Talk to the agent via Telegram to deploy something.
          </p>
        ) : (
          <div className="space-y-2">
            {sites.map((s: any) => {
              const domain = s.production_domain || s.staging_domain || ''
              const url = s.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''
              return (
                <Link key={s.id} to={`/sites/${s.id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-surface-900/50 hover:bg-surface-900 transition-colors">
                  <div className="flex items-center gap-3">
                    <span className={cn('w-2 h-2 rounded-full',
                      s.status === 'production' ? 'bg-green-400' :
                      s.status === 'staging' ? 'bg-yellow-400' :
                      s.status === 'error' ? 'bg-red-400' : 'bg-gray-400'
                    )} />
                    <div>
                      <p className="text-sm font-medium">{s.name}</p>
                      <p className="text-xs text-gray-500">{domain || 'deploying...'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-600">{formatDate(s.created_at)}</span>
                    <span className={cn('text-xs px-2 py-0.5 rounded-full', statusColors[s.status] || 'bg-gray-600')}>
                      {s.status}
                    </span>
                    {url && (
                      <a href={url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                        className="text-gray-500 hover:text-primary-400">
                        <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn('text-2xl font-bold', color)}>{value}</p>
    </div>
  )
}
