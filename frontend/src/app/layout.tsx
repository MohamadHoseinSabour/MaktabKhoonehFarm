import type { Metadata } from 'next'
import Link from 'next/link'
import { Vazirmatn } from 'next/font/google'

import './globals.css'
import { TopNav } from '@/components/TopNav'

const persianFont = Vazirmatn({
  subsets: ['arabic', 'latin'],
  variable: '--font-persian',
})

export const metadata: Metadata = {
  title: 'داشبورد ACMS',
  description: 'سیستم هوشمند اتوماسیون دوره‌ها',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body className={persianFont.variable}>
        <div className="bg-grid" />
        <header className="topbar">
          <Link href="/" className="brand">
            <span className="dot" />
            <span style={{ fontFamily: 'sans-serif', paddingRight: '0.25rem' }}>ACMS</span>
          </Link>
          <TopNav />
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  )
}