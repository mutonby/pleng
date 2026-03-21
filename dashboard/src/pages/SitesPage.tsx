import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Rocket } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function SitesPage() {
  const [sites, setSites] = useState<any[]>([])

  useEffect(() => {
    api.get('/sites').then((d) => setSites(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Sites</h2>
        <Link to="/deploy" className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm">
          <Rocket size={16} /> Deploy
        </Link>
      </div>

      {sites.length === 0 ? (
        <div className="bg-surface-800 rounded-xl p-8 border border-gray-700/50 text-center">
          <p className="text-gray-500 mb-3">No sites yet.</p>
          <Link to="/deploy" className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm">
            <Rocket size={16} /> Deploy
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sites.map((s: any) => {
            const domain = s.production_domain || s.staging_domain
            const url = s.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''
            return (
              <div key={s.id} className="bg-surface-800 rounded-xl border border-gray-700/50 hover:border-primary-500/30 transition-colors overflow-hidden">
                <div className={cn('h-1',
                  s.status === 'production' ? 'bg-green-500' :
                  s.status === 'staging' ? 'bg-yellow-500' :
                  s.status === 'error' ? 'bg-red-500' : 'bg-gray-500'
                )} />
                <div className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-semibold">{s.name}</h3>
                    <span className={cn('text-xs px-2 py-0.5 rounded-full', statusColors[s.status] || 'bg-gray-600')}>
                      {s.status}
                    </span>
                  </div>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary-400 hover:underline mb-2">
                      <ExternalLink size={12} /> {domain}
                    </a>
                  )}
                  <p className="text-xs text-gray-600">{s.deploy_mode} · {formatDate(s.created_at)}</p>
                  <Link to={`/sites/${s.id}`}
                    className="block mt-3 text-center py-1.5 bg-surface-900/50 hover:bg-surface-900 rounded-lg text-xs text-gray-400 hover:text-gray-200 transition-colors">
                    Details
                  </Link>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
