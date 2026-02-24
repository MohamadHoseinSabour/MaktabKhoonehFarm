import Link from 'next/link'

export function AdminSidebar() {
  return (
    <aside className="admin-sidebar">
      <h2>Admin</h2>
      <nav>
        <Link href="/admin/courses">Manage Courses</Link>
        <Link href="/admin/settings">General Settings</Link>
        <Link href="/admin/ai-config">AI Config</Link>
        <Link href="/admin/logs">Logs</Link>
      </nav>
    </aside>
  )
}
