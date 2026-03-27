import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ExternalLink, ArrowUpCircle, ArrowLeft, Box, Clock, HardDrive } from 'lucide-react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
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

  if (!site) return <p className="text-gray-600 font-mono text-sm">Loading...</p>

  const domain = site.production_domain || site.staging_domain
  const url = site.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''

  return (
    <div className="space-y-4">
      {/* Back + Header */}
      <Link to="/sites" className="text-xs font-mono text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors">
        <ArrowLeft size={14} /> Back to sites
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-display font-black tracking-tight">{site.name}</h2>
            <span className={cn('text-[0.65rem] font-mono px-3 py-1 rounded-full', statusColors[site.status] || 'bg-gray-700')}>
              {site.status}
            </span>
          </div>
          {url && (
            <a href={url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 mt-2 px-4 py-2 bg-primary-500/10 border border-primary-500/20 rounded-lg text-primary-400 hover:bg-primary-500/15 hover:border-primary-500/30 transition-all duration-200">
              <ExternalLink size={14} />
              <span className="text-sm font-mono">{url}</span>
            </a>
          )}
        </div>
      </div>

      {/* Containers status */}
      {containers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {containers.map((c: any, i: number) => (
            <div key={i} className="bg-surface-800 rounded-lg p-3 border border-border hover:border-border-bright transition-all duration-200">
              <div className="flex items-center gap-2 mb-2">
                <Box size={13} className={c.State === 'running' ? 'text-green-400' : 'text-red-400'} />
                <span className="text-sm font-medium">{c.Name || c.Service || '?'}</span>
              </div>
              <div className="space-y-1 text-xs font-mono text-gray-600">
                <div className="flex items-center gap-1.5">
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
      <div className="flex gap-1 bg-surface-800 rounded-lg p-1 border border-border">
        {['overview', 'analytics', 'logs', 'build-log'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={cn('px-3 py-1.5 rounded-md text-xs font-mono capitalize transition-all duration-200',
              tab === t ? 'bg-primary-400 text-surface-900 font-bold' : 'text-gray-500 hover:text-gray-300 hover:bg-surface-700/50')}>
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
            <div className="bg-surface-800 rounded-xl p-4 border border-primary-500/20">
              <h4 className="text-sm font-mono font-bold mb-2 flex items-center gap-2">
                <ArrowUpCircle size={16} className="text-primary-400" /> Promote to Production
              </h4>
              <p className="text-xs text-gray-600 font-mono mb-3">Add a custom domain. SSL certificate via Let's Encrypt.</p>
              <div className="flex gap-2">
                <input
                  type="text" value={promoteDomain} onChange={e => setPromoteDomain(e.target.value)}
                  placeholder="app.example.com"
                  className="flex-1 px-3 py-2 bg-surface-900 border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-primary-500 transition-colors"
                />
                <button onClick={promote} disabled={promoting || !promoteDomain.trim()}
                  className="px-4 py-2 bg-primary-400 hover:bg-primary-300 disabled:bg-gray-800 disabled:text-gray-600 text-surface-900 rounded-lg text-sm font-mono font-bold transition-all duration-200 hover:-translate-y-0.5">
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
            <div className="bg-surface-800 rounded-xl p-6 border border-border text-center">
              <p className="text-gray-500 text-sm">No traffic data yet.</p>
              <p className="text-gray-700 text-xs font-mono mt-1">Analytics are collected from Traefik access logs. Data appears after the site receives traffic.</p>
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
                <div className="bg-surface-800 rounded-xl p-4 border border-border">
                  <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-gray-500 mb-3">Top Pages</h4>
                  <ResponsiveContainer width="100%" height={Math.max(180, analytics.top_pages.length * 32)}>
                    <BarChart data={analytics.top_pages} layout="vertical" margin={{ left: 10, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e2230" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: '#555a6e' }} />
                      <YAxis type="category" dataKey="path" tick={{ fontSize: 11, fill: '#8b90a0' }} width={150} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#13161e', border: '1px solid #2a2f40', borderRadius: 8, fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}
                        labelStyle={{ color: '#e8eaf0' }}
                      />
                      <Bar dataKey="views" name="Views" fill="#22d3a7" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="visitors" name="Visitors" fill="#1a9e7e" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {analytics.top_sources?.length > 0 && (
                <div className="bg-surface-800 rounded-xl p-4 border border-border">
                  <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-gray-500 mb-3">Top Sources</h4>
                  <div className="space-y-1">
                    {analytics.top_sources.map((s: any) => (
                      <div key={s.source} className="flex justify-between text-xs font-mono p-2 bg-surface-900/50 rounded border border-transparent hover:border-border transition-colors">
                        <span className="text-gray-300">{s.source}</span>
                        <span className="text-gray-600">{s.visitors} visitors</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analytics.daily?.length > 0 && (
                <div className="bg-surface-800 rounded-xl p-4 border border-border">
                  <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-gray-500 mb-3">Daily Traffic</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={analytics.daily.map((d: any) => ({ ...d, date: d.date.slice(5) }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e2230" />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#555a6e' }} />
                      <YAxis tick={{ fontSize: 11, fill: '#555a6e' }} width={35} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#13161e', border: '1px solid #2a2f40', borderRadius: 8, fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}
                        labelStyle={{ color: '#e8eaf0' }}
                      />
                      <Area type="monotone" dataKey="pageviews" name="Pageviews" stroke="#22d3a7" fill="#22d3a7" fillOpacity={0.12} strokeWidth={2} />
                      <Area type="monotone" dataKey="visitors" name="Visitors" stroke="#1a9e7e" fill="#1a9e7e" fillOpacity={0.08} strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-surface-800 rounded-xl border border-border overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            {/* Terminal-style dots */}
            <div className="flex items-center gap-3">
              <div className="flex gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
              </div>
              <span className="text-[0.65rem] font-mono uppercase tracking-wider text-gray-600">Docker Logs</span>
            </div>
            <span className="text-[0.6rem] font-mono text-gray-700">auto-refresh 5s</span>
          </div>
          <pre className="p-4 text-xs font-mono text-gray-400 overflow-auto max-h-[600px] whitespace-pre-wrap leading-relaxed">
            {logs || 'No logs available'}
          </pre>
        </div>
      )}

      {tab === 'build-log' && (
        <div className="bg-surface-800 rounded-xl border border-border overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="flex gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
              </div>
              <span className="text-[0.65rem] font-mono uppercase tracking-wider text-gray-600">Build Log</span>
            </div>
          </div>
          <div className="p-4 max-h-[500px] overflow-auto">
            {buildLogs.length === 0 ? (
              <p className="text-gray-600 text-sm font-mono">No build logs</p>
            ) : (
              <div className="space-y-0.5 font-mono text-xs">
                {buildLogs.map((l: any) => (
                  <div key={l.id} className={cn('py-0.5', l.level === 'error' ? 'text-red-400' : 'text-gray-500')}>
                    <span className="text-gray-700 mr-2">{l.created_at?.slice(11, 19)}</span>
                    {l.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-3 border border-border hover:border-border-bright transition-all duration-200">
      <p className="text-[0.65rem] font-mono uppercase tracking-wider text-gray-600">{label}</p>
      <p className={cn('text-lg font-display font-black mt-1', color || 'text-gray-100')}>{value}</p>
    </div>
  )
}

function Info({ label, value, link }: { label: string; value: string; link?: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-3 border border-border hover:border-border-bright transition-all duration-200">
      <p className="text-[0.65rem] font-mono uppercase tracking-wider text-gray-600 mb-1">{label}</p>
      {link ? (
        <a href={link} target="_blank" rel="noreferrer" className="text-sm text-primary-400 hover:text-primary-300 font-mono break-all transition-colors">{value}</a>
      ) : (
        <p className="text-sm break-all">{value || '-'}</p>
      )}
    </div>
  )
}
