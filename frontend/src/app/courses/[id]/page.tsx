'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { DebugConsole } from '@/components/DebugConsole'
import { EpisodeTable } from '@/components/EpisodeTable'
import { LinkManager } from '@/components/LinkManager'
import { ProgressBar } from '@/components/ProgressBar'
import { StatusBadge } from '@/components/StatusBadge'
import { useCourseProgress } from '@/hooks/useCourseProgress'
import { useWebSocket } from '@/hooks/useWebSocket'
import { API_BASE, aiTranslate, getCourse, processSubtitles, startProcessing, toggleDebug } from '@/services/api'

function toWsUrl(base: string, courseId: string) {
  const wsBase = base.replace(/^http/i, 'ws')
  return `${wsBase}/ws/courses/${courseId}/live-logs/`
}

export default function CourseDetailPage() {
  const params = useParams<{ id: string }>()
  const courseId = params.id

  const [course, setCourse] = useState<Awaited<ReturnType<typeof getCourse>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { progress } = useCourseProgress(courseId)

  const wsUrl = useMemo(() => toWsUrl(API_BASE, courseId), [courseId])
  const { connected, messages } = useWebSocket(wsUrl)

  const load = async () => {
    try {
      const data = await getCourse(courseId)
      setCourse(data)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const runAction = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (loading) {
    return <p>Loading...</p>
  }

  if (!course) {
    return <p>{error ?? 'Course not found'}</p>
  }

  return (
    <div className="grid">
      <section className="panel stack">
        <div className="row-between">
          <div className="stack" style={{ gap: 6 }}>
            <h1>{course.title_en ?? 'Untitled Course'}</h1>
            <p dir="rtl">{course.title_fa ?? '???? ????? ?????'}</p>
            <p>Platform: {course.source_platform ?? '-'} | Instructor: {course.instructor ?? '-'}</p>
          </div>
          <StatusBadge status={course.status} />
        </div>

        <ProgressBar value={progress?.progress_percent ?? 0} />

        <div className="row">
          <button className="btn secondary" onClick={() => runAction(() => toggleDebug(courseId))}>
            Debug: {course.debug_mode ? 'ON' : 'OFF'}
          </button>
          <button className="btn" onClick={() => runAction(() => startProcessing(courseId))}>Start Download</button>
          <button className="btn" onClick={() => runAction(() => processSubtitles(courseId))}>Process Subtitles</button>
          <button className="btn" onClick={() => runAction(() => aiTranslate(courseId))}>AI Translate</button>
        </div>
        {error && <p>{error}</p>}
      </section>

      <LinkManager courseId={courseId} />

      <section className="panel stack">
        <h3>Episodes</h3>
        <EpisodeTable episodes={course.episodes} />
      </section>

      <DebugConsole connected={connected} messages={messages} />
    </div>
  )
}