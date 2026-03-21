import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Play, Square, RefreshCw, Trash2, ExternalLink, ArrowUpCircle } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function SiteDetailPage() {
  const { id } = useParams()
  const [site, setSite] = useState<any>(null)
  const [logs, setLogs] = useState('')
  const [buildLogs, setBuildLogs] = useState<any[]>([])
  const [tab, setTab] = useState('overview')
  const [loading, setLoading] = useState('')
  const [promoteDomain, setPromoteDomain] = useState('')

  useEffect(() => {
    if (!id) return
    api.get(`/sites/${id}`).then(setSite).catch(() => {})
  }, [id])

  useEffect(() => {
    if (!id || tab !== 'logs') return
    api.get(`/sites/${id}/logs?lines=200`).then(d => setLogs(d.logs || '')).catch(() => {})
  }, [id, tab])

  useEffect(() => {
    if (!id || tab !== 'build-log') return
    api.get(`/sites/${id}/build-logs`).then(d => setBuildLogs(Array.isArray(d) ? d : [])).catch(() => {})
  }, [id, tab])

  async function action(act: string) {
    if (!id) return
    setLoading(act)
    await api.post(`/sites/${id}/${act}`)
    const updated = await api.get(`/sites/${id}`)
    setSite(updated)
    setLoading('')
  }

  async function promote() {
    if (!id || !promoteDomain.trim()) return
    setLoading('promote')
    await api.post(`/sites/${id}/promote`, { domain: promoteDomain.trim() })
    const updated = await api.get(`/sites/${id}`)
    setSite(updated)
    setLoading('')
    setPromoteDomain('')
  }

  if (!site) return <p className="text-gray-500">Loading...</p>

  const domain = site.production_domain || site.staging_domain
  const url = site.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{site.name}</h2>
          {url && (
            <a href={url} target="_blank" rel="noreferrer" className="text-sm text-primary-400 hover:underline flex items-center gap-1">
              <ExternalLink size={14} /> {domain}
            </a>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={cn('text-xs px-3 py-1 rounded-full', statusColors[site.status] || 'bg-gray-600')}>
            {site.status}
          </span>
          {['staging', 'production'].includes(site.status) && (
            <button onClick={() => action('stop')} disabled={!!loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-xs">
              <Square size={14} /> Stop
            </button>
          )}
          {site.status === 'stopped' && (
            <button onClick={() => action('restart')} disabled={!!loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg text-xs">
              <Play size={14} /> Start
            </button>
          )}
          <button onClick={() => action('restart')} disabled={!!loading}
            className="flex items-center gap-1 px-3 py-1.5 bg-surface-900/50 hover:bg-surface-900 rounded-lg text-xs">
            <RefreshCw size={14} /> Restart
          </button>
        </div>
      </div>

      <div className="flex gap-1 bg-surface-800 rounded-lg p-1">
        {['overview', 'logs', 'build-log'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={cn('px-3 py-1.5 rounded-md text-xs capitalize transition-colors',
              tab === t ? 'bg-primary-600 text-white' : 'text-gray-400 hover:text-gray-200')}>
            {t.replace('-', ' ')}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Info label="Status" value={site.status} />
            <Info label="Mode" value={site.deploy_mode} />
            <Info label="Staging URL" value={site.staging_domain ? `http://${site.staging_domain}` : '-'} link={site.staging_domain ? `http://${site.staging_domain}` : undefined} />
            <Info label="Production URL" value={site.production_domain ? `https://${site.production_domain}` : '-'} link={site.production_domain ? `https://${site.production_domain}` : undefined} />
            <Info label="GitHub" value={site.github_url || '-'} link={site.github_url} />
            <Info label="Created" value={formatDate(site.created_at)} />
            <Info label="Deployed" value={formatDate(site.deployed_at)} />
            <Info label="AI Cost" value={`$${(site.ai_cost || 0).toFixed(2)}`} />
          </div>

          {/* Promote section */}
          {site.status === 'staging' && (
            <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <ArrowUpCircle size={16} className="text-green-400" /> Promote to Production
              </h4>
              <p className="text-xs text-gray-500 mb-3">Add a custom domain with automatic SSL (Let's Encrypt).</p>
              <div className="flex gap-2">
                <input
                  type="text" value={promoteDomain} onChange={e => setPromoteDomain(e.target.value)}
                  placeholder="app.example.com"
                  className="flex-1 px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500"
                />
                <button onClick={promote} disabled={!!loading || !promoteDomain.trim()}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 rounded-lg text-sm transition-colors">
                  {loading === 'promote' ? '...' : 'Promote'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-surface-800 rounded-xl border border-gray-700/50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700/50">
            <span className="text-xs text-gray-500">Docker Logs</span>
            <button onClick={() => api.get(`/sites/${id}/logs?lines=200`).then(d => setLogs(d.logs || ''))}
              className="text-xs text-primary-400 hover:underline">Refresh</button>
          </div>
          <pre className="p-4 text-xs font-mono text-gray-400 overflow-auto max-h-[600px] whitespace-pre-wrap">
            {logs || 'No logs'}
          </pre>
        </div>
      )}

      {tab === 'build-log' && (
        <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50 max-h-96 overflow-auto">
          {buildLogs.length === 0 ? (
            <p className="text-gray-500 text-sm">No build logs</p>
          ) : (
            <div className="space-y-1 font-mono text-xs">
              {buildLogs.map((l: any) => (
                <div key={l.id} className={cn('py-0.5', l.level === 'error' ? 'text-red-400' : 'text-gray-400')}>
                  <span className="text-gray-600">{l.created_at?.slice(11, 19)}</span> {l.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Info({ label, value, link }: { label: string; value: string; link?: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-3 border border-gray-700/50">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {link ? (
        <a href={link} target="_blank" rel="noreferrer" className="text-sm text-primary-400 hover:underline break-all">{value}</a>
      ) : (
        <p className="text-sm break-all">{value || '-'}</p>
      )}
    </div>
  )
}
