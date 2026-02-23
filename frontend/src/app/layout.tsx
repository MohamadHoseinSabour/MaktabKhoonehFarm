import type { Metadata } from 'next'
import Link from 'next/link'
import { Space_Grotesk, Vazirmatn } from 'next/font/google'

import './globals.css'

const headingFont = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-heading',
})

const persianFont = Vazirmatn({
  subsets: ['arabic', 'latin'],
  variable: '--font-persian',
})

export const metadata: Metadata = {
  title: 'ACMS Dashboard',
  description: 'Automated Course Migration System',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${headingFont.variable} ${persianFont.variable}`}>
        <div className="bg-grid" />
        <header className="topbar">
          <div className="brand">
            <span className="dot" />
            <strong>ACMS</strong>
          </div>
          <nav>
            <Link href="/">Dashboard</Link>
            <Link href="/courses">Courses</Link>
            <Link href="/admin/settings">Admin</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  )
}