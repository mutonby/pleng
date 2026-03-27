import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function SitesPage() {
  const [sites, setSites] = useState<any[]>([])

  useEffect(() => {
    api.get('/sites').then((d) => setSites(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-display font-black tracking-tight">Sites</h2>

      {sites.length === 0 ? (
        <div className="bg-surface-800 rounded-xl p-8 border border-border text-center">
          <p className="text-gray-600 font-mono text-sm">No sites yet. Talk to the agent via Telegram to deploy something.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sites.map((s: any) => {
            const domain = s.production_domain || s.staging_domain
            const url = s.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''
            return (
              <div key={s.id} className="bg-surface-800 rounded-xl border border-border hover:border-border-bright hover:-translate-y-1 transition-all duration-200 overflow-hidden group">
                <div className={cn('h-0.5',
                  s.status === 'production' ? 'bg-green-500' :
                  s.status === 'staging' ? 'bg-yellow-500' :
                  s.status === 'error' ? 'bg-red-500' : 'bg-gray-600'
                )} />
                <div className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-semibold text-gray-100">{s.name}</h3>
                    <span className={cn('text-[0.65rem] font-mono px-2 py-0.5 rounded-full', statusColors[s.status] || 'bg-gray-700')}>
                      {s.status}
                    </span>
                  </div>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 font-mono mb-2 transition-colors">
                      <ExternalLink size={11} /> {domain}
                    </a>
                  )}
                  <p className="text-[0.65rem] font-mono text-gray-600">{s.deploy_mode} · {formatDate(s.created_at)}</p>
                  <Link to={`/sites/${s.id}`}
                    className="block mt-3 text-center py-1.5 bg-surface-900/50 hover:bg-primary-500/10 border border-border hover:border-primary-500/30 rounded-lg text-xs font-mono text-gray-500 hover:text-primary-400 transition-all duration-200">
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
