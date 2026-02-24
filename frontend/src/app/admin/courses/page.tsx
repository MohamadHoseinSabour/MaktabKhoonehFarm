'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { AdminSidebar } from '@/components/AdminSidebar'
import { Course, deleteCourse, getCourses } from '@/services/api'

export default function AdminCoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyCourseId, setBusyCourseId] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)

  const load = async () => {
    try {
      const data = await getCourses()
      setCourses(data)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
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
      setStatusNote('دوره با موفقیت حذف شد.')
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusyCourseId(null)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack">
        <h1>Manage Courses</h1>
        <p dir="rtl">از این بخش می‌توانید کل دوره را به همراه همه فایل‌های دانلودشده حذف کنید.</p>
        <p>Total courses: {totalCourses}</p>
        {statusNote && <p className="status-note">{statusNote}</p>}
        {error && <p>{error}</p>}
        {loading ? (
          <p>Loading...</p>
        ) : (
          <div className="stack">
            {courses.map((course) => {
              const titleFa = course.title_fa?.trim()
              const titleEn = course.title_en?.trim()
              const label = titleFa || titleEn || course.slug || 'Untitled Course'
              const isBusy = busyCourseId === course.id
              return (
                <div key={course.id} className="admin-course-item">
                  <div className="stack" style={{ gap: 4 }}>
                    <strong>{label}</strong>
                    <span>{course.source_url}</span>
                  </div>
                  <div className="row">
                    <Link className="btn secondary" href={`/courses/${course.id}`}>
                      Open
                    </Link>
                    <button
                      type="button"
                      className="btn warn"
                      disabled={Boolean(busyCourseId)}
                      onClick={() => handleDelete(course)}
                    >
                      {isBusy ? 'Deleting...' : 'Delete Course'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
