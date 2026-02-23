import Link from 'next/link'

export default function AdminIndexPage() {
  return (
    <section className="panel stack">
      <h1>Admin Panel</h1>
      <div className="row">
        <Link className="btn" href="/admin/settings">Settings</Link>
        <Link className="btn" href="/admin/ai-config">AI Config</Link>
        <Link className="btn" href="/admin/logs">Logs</Link>
      </div>
    </section>
  )
}