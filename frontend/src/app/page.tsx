'use client'

import { useEffect, useState, useRef } from 'react'
import { CourseCard } from '@/components/CourseCard'
import { DashboardStats, getCourses, getDashboardStats, Course } from '@/services/api'

// Inline SVG components
const CourseIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
  </svg>
)
const DownloadIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
)
const TaskIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 11 12 14 22 4" />
    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
)

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true

    const load = async () => {
      try {
        const [statsData, coursesData] = await Promise.all([getDashboardStats(), getCourses()])
        if (mounted.current) {
          setStats(statsData)
          setCourses(coursesData.slice(0, 9))
          setError(null)
        }
      } catch (err) {
        if (mounted.current) setError((err as Error).message)
      }
    }

    void load()
    const timer = setInterval(() => {
      void load()
    }, 5000)

    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [])

  return (
    <>
      <section className="grid cols-3" style={{ marginTop: '1rem' }}>
        <article className="stat" style={{ borderTop: '4px solid var(--accent)' }}>
          <div className="row-between">
            <h3>Total Courses</h3>
            <span style={{ color: 'var(--accent)' }}><CourseIcon /></span>
          </div>
          <h2>{stats?.total_courses ?? '-'}</h2>
        </article>

        <article className="stat" style={{ borderTop: '4px solid var(--success)' }}>
          <div className="row-between">
            <h3>Active Downloads</h3>
            <span style={{ color: 'var(--success)' }}><DownloadIcon /></span>
          </div>
          <h2>{stats?.active_downloads ?? '-'}</h2>
        </article>

        <article className="stat" style={{ borderTop: '4px solid var(--warning)' }}>
          <div className="row-between">
            <h3>Queued Tasks</h3>
            <span style={{ color: 'var(--warning)' }}><TaskIcon /></span>
          </div>
          <h2>{stats?.queued_tasks ?? '-'}</h2>
        </article>
      </section>

      {error && (
        <div className="operation-banner warn" style={{ marginTop: '1rem' }}>
          <strong>Error: </strong>{error}
        </div>
      )}

      <section className="panel stack" style={{ marginTop: '1rem', padding: '2rem' }}>
        <div className="row-between" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.6rem' }}>Recent Courses</h2>
        </div>

        {courses.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
            No courses found. Head over to the Courses tab to add one.
          </div>
        ) : (
          <div className="grid cols-3">
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>
        )}
      </section>
    </>
  )
}
