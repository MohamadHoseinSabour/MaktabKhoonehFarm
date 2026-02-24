'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState, useRef } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { Course, deleteCourse, getCourses } from '@/services/api'

export default function AdminCoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyCourseId, setBusyCourseId] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)
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
    } finally {
      if (mounted.current) setLoading(false)
    }
  }

  useEffect(() => {
    mounted.current = true
    void load()
    return () => {
      mounted.current = false
    }
  }, [])

  const totalCourses = useMemo(() => courses.length, [courses])

  const handleDelete = async (course: Course) => {
    const title = (course.title_fa ?? course.title_en ?? course.slug ?? course.id).trim()
    const confirmed = window.confirm(
      `آیا از حذف کامل این دوره مطمئن هستید؟\n\n${title}\n\nاین عملیات غیرقابل بازگشت است و تمام فایل‌های دانلودشده دوره حذف می‌شود.`
    )
    if (!confirmed) {
      return
    }

    setBusyCourseId(course.id)
    setStatusNote(null)
    setError(null)
    try {
      await deleteCourse(course.id)
      if (mounted.current) {
        setStatusNote('دوره با موفقیت حذف شد.')
        await load()
      }
    } catch (err) {
      if (mounted.current) setError((err as Error).message)
    } finally {
      if (mounted.current) setBusyCourseId(null)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h1 style={{ marginBottom: '0.5rem' }}>Course Directory</h1>
        <p style={{ color: 'var(--text-muted)' }} dir="rtl">
          از این بخش می‌توانید کل دوره را به همراه همه فایل‌های دانلودشده به طور دائمی حذف کنید.
        </p>

        <div style={{ padding: '1rem', background: 'var(--bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong>Total Managed Items</strong>
          <span className="badge badge-pending" style={{ fontSize: '0.9rem', padding: '0.4rem 1rem' }}>{totalCourses} Courses</span>
        </div>

        {statusNote && <div className="status-note" style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--success)' }}>{statusNote}</div>}
        {error && <div className="operation-banner warn" style={{ marginBottom: '1.5rem' }}>{error}</div>}

        {loading ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Loading workspace structure...</p>
        ) : (
          <div className="stack" style={{ gap: '1rem' }}>
            {courses.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                No courses available.
              </div>
            ) : (
              courses.map((course) => {
                const titleFa = course.title_fa?.trim()
                const titleEn = course.title_en?.trim()
                const label = titleFa || titleEn || course.slug || 'Untitled Course'
                const isBusy = busyCourseId === course.id

                return (
                  <div key={course.id} className="admin-course-item" style={{ background: 'var(--bg)', border: '1px solid var(--border)', padding: '1.25rem' }}>
                    <div className="stack" style={{ gap: 4, flex: 1, minWidth: 0 }}>
                      <strong style={{ fontSize: '1rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</strong>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{course.source_url}</span>
                    </div>
                    <div className="row" style={{ flexShrink: 0 }}>
                      <Link className="btn secondary tiny" href={`/courses/${course.id}`}>
                        Open Details
                      </Link>
                      <button
                        type="button"
                        className={`btn warn tiny ${isBusy ? 'running' : ''}`}
                        disabled={Boolean(busyCourseId)}
                        onClick={() => handleDelete(course)}
                      >
                        {isBusy ? 'Deleting...' : 'Wipe Data'}
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        )}
      </section>
    </div>
  )
}
