'use client'

import { FormEvent, useEffect, useState, useRef } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { API_BASE } from '@/services/api'

type Config = {
  id: string
  provider: string
  model_name: string
  priority: number
  is_active: boolean
}

const ModelIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </svg>
)

export default function AIConfigPage() {
  const [configs, setConfigs] = useState<Config[]>([])
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('gpt-4o-mini')
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  const load = async () => {
    const response = await fetch(`${API_BASE}/api/ai-configs/`, { cache: 'no-store' })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    const data = (await response.json()) as Config[]
    if (mounted.current) setConfigs(data)
  }

  useEffect(() => {
    mounted.current = true
    load().catch((err) => {
      if (mounted.current) setError((err as Error).message)
    })
    return () => {
      mounted.current = false
    }
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/api/ai-configs/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          model_name: modelName,
          priority: configs.length + 1,
          is_active: true,
        }),
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      if (mounted.current) {
        setApiKey('')
        await load()
      }
    } catch (err) {
      if (mounted.current) setError((err as Error).message)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <div className="row" style={{ gap: '1rem', marginBottom: '1.5rem' }}>
          <div style={{ width: 48, height: 48, borderRadius: 'var(--radius-md)', background: 'var(--accent-soft)', color: 'var(--accent)', display: 'grid', placeItems: 'center' }}>
            <ModelIcon />
          </div>
          <div className="stack" style={{ gap: '0.2rem' }}>
            <h1 style={{ fontSize: '1.8rem', margin: 0 }}>AI Inference Providers</h1>
            <p style={{ margin: 0, fontSize: '0.95rem' }}>Inject secure keys to enable multi-agent translations and intelligence tasks.</p>
          </div>
        </div>

        <form className="stack" onSubmit={submit} style={{ background: 'var(--bg)', border: '1px solid var(--border)', padding: '1.5rem', borderRadius: 'var(--radius-lg)' }}>
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Register API Key</h3>
          <div className="grid cols-3" style={{ gap: '1rem' }}>
            <div className="stack" style={{ gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Provider Engine</label>
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="openai">OpenAI Edge</option>
                <option value="claude">Anthropic Claude</option>
              </select>
            </div>

            <div className="stack" style={{ gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Target Model</label>
              <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model (e.g. gpt-4)" required />
            </div>

            <div className="stack" style={{ gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Secret Token</label>
              <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-..." required />
            </div>
          </div>

          <button className="btn" style={{ marginTop: '1rem', alignSelf: 'flex-start' }}>Inject Key Securely</button>
        </form>

        <h3 style={{ marginTop: '2rem', fontSize: '1.2rem' }}>Configured Identities</h3>
        <div className="grid cols-3" style={{ gap: '1.5rem' }}>
          {configs.map((cfg) => (
            <article key={cfg.id} className="stat" style={{ borderTop: `4px solid ${cfg.is_active ? 'var(--success)' : 'var(--text-muted)'}` }}>
              <div className="row-between" style={{ marginBottom: '1rem' }}>
                <span className={`badge ${cfg.is_active ? 'badge-processing' : 'badge-muted'}`} style={{ margin: 0 }}>
                  {cfg.is_active ? 'Active Node' : 'Suspended'}
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Priority {cfg.priority}</span>
              </div>
              <h3 style={{ fontSize: '1.1rem', color: 'var(--text)', marginBottom: '0.2rem' }}>{cfg.provider.toUpperCase()}</h3>
              <p style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--accent)' }}>{cfg.model_name}</p>
            </article>
          ))}
          {configs.length === 0 && (
            <div style={{ gridColumn: '1 / -1', padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', background: 'var(--bg)', borderRadius: 'var(--radius-md)' }}>
              No AI identities strictly registered.
            </div>
          )}
        </div>

        {error && <div className="operation-banner warn" style={{ marginTop: '1.5rem' }}>{error}</div>}
      </section>
    </div>
  )
}