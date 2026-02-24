import Link from 'next/link'
import { AdminSidebar } from '@/components/AdminSidebar'

export default function AdminIndexPage() {
  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h1 style={{ marginBottom: '1.5rem' }}>داشبورد مدیریت</h1>
        <p style={{ marginBottom: '2rem' }}>به کنترل پنل سیستم خوش آمدید. یکی از گزینه‌های زیر را برای مدیریت بخش‌های مختلف انتخاب کنید.</p>

        <div className="grid cols-2" style={{ gap: '1.5rem' }}>
          <Link href="/admin/courses" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--accent)' }}>مدیریت دوره‌ها</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>مشاهده، باز کردن یا حذف تمام دوره‌های ذخیره‌شده در سیستم.</p>
          </Link>
          <Link href="/admin/settings" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--success)' }}>تنظیمات عمومی</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>پیکربندی خودکارسازی آپلود، مسیرهای XPath و کوکی‌های ورود (Sessions).</p>
          </Link>
          <Link href="/admin/ai-config" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: 'var(--warning)' }}>تنظیمات هوش مصنوعی</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>مدیریت کلیدهای API برای ارائه‌دهندگان سرویس مثل OpenAI.</p>
          </Link>
          <Link href="/admin/logs" className="stat" style={{ textDecoration: 'none' }}>
            <h3 style={{ color: '#8b5cf6' }}>لاگ سیستم</h3>
            <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', flex: 1 }}>مشاهده لحظه‌ای لاگ‌ها و رویدادهای در حال اجرا توسط ربات پایتون.</p>
          </Link>
        </div>
      </section>
    </div>
  )
}
