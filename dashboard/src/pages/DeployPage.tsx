import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, GitBranch, Wand2, Rocket } from 'lucide-react'
import { api } from '../lib/api'
import { cn } from '../lib/utils'

type Mode = 'git' | 'compose' | 'generate'

export default function DeployPage() {
  const [mode, setMode] = useState<Mode>('git')
  const [name, setName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [composePath, setComposePath] = useState('')
  const [description, setDescription] = useState('')
  const [deploying, setDeploying] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const modes = [
    { id: 'git' as Mode, label: 'Git Repo', icon: GitBranch, desc: 'Deploy from GitHub/Git' },
    { id: 'compose' as Mode, label: 'Docker Compose', icon: Upload, desc: 'Bring your own compose' },
    { id: 'generate' as Mode, label: 'AI Generate', icon: Wand2, desc: 'Describe it, AI builds it' },
  ]

  async function handleDeploy(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Name is required'); return }
    setError('')
    setDeploying(true)

    try {
      let result: any
      if (mode === 'git') {
        if (!repoUrl.trim()) { setError('Repo URL required'); setDeploying(false); return }
        result = await api.post('/deploy/git', { name: name.trim(), repo_url: repoUrl.trim() })
      } else if (mode === 'compose') {
        if (!composePath.trim()) { setError('Path required'); setDeploying(false); return }
        result = await api.post('/deploy/compose', { name: name.trim(), compose_path: composePath.trim() })
      } else {
        if (!description.trim()) { setError('Description required'); setDeploying(false); return }
        result = await api.post('/deploy/generate', { name: name.trim(), description: description.trim() })
      }

      if (result.detail) {
        setError(result.detail)
        setDeploying(false)
      } else if (result.site_id) {
        navigate(`/sites/${result.site_id}`)
      }
    } catch (err: any) {
      setError(err.message || 'Deploy failed')
      setDeploying(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Deploy</h2>

      <div className="grid grid-cols-3 gap-3">
        {modes.map(({ id, label, icon: Icon, desc }) => (
          <button key={id} onClick={() => setMode(id)}
            className={cn(
              'p-4 rounded-xl border text-left transition-all',
              mode === id ? 'border-primary-500 bg-primary-600/10' : 'border-gray-700/50 bg-surface-800 hover:border-gray-600'
            )}>
            <Icon size={20} className={mode === id ? 'text-primary-400' : 'text-gray-500'} />
            <p className="text-sm font-medium mt-2">{label}</p>
            <p className="text-xs text-gray-500 mt-1">{desc}</p>
          </button>
        ))}
      </div>

      <form onSubmit={handleDeploy} className="bg-surface-800 rounded-xl p-6 border border-gray-700/50 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">{error}</div>
        )}

        <div>
          <label className="block text-sm text-gray-400 mb-1">App Name</label>
          <input type="text" value={name}
            onChange={e => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
            placeholder="my-app"
            className="w-full px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500" />
          <p className="text-xs text-gray-600 mt-1">Will be at http://{name || 'my-app'}.YOUR-IP.sslip.io</p>
        </div>

        {mode === 'git' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">Repository URL</label>
            <input type="text" value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
              placeholder="https://github.com/user/repo"
              className="w-full px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500" />
          </div>
        )}

        {mode === 'compose' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">Path on server</label>
            <input type="text" value={composePath} onChange={e => setComposePath(e.target.value)}
              placeholder="/projects/my-project or /path/to/docker-compose.yml"
              className="w-full px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500" />
          </div>
        )}

        {mode === 'generate' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">What do you want?</label>
            <textarea value={description} onChange={e => setDescription(e.target.value)}
              placeholder="A booking API with Postgres, a color converter tool, a landing page for..."
              rows={4}
              className="w-full px-3 py-2 bg-surface-900 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary-500 resize-none" />
          </div>
        )}

        <button type="submit" disabled={deploying}
          className={cn(
            'w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors',
            deploying ? 'bg-gray-700 text-gray-400 cursor-not-allowed' : 'bg-primary-600 hover:bg-primary-700 text-white'
          )}>
          {deploying ? 'Deploying...' : <><Rocket size={16} /> Deploy</>}
        </button>
      </form>
    </div>
  )
}
