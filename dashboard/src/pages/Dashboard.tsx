import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, ExternalLink, MessageCircle, Terminal, FileCode, CheckCircle2, Circle } from 'lucide-react'
import { api } from '../lib/api'
import { statusColors, cn, formatDate } from '../lib/utils'

export default function Dashboard({ setup }: { setup: any }) {
  const [sites, setSites] = useState<any[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    api.get('/sites').then((d) => { setSites(Array.isArray(d) ? d : []); setLoaded(true) }).catch(() => setLoaded(true))
    const interval = setInterval(() => {
      api.get('/sites').then((d) => setSites(Array.isArray(d) ? d : [])).catch(() => {})
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const staging = sites.filter(s => s.status === 'staging').length
  const production = sites.filter(s => s.status === 'production').length
  const errors = sites.filter(s => s.status === 'error').length
  const botName = setup?.telegram_bot || ''
  const telegramOk = setup?.telegram_configured || false

  if (!loaded) {
    return <p className="text-gray-600 font-mono text-sm">Loading...</p>
  }

  if (setup?.sites_count > 0 && sites.length === 0) {
    localStorage.removeItem('pleng_auth')
    window.location.href = '/login'
    return null
  }

  // Onboarding
  if (sites.length === 0) {
    return (
      <div className="max-w-2xl mx-auto space-y-6 mt-8">
        <div className="text-center">
          <h2 className="text-3xl font-display font-black tracking-tight mb-2">Welcome to Pleng</h2>
          <p className="text-gray-500 font-mono text-sm">Your AI Platform Engineer</p>
        </div>

        <div className="bg-surface-800 rounded-xl p-6 border border-border space-y-4">
          <h3 className="font-mono font-bold text-sm uppercase tracking-wider text-gray-300">Getting started</h3>

          <SetupStep
            done={true}
            title="Pleng is running"
            description="All services are up."
          />
          <SetupStep
            done={telegramOk}
            title="Telegram bot connected"
            description={
              telegramOk
                ? botName ? `@${botName} is ready. Message it to deploy.` : 'Bot is configured.'
                : 'Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to your .env file, then restart.'
            }
            link={botName ? `https://t.me/${botName}` : undefined}
            linkLabel={botName ? `Open @${botName}` : undefined}
          />
          <SetupStep
            done={false}
            title="Deploy your first app"
            description={
              telegramOk
                ? 'Message your bot on Telegram. Try: "deploy github.com/user/repo" or "build me a landing page"'
                : 'Configure Telegram first, then talk to your bot to deploy.'
            }
          />
        </div>

        <div className="bg-surface-800 rounded-xl p-6 border border-border space-y-3">
          <h3 className="font-mono font-bold text-sm uppercase tracking-wider text-gray-300">How to talk to Pleng</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <InteractionCard
              icon={MessageCircle}
              title="Telegram"
              description="From anywhere. Deploy, check status, ask questions."
              link={botName ? `https://t.me/${botName}` : undefined}
              color="text-blue-400"
            />
            <InteractionCard
              icon={Terminal}
              title="Terminal"
              description="On the VPS. Run: make chat"
              color="text-primary-400"
            />
            <InteractionCard
              icon={Globe}
              title="Dashboard"
              description="You're here. View sites, logs, status."
              color="text-primary-300"
            />
            <InteractionCard
              icon={FileCode}
              title="External agents"
              description="Read /skill.md from any AI tool."
              link={setup?.panel_url ? `${setup.panel_url}/skill.md` : undefined}
              color="text-amber-400"
            />
          </div>
        </div>
      </div>
    )
  }

  // Normal dashboard
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-display font-black tracking-tight">Dashboard</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Total" value={sites.length} color="text-primary-400" />
        <Stat label="Staging" value={staging} color="text-yellow-400" />
        <Stat label="Production" value={production} color="text-green-400" />
        <Stat label="Errors" value={errors} color="text-red-400" />
      </div>

      <div className="bg-surface-800 rounded-xl p-4 border border-border">
        <h3 className="font-mono font-bold text-xs uppercase tracking-wider text-gray-400 flex items-center gap-2 mb-3">
          <Globe size={14} /> Sites
        </h3>
        <div className="space-y-1">
          {sites.map((s: any) => {
            const domain = s.production_domain || s.staging_domain || ''
            const url = s.production_domain ? `https://${domain}` : domain ? `http://${domain}` : ''
            return (
              <Link key={s.id} to={`/sites/${s.id}`}
                className="flex items-center justify-between p-3 rounded-lg bg-surface-900/50 hover:bg-surface-700/50 border border-transparent hover:border-border-bright transition-all duration-200">
                <div className="flex items-center gap-3">
                  <span className={cn('w-2 h-2 rounded-full',
                    s.status === 'production' ? 'bg-green-400' :
                    s.status === 'staging' ? 'bg-yellow-400' :
                    s.status === 'error' ? 'bg-red-400' : 'bg-gray-500'
                  )} />
                  <div>
                    <p className="text-sm font-medium">{s.name}</p>
                    {url && <p className="text-xs text-primary-400 font-mono">{domain}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[0.65rem] font-mono text-gray-600">{formatDate(s.created_at)}</span>
                  <span className={cn('text-[0.65rem] font-mono px-2 py-0.5 rounded-full', statusColors[s.status] || 'bg-gray-700')}>
                    {s.status}
                  </span>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                      className="text-gray-600 hover:text-primary-400 transition-colors">
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-surface-800 rounded-xl p-4 border border-border hover:border-border-bright transition-all duration-200 group">
      <p className="text-[0.65rem] font-mono uppercase tracking-wider text-gray-600">{label}</p>
      <p className={cn('text-2xl font-display font-black mt-1', color)}>{value}</p>
    </div>
  )
}

function SetupStep({ done, title, description, link, linkLabel }: {
  done: boolean; title: string; description: string; link?: string; linkLabel?: string
}) {
  return (
    <div className="flex items-start gap-3">
      {done
        ? <CheckCircle2 size={18} className="text-primary-400 mt-0.5 shrink-0" />
        : <Circle size={18} className="text-gray-700 mt-0.5 shrink-0" />
      }
      <div>
        <p className={cn('text-sm font-medium', done ? 'text-gray-400' : 'text-gray-200')}>{title}</p>
        <p className="text-xs text-gray-600 mt-0.5">{description}</p>
        {link && (
          <a href={link} target="_blank" rel="noreferrer"
            className="text-xs text-primary-400 hover:text-primary-300 font-mono mt-1 inline-block transition-colors">
            {linkLabel || link}
          </a>
        )}
      </div>
    </div>
  )
}

function InteractionCard({ icon: Icon, title, description, link, color }: {
  icon: any; title: string; description: string; link?: string; color: string
}) {
  const content = (
    <div className="bg-surface-900/50 rounded-lg p-3 border border-border hover:border-border-bright hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={15} className={color} />
        <span className="text-sm font-medium">{title}</span>
      </div>
      <p className="text-xs text-gray-600">{description}</p>
    </div>
  )

  if (link) {
    return <a href={link} target="_blank" rel="noreferrer">{content}</a>
  }
  return content
}
