'use client'

import { useEffect, useState } from 'react'

import { CourseProgress, getCourseProgress } from '@/services/api'

export function useCourseProgress(courseId: string) {
  const [progress, setProgress] = useState<CourseProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    const fetchData = async () => {
      try {
        const data = await getCourseProgress(courseId)
        if (active) {
          setProgress(data)
          setError(null)
        }
      } catch (err) {
        if (active) {
          setError((err as Error).message)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [courseId])

  return { progress, loading, error }
}