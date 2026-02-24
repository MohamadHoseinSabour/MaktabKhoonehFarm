import Link from 'next/link'
import { AdminSidebar } from '@/components/AdminSidebar'

export default function AdminIndexPage() {
  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h1 style={{ marginBottom: '1.5rem' }}>Admin Dashboard</h1>
        <p style={{ marginBottom: '2rem' }}>Welcome to the ACP control panel. Select an option below or from the sidebar to manage your system.</p>

        <div className="grid cols-2" style={{ gap: '1.5rem' }}>
          <Link href="/admin/courses" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--accent)' }}>Manage Courses</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>View, open, or delete all courses stored in the database.</p>
          </Link>
          <Link href="/admin/settings" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--success)' }}>General Settings</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>Configure upload automation semantics, xpath mappings, and session cookies.</p>
          </Link>
          <Link href="/admin/ai-config" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--warning)' }}>AI Configuration</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>Provide or manage API keys for translation providers like OpenAI or Claude.</p>
          </Link>
          <Link href="/admin/logs" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: '#8b5cf6' }}>System Logs</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>View live activity logs, worker stdout, and component lifecycle events.</p>
          </Link>
        </div>
      </section>
    </div>
  )
}
