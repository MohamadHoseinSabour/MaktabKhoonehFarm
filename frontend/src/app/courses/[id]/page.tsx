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
import {
  API_BASE,
  aiTranslate,
  downloadEpisode,
  getCourse,
  processEpisode,
  processSubtitles,
  retryEpisode,
  startProcessing,
  toggleDebug,
  uploadEpisode,
} from '@/services/api'

function toWsUrl(base: string, courseId: string) {
  const wsBase = base.replace(/^http/i, 'ws')
  return `${wsBase}/ws/courses/${courseId}/live-logs/`
}

type GlobalAction = 'toggle_debug' | 'start_download' | 'process_subtitles' | 'ai_translate'
type EpisodeAction = 'download' | 'process' | 'upload' | 'retry'

function episodeCurrentOperation(episode: { video_status: string; subtitle_status: string; exercise_status: string }) {
  if (episode.video_status === 'downloading') return 'Downloading video'
  if (episode.subtitle_status === 'downloading') return 'Downloading subtitle'
  if (episode.exercise_status === 'downloading') return 'Downloading exercise'
  if (episode.video_status === 'processing' || episode.subtitle_status === 'processing' || episode.exercise_status === 'processing') {
    return 'Processing assets'
  }
  if (episode.video_status === 'uploading' || episode.subtitle_status === 'uploading' || episode.exercise_status === 'uploading') {
    return 'Uploading assets'
  }
  return null
}

export default function CourseDetailPage() {
  const params = useParams<{ id: string }>()
  const courseId = params.id

  const [course, setCourse] = useState<Awaited<ReturnType<typeof getCourse>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)
  const [runningGlobalAction, setRunningGlobalAction] = useState<GlobalAction | null>(null)
  const [runningEpisodeAction, setRunningEpisodeAction] = useState<{ episodeId: string; action: EpisodeAction } | null>(null)

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

  useEffect(() => {
    const timer = setInterval(() => {
      void load()
    }, 4000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const runGlobalAction = async (action: GlobalAction, title: string, fn: () => Promise<unknown>) => {
    setRunningGlobalAction(action)
    setStatusNote(`${title} started...`)
    setError(null)
    try {
      const result = await fn()
      const payload = result as { mode?: string; status?: string }
      setStatusNote(`${title} ${payload?.mode ? `(${payload.mode})` : ''} ${payload?.status ?? 'done'}`.trim())
      await load()
    } catch (err) {
      setError((err as Error).message)
      setStatusNote(`${title} failed`)
    } finally {
      setRunningGlobalAction(null)
    }
  }

  const runEpisodeAction = async (episodeId: string, action: EpisodeAction) => {
    setRunningEpisodeAction({ episodeId, action })
    setError(null)
    setStatusNote(`Episode action started: ${action}`)

    try {
      if (action === 'download') {
        await downloadEpisode(episodeId)
      } else if (action === 'process') {
        await processEpisode(episodeId)
      } else if (action === 'upload') {
        await uploadEpisode(episodeId)
      } else {
        await retryEpisode(episodeId)
      }
      setStatusNote(`Episode action completed: ${action}`)
      await load()
    } catch (err) {
      setError((err as Error).message)
      setStatusNote(`Episode action failed: ${action}`)
    } finally {
      setRunningEpisodeAction(null)
    }
  }

  const activeEpisode = useMemo(() => {
    if (!course) return null
    return course.episodes.find((episode) => episodeCurrentOperation(episode)) ?? null
  }, [course])

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

        {activeEpisode && (
          <p className="operation-banner">
            Active: Episode {String(activeEpisode.episode_number ?? '-').padStart(3, '0')} - {activeEpisode.title_en ?? '-'} ({episodeCurrentOperation(activeEpisode)})
          </p>
        )}

        {course.debug_mode && (
          <p className="operation-banner">
            Debug mode is ON: only first episode will be downloaded by pipeline.
          </p>
        )}

        {statusNote && <p className="status-note">{statusNote}</p>}

        <div className="row">
          <button
            className={`btn secondary ${runningGlobalAction === 'toggle_debug' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('toggle_debug', 'Toggle debug', () => toggleDebug(courseId))}
          >
            {runningGlobalAction === 'toggle_debug' ? 'Updating...' : `Debug: ${course.debug_mode ? 'ON' : 'OFF'}`}
          </button>

          <button
            className={`btn ${runningGlobalAction === 'start_download' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('start_download', 'Download pipeline', () => startProcessing(courseId))}
          >
            {runningGlobalAction === 'start_download' ? 'Starting download...' : 'Start Download'}
          </button>

          <button
            className={`btn ${runningGlobalAction === 'process_subtitles' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('process_subtitles', 'Subtitle processing', () => processSubtitles(courseId))}
          >
            {runningGlobalAction === 'process_subtitles' ? 'Processing...' : 'Process Subtitles'}
          </button>

          <button
            className={`btn ${runningGlobalAction === 'ai_translate' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('ai_translate', 'AI translation', () => aiTranslate(courseId))}
          >
            {runningGlobalAction === 'ai_translate' ? 'Translating...' : 'AI Translate'}
          </button>
        </div>

        {error && <p>{error}</p>}
      </section>

      <LinkManager courseId={courseId} />

      <section className="panel stack">
        <h3>Episodes</h3>
        <EpisodeTable episodes={course.episodes} onAction={runEpisodeAction} runningAction={runningEpisodeAction} />
      </section>

      <DebugConsole connected={connected} messages={messages} />
    </div>
  )
}
