'use client'

import { FormEvent, useEffect, useState } from 'react'

import { CourseCard } from '@/components/CourseCard'
import { createCourse, getCourses, Course } from '@/services/api'

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [debugMode, setDebugMode] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    try {
      const data = await getCourses()
      setCourses(data)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => {
      void load()
    }, 5000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await createCourse(sourceUrl, debugMode)
      setSourceUrl('')
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <section className="panel stack">
        <h1>Add New Course</h1>
        <form className="stack" onSubmit={submit}>
          <input
            type="url"
            required
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://git.ir/..."
          />
          <label className="row">
            <input
              type="checkbox"
              checked={debugMode}
              onChange={(event) => setDebugMode(event.target.checked)}
              style={{ width: 18 }}
            />
            <span>Enable debug mode for first-run validation</span>
          </label>
          <button className="btn" disabled={loading}>
            {loading ? 'Adding...' : 'Add + Scrape'}
          </button>
        </form>
        {error && <p>{error}</p>}
      </section>

      <section className="grid cols-3">
        {courses.map((course) => (
          <CourseCard key={course.id} course={course} />
        ))}
      </section>
    </>
  )
}
