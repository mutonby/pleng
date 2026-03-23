import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ExternalLink, ArrowUpCircle, ArrowLeft, Box, Clock, HardDrive } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function SiteDetailPage() {
  const { id } = useParams()
  const [site, setSite] = useState<any>(null)
  const [logs, setLogs] = useState('')
  const [buildLogs, setBuildLogs] = useState<any[]>([])
  const [containers, setContainers] = useState<any[]>([])
  const [analytics, setAnalytics] = useState<any>(null)
  const [tab, setTab] = useState('overview')
  const [promoteDomain, setPromoteDomain] = useState('')
  const [promoting, setPromoting] = useState(false)

  const refreshSite = useCallback(() => {
    if (!id) return
    api.get(`/sites/${id}`).then(setSite).catch(() => {})
    api.get(`/sites/${id}/containers`).then(d => setContainers(Array.isArray(d) ? d : [])).catch(() => {})
  }, [id])

  useEffect(() => {
    refreshSite()
    const interval = setInterval(refreshSite, 8000)
    return () => clearInterval(interval)
  }, [refreshSite])

  useEffect(() => {
    if (!id || tab !== 'logs') return
    const fetchLogs = () => api.get(`/sites/${id}/logs?lines=200`).then(d => setLogs(d.logs || '')).catch(() => {})
    fetchLogs()
    const interval = setInterval(fetchLogs, 5000)
    return () => clearInterval(interval)
  }, [id, tab])

  useEffect(() => {
    if (!id || tab !== 'build-log') return
    api.get(`/sites/${id}/build-logs`).then(d => setBuildLogs(Array.isArray(d) ? d : [])).catch(() => {})
  }, [id, tab])

  useEffect(() => {
    if (!id || tab !== 'analytics') return
    api.get(`/sites/${id}/analytics?period=7d`).then(setAnalytics).catch(() => {})
  }, [id, tab])

  async function promote() {
    if (!id || !promoteDomain.trim()) return
    setPromoting(true)
    await api.post(`/sites/${id}/promote`, { domain: promoteDomain.trim() })
    refreshSite()
    setPromoting(false)
    setPromoteDomain('')
  }

  if (!site) return <p className="text-gray-500">Loading...</p>

  const domain = site.production_domain || site.staging_domain
  const url = site.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''

  return (
    <div className="space-y-4">
      {/* Back + Header */}
      <Link to="/sites" className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
        <ArrowLeft size={14} /> Back to sites
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{site.name}</h2>
            <span className={cn('text-xs px-3 py-1 rounded-full', statusColors[site.status] || 'bg-gray-600')}>
              {site.status}
            </span>
          </div>
          {url && (
            <a href={url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 mt-2 px-4 py-2 bg-primary-600/10 border border-primary-500/30 rounded-lg text-primary-400 hover:bg-primary-600/20 transition-colors">
              <ExternalLink size={16} />
              <span className="text-sm font-medium">{url}</span>
            </a>
          )}
        </div>
      </div>

      {/* Containers status */}
      {containers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {containers.map((c: any, i: number) => (
            <div key={i} className="bg-surface-800 rounded-lg p-3 border border-gray-700/50">
              <div className="flex items-center gap-2 mb-2">
                <Box size={14} className={c.State === 'running' ? 'text-green-400' : 'text-red-400'} />
                <span className="text-sm font-medium">{c.Name || c.Service || '?'}</span>
              </div>
              <div className="space-y-1 text-xs text-gray-500">
                <div className="flex items-center gap-1">
                  <span className={cn('w-1.5 h-1.5 rounded-full', c.State === 'running' ? 'bg-green-400' : 'bg-red-400')} />
                  {c.State || '?'}
                </div>
                {c.Image && <div className="flex items-center gap-1"><HardDrive size={10} /> {c.Image}</div>}
                {c.Status && <div className="flex items-center gap-1"><Clock size={10} /> {c.Status}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-800 rounded-lg p-1">
        {['overview', 'analytics', 'logs', 'build-log'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={cn('px-3 py-1.5 rounded-md text-xs capitalize transition-colors',
              tab === t ? 'bg-primary-600 text-white' : 'text-gray-400 hover:text-gray-200')}>
            {t === 'logs' ? 'Docker Logs' : t === 'build-log' ? 'Build Log' : t === 'analytics' ? 'Analytics' : 'Overview'}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Info label="Status" value={site.status} />
            <Info label="Mode" value={site.deploy_mode} />
            <Info label="Created" value={formatDate(site.created_at)} />
            <Info label="Last deploy" value={formatDate(site.deployed_at)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Info label="Staging URL" value={site.staging_domain ? `http://${site.staging_domain}` : '-'} link={site.staging_domain ? `http://${site.staging_domain}` : undefined} />
            <Info label="Production URL" value={site.production_domain ? `https://${site.production_domain}` : '-'} link={site.production_domain ? `https://${site.production_domain}` : undefined} />
          </div>

          {site.github_url && (
            <Info label="Repository" value={site.github_url} link={site.github_url} />
          )}

          {/* Promote section */}
          {site.status === 'staging' && (
            <div className="bg-surface-800 rounded-xl p-4 border border-green-500/20">
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <ArrowUpCircle size={16} className="text-green-400" /> Promote to Production
              </h4>
              <p className="text-xs text-gray-500 mb-3">Add a custom domain. SSL certificate via Let's Encrypt.</p>
              <div className="flex gap-2">
                <input
                  type="text" value={promoteDomain} onChange={e => setPromoteDomain(e.target.value)}
                  placeholder="app.example.com"
                  className="flex-1 px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-green-500"
                />
                <button onClick={promote} disabled={promoting || !promoteDomain.trim()}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 rounded-lg text-sm transition-colors">
                  {promoting ? '...' : 'Promote'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'analytics' && (
        <div className="space-y-4">
          {!analytics || !analytics.stats?.pageviews ? (
            <div className="bg-surface-800 rounded-xl p-6 border border-gray-700/50 text-center">
              <p className="text-gray-500 text-sm">No traffic data yet.</p>
              <p className="text-gray-600 text-xs mt-1">Analytics are collected from Traefik access logs. Data appears after the site receives traffic.</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard label="Pageviews" value={analytics.stats.pageviews.toLocaleString()} />
                <StatCard label="Visitors" value={analytics.stats.visitors.toLocaleString()} />
                <StatCard label="Avg Response" value={`${analytics.stats.avg_response_ms}ms`} />
                <StatCard label="Errors (5xx)" value={analytics.stats.errors.toString()} color={analytics.stats.errors > 0 ? 'text-red-400' : undefined} />
              </div>

              {analytics.top_pages?.length > 0 && (
                <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
                  <h4 className="text-sm font-medium mb-3">Top Pages</h4>
                  <div className="space-y-1">
                    {analytics.top_pages.map((p: any) => (
                      <div key={p.path} className="flex justify-between text-xs p-2 bg-surface-900/50 rounded">
                        <span className="text-gray-300 font-mono">{p.path}</span>
                        <span className="text-gray-500">{p.views} views · {p.visitors} visitors</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analytics.top_sources?.length > 0 && (
                <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
                  <h4 className="text-sm font-medium mb-3">Top Sources</h4>
                  <div className="space-y-1">
                    {analytics.top_sources.map((s: any) => (
                      <div key={s.source} className="flex justify-between text-xs p-2 bg-surface-900/50 rounded">
                        <span className="text-gray-300">{s.source}</span>
                        <span className="text-gray-500">{s.visitors} visitors</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analytics.daily?.length > 0 && (
                <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50">
                  <h4 className="text-sm font-medium mb-3">Daily Traffic</h4>
                  <div className="space-y-1">
                    {analytics.daily.map((d: any) => (
                      <div key={d.date} className="flex justify-between text-xs p-2 bg-surface-900/50 rounded">
                        <span className="text-gray-400">{d.date}</span>
                        <span className="text-gray-500">{d.pageviews} views · {d.visitors} visitors</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-surface-800 rounded-xl border border-gray-700/50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700/50">
            <span className="text-xs text-gray-500">Docker Logs (auto-refresh 5s)</span>
          </div>
          <pre className="p-4 text-xs font-mono text-gray-400 overflow-auto max-h-[600px] whitespace-pre-wrap leading-relaxed">
            {logs || 'No logs available'}
          </pre>
        </div>
      )}

      {tab === 'build-log' && (
        <div className="bg-surface-800 rounded-xl p-4 border border-gray-700/50 max-h-[500px] overflow-auto">
          {buildLogs.length === 0 ? (
            <p className="text-gray-500 text-sm">No build logs</p>
          ) : (
            <div className="space-y-1 font-mono text-xs">
              {buildLogs.map((l: any) => (
                <div key={l.id} className={cn('py-0.5', l.level === 'error' ? 'text-red-400' : 'text-gray-400')}>
                  <span className="text-gray-600 mr-2">{l.created_at?.slice(11, 19)}</span>
                  {l.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-3 border border-gray-700/50">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn('text-lg font-semibold mt-1', color || 'text-gray-100')}>{value}</p>
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
