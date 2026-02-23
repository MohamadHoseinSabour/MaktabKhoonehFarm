'use client'

import { useEffect, useState } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { API_BASE } from '@/services/api'

type Setting = {
  id: string
  key: string
  value: string
  category?: string | null
  description?: string | null
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings/`, { cache: 'no-store' })
      const data = (await res.json()) as Setting[]
      setSettings(data)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await fetch(`${API_BASE}/api/settings/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings.map(({ key, value, category, description }) => ({ key, value, category, description }))),
      })
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack">
        <h1>General Settings</h1>
        {settings.map((item, index) => (
          <div key={item.id} className="stack">
            <strong>{item.key}</strong>
            <input
              value={item.value}
              onChange={(event) => {
                const next = [...settings]
                next[index] = { ...next[index], value: event.target.value }
                setSettings(next)
              }}
            />
          </div>
        ))}
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
        {error && <p>{error}</p>}
      </section>
    </div>
  )
}