'use client'

import { useEffect, useState } from 'react'

import { CourseCard } from '@/components/CourseCard'
import { DashboardStats, getCourses, getDashboardStats, Course } from '@/services/api'

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [statsData, coursesData] = await Promise.all([getDashboardStats(), getCourses()])
        setStats(statsData)
        setCourses(coursesData.slice(0, 9))
      } catch (err) {
        setError((err as Error).message)
      }
    }

    load()
  }, [])

  return (
    <>
      <section className="grid cols-3">
        <article className="stat">
          <h3>Total Courses</h3>
          <h2>{stats?.total_courses ?? '-'}</h2>
        </article>
        <article className="stat">
          <h3>Active Downloads</h3>
          <h2>{stats?.active_downloads ?? '-'}</h2>
        </article>
        <article className="stat">
          <h3>Queued Tasks</h3>
          <h2>{stats?.queued_tasks ?? '-'}</h2>
        </article>
      </section>

      {error && <p>{error}</p>}

      <section className="panel stack">
        <h2>Recent Courses</h2>
        <div className="grid cols-3">
          {courses.map((course) => (
            <CourseCard key={course.id} course={course} />
          ))}
        </div>
      </section>
    </>
  )
}