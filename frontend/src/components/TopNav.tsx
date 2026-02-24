'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export function TopNav() {
    const pathname = usePathname()

    return (
        <nav>
            <Link href="/" className={pathname === '/' ? 'active' : ''}>
                Dashboard
            </Link>
            <Link href="/courses" className={pathname.startsWith('/courses') ? 'active' : ''}>
                Courses
            </Link>
            <Link href="/admin/settings" className={pathname.startsWith('/admin') ? 'active' : ''}>
                Admin
            </Link>
        </nav>
    )
}
