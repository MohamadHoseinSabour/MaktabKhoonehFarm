import type { Metadata } from 'next'
import Link from 'next/link'
import { Space_Grotesk, Vazirmatn } from 'next/font/google'

import './globals.css'
import { TopNav } from '@/components/TopNav'

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
          <Link href="/" className="brand">
            <span className="dot" />
            <span>ACMS</span>
          </Link>
          <TopNav />
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  )
}