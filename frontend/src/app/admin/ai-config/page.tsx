'use client'

import { FormEvent, useEffect, useState } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { API_BASE } from '@/services/api'

type Config = {
  id: string
  provider: string
  model_name: string
  priority: number
  is_active: boolean
}

export default function AIConfigPage() {
  const [configs, setConfigs] = useState<Config[]>([])
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('gpt-4o-mini')
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    const response = await fetch(`${API_BASE}/api/ai-configs/`, { cache: 'no-store' })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    setConfigs((await response.json()) as Config[])
  }

  useEffect(() => {
    load().catch((err) => setError((err as Error).message))
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
      setApiKey('')
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack">
        <h1>AI Provider Management</h1>

        <form className="stack" onSubmit={submit}>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="claude">Claude</option>
          </select>
          <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model" required />
          <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="API Key" required />
          <button className="btn">Add Provider</button>
        </form>

        <div className="stack">
          {configs.map((cfg) => (
            <article key={cfg.id} className="panel">
              <h3>{cfg.provider} ({cfg.model_name})</h3>
              <p>Priority: {cfg.priority} | {cfg.is_active ? 'Active' : 'Disabled'}</p>
            </article>
          ))}
        </div>

        {error && <p>{error}</p>}
      </section>
    </div>
  )
}