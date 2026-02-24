'use client'

import { useEffect, useState, useRef } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { API_BASE } from '@/services/api'

type LogItem = {
  id: string
  level: string
  task_type: string
  status: string
  message: string
  created_at: string
}

const LogIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" />
  </svg>
)

export default function AdminLogsPage() {
  const [logs, setLogs] = useState<LogItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true

    const load = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/logs/`, { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(await response.text())
        }
        const data = (await response.json()) as LogItem[]
        if (mounted.current) setLogs(data)
      } catch (err) {
        if (mounted.current) setError((err as Error).message)
      }
    }

    void load()

    // Auto-refresh logs every few seconds for active view
    const timer = setInterval(() => void load(), 5000)

    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [])

  const getLevelColor = (level: string) => {
    switch (level.toLowerCase()) {
      case 'error': return 'var(--danger)';
      case 'warning': return 'var(--warning)';
      case 'info': return '#38bdf8';
      default: return 'var(--text-muted)';
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 150px)' }}>
        <div className="row-between" style={{ marginBottom: '1.5rem', flexShrink: 0 }}>
          <div className="row" style={{ gap: '1rem' }}>
            <div style={{ width: 44, height: 44, borderRadius: 'var(--radius-md)', background: '#1e293b', color: '#c4b5fd', display: 'grid', placeItems: 'center' }}>
              <LogIcon />
            </div>
            <div className="stack" style={{ gap: '0.2rem' }}>
              <h1 style={{ fontSize: '1.6rem', margin: 0 }}>جریان مانیتورینگ سیستم</h1>
              <p style={{ margin: 0, fontSize: '0.9rem' }}>خروجی‌های لحظه‌ای استخراج‌گرها و پردازشگرها در پس‌زمینه.</p>
            </div>
          </div>
          <div className="badge badge-processing">اتصال زنده</div>
        </div>

        {error && <div className="operation-banner warn" style={{ marginBottom: '1rem', flexShrink: 0 }}>{error}</div>}

        <div className="console" style={{ flex: 1, maxHeight: 'none', display: 'flex', flexDirection: 'column-reverse' }} dir="ltr">
          <div style={{ textAlign: 'left' }}>
            {logs.length === 0 ? (
              <div style={{ textAlign: 'center', opacity: 0.5, padding: '2rem' }}>در انتظار دریافت گزارشات...</div>
            ) : (
              logs.map((log) => (
                <div key={log.id} style={{ marginBottom: '0.75rem', fontFamily: 'monospace', display: 'flex', gap: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.5rem' }}>
                  <span style={{ color: 'rgba(255,255,255,0.4)', flexShrink: 0 }}>
                    {new Date(log.created_at).toLocaleTimeString()}
                  </span>
                  <span style={{ color: getLevelColor(log.level), width: '60px', flexShrink: 0, fontWeight: 600 }}>
                    [{log.level}]
                  </span>
                  <span style={{ color: 'rgba(255,255,255,0.6)', width: '120px', flexShrink: 0 }}>
                    {log.task_type}/{log.status}
                  </span>
                  <span style={{ color: '#e2e8f0', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
                    {log.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  )
}