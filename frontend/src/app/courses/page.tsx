'use client'

import { FormEvent, useEffect, useState, useRef } from 'react'
import { CourseCard } from '@/components/CourseCard'
import { createCourse, getCourses, Course } from '@/services/api'

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [debugMode, setDebugMode] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const mounted = useRef(true)

  const load = async () => {
    try {
      const data = await getCourses()
      if (mounted.current) {
        setCourses(data)
        setError(null)
      }
    } catch (err) {
      if (mounted.current) setError((err as Error).message)
    }
  }

  useEffect(() => {
    mounted.current = true
    void load()

    const timer = setInterval(() => {
      void load()
    }, 5000)

    return () => {
      mounted.current = false
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const normalizedSourceUrl = sourceUrl.trim()
    if (!normalizedSourceUrl) {
      setError('لینک دوره معتبر نیست.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      await createCourse(normalizedSourceUrl, debugMode)
      if (mounted.current) {
        setSourceUrl('')
        await load()
      }
    } catch (err) {
      if (mounted.current) setError((err as Error).message)
    } finally {
      if (mounted.current) setLoading(false)
    }
  }

  return (
    <>
      <section className="panel stack" style={{ marginBottom: '2rem' }}>
        <h1 style={{ marginBottom: '0.5rem' }}>افزودن دوره جدید</h1>
        <p style={{ marginBottom: '1.5rem' }}>با ثبت لینک منبع، فرآیند دانلود و پردازش یک دوره جدید را به سرعت آغاز کنید.</p>

        <form className="stack" onSubmit={submit} style={{ maxWidth: '600px' }}>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <input
                type="url"
                required
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder="مثال: https://git.ir/course-link"
                dir="ltr"
              />
            </div>
            <button className={`btn ${loading ? 'running' : ''}`} disabled={loading} style={{ padding: '0.875rem 2rem' }}>
              {loading ? 'در حال افزودن...' : 'افزودن و پردازش'}
            </button>
          </div>

          <label className="row" style={{ userSelect: 'none', color: 'var(--text-muted)' }}>
            <input
              type="checkbox"
              checked={debugMode}
              onChange={(event) => setDebugMode(event.target.checked)}
            />
            <span>فعال‌سازی حالت دیباگ (پردازش فقط قسمت اول)</span>
          </label>
        </form>
        {error && <div className="operation-banner warn" style={{ marginTop: '1rem', maxWidth: '600px' }}>{error}</div>}
      </section>

      <section className="grid cols-3">
        {courses.map((course) => (
          <CourseCard key={course.id} course={course} />
        ))}
        {courses.length === 0 && !loading && (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 1rem', opacity: 0.5 }}>
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
            </svg>
            <h3>هنوز دوره‌ای در دسترس نیست</h3>
            <p>اولین دوره خود را با استفاده از فرم بالا اضافه کنید.</p>
          </div>
        )}
      </section>
    </>
  )
}
