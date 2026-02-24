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
  AICourseContent,
  API_BASE,
  aiTranslate,
  downloadEpisode,
  generateCourseAiContent,
  getCourse,
  processEpisode,
  processSubtitles,
  retryEpisode,
  startProcessing,
  toggleDebug,
  translateEpisodeTitle,
  UploadEpisodeResponse,
  uploadEpisode,
} from '@/services/api'

function toWsUrl(base: string, courseId: string) {
  const wsBase = base.replace(/^http/i, 'ws')
  return `${wsBase}/ws/courses/${courseId}/live-logs/`
}

type GlobalAction = 'toggle_debug' | 'start_download' | 'process_subtitles' | 'ai_translate' | 'ai_course_content'
type EpisodeAction = 'download' | 'process' | 'upload' | 'retry' | 'translate'
const EXPIRED_LINK_PREFIX = 'LINK_EXPIRED:'

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

function parseAiCourseContent(value: unknown): AICourseContent | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  const data = value as Record<string, unknown>
  const asText = (item: unknown) => (typeof item === 'string' && item.trim() ? item.trim() : null)
  const asList = (item: unknown) =>
    Array.isArray(item) ? item.map((entry) => (typeof entry === 'string' ? entry.trim() : '')).filter(Boolean) : []

  const course_overview = asText(data.course_overview)
  const prerequisites_description = asText(data.prerequisites_description)
  const prerequisites = asList(data.prerequisites)
  const what_you_will_learn = asList(data.what_you_will_learn)
  const course_goals = asList(data.course_goals)

  if (!course_overview || !prerequisites_description || !prerequisites.length || !what_you_will_learn.length || !course_goals.length) {
    return null
  }

  return {
    course_overview,
    prerequisites,
    prerequisites_description,
    what_you_will_learn,
    course_goals,
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function listToHtml(items: string[]): string {
  return items.map((item) => `    <li>${escapeHtml(item)}</li>`).join('\n')
}

function buildCourseContentHtml(content: AICourseContent): string {
  const paragraphs = content.course_overview
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean)
  const overviewHtml = (paragraphs.length ? paragraphs : [content.course_overview])
    .map((item) => `  <p>${escapeHtml(item).replace(/\n/g, '<br />')}</p>`)
    .join('\n')

  return [
    '<section class="generated-course-content" dir="rtl">',
    '  <h2>شرح دوره</h2>',
    overviewHtml,
    '  <h3>پیش نیاز ها</h3>',
    '  <ul>',
    listToHtml(content.prerequisites),
    '  </ul>',
    '  <h3>توضیحات پیش نیاز</h3>',
    `  <p>${escapeHtml(content.prerequisites_description).replace(/\n/g, '<br />')}</p>`,
    '  <h3>آنچه در این دوره می آموزید</h3>',
    '  <ul>',
    listToHtml(content.what_you_will_learn),
    '  </ul>',
    '  <h3>اهداف دوره</h3>',
    '  <ul>',
    listToHtml(content.course_goals),
    '  </ul>',
    '</section>',
  ].join('\n')
}

export default function CourseDetailPage() {
  const params = useParams<{ id: string }>()
  const courseId = params.id

  const [course, setCourse] = useState<Awaited<ReturnType<typeof getCourse>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)
  const [copyHint, setCopyHint] = useState<string>('Click HTML box to copy all')
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
        const uploadResult: UploadEpisodeResponse = await uploadEpisode(episodeId)
        if (uploadResult.skip_existing) {
          if (uploadResult.debug_halt) {
            setStatusNote('Upload stopped in debug mode: similar episode already exists on target.')
          } else {
            setStatusNote('Upload skipped: similar episode already exists on target.')
          }
          await load()
          return
        }
        if (uploadResult.summary) {
          const summary = uploadResult.summary
          setStatusNote(
            `Upload finished: uploaded=${summary.run_uploaded}, failed=${summary.run_failed}, skipped=${summary.run_skipped_existing}`
          )
          await load()
          return
        }
      } else if (action === 'translate') {
        await translateEpisodeTitle(episodeId)
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

  const hasExpiredLinks = useMemo(() => {
    if (!course) return false

    const flag = course.extra_metadata?.links_expired
    if (flag === true) return true

    return course.episodes.some((episode) => (episode.error_message ?? '').startsWith(EXPIRED_LINK_PREFIX))
  }, [course])

  const aiCourseContent = useMemo(() => parseAiCourseContent(course?.extra_metadata?.ai_course_content), [course])
  const aiCourseContentHtml = useMemo(
    () => (aiCourseContent ? buildCourseContentHtml(aiCourseContent) : ''),
    [aiCourseContent]
  )

  const jumpToLinkManager = () => {
    document.getElementById('link-manager')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const copyHtmlPayload = async () => {
    if (!aiCourseContentHtml) {
      return
    }
    try {
      await navigator.clipboard.writeText(aiCourseContentHtml)
      setCopyHint('Copied to clipboard')
      setTimeout(() => setCopyHint('Click HTML box to copy all'), 1800)
    } catch {
      setCopyHint('Copy failed')
      setTimeout(() => setCopyHint('Click HTML box to copy all'), 1800)
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

          <button
            className={`btn secondary ${runningGlobalAction === 'ai_course_content' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('ai_course_content', 'AI course content', () => generateCourseAiContent(courseId))}
          >
            {runningGlobalAction === 'ai_course_content' ? 'Generating...' : 'Generate AI Content'}
          </button>
        </div>

        {error && <p>{error}</p>}
      </section>

      <section className="panel stack">
        <h3 dir="rtl">محتوای تولیدشده با هوش مصنوعی</h3>
        {aiCourseContent ? (
          <div className="stack ai-content" dir="rtl">
            <div className="stack" style={{ gap: 6 }}>
              <h4>شرح دوره</h4>
              <p className="overview-text">{aiCourseContent.course_overview}</p>
            </div>

            <div className="stack" style={{ gap: 6 }}>
              <h4>پیش نیاز ها</h4>
              <ul className="bullet-list">
                {aiCourseContent.prerequisites.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="stack" style={{ gap: 6 }}>
              <h4>توضیحات پیش نیاز</h4>
              <p>{aiCourseContent.prerequisites_description}</p>
            </div>

            <div className="stack" style={{ gap: 6 }}>
              <h4>آنچه در این دوره می آموزید</h4>
              <ul className="bullet-list">
                {aiCourseContent.what_you_will_learn.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="stack" style={{ gap: 6 }}>
              <h4>اهداف دوره</h4>
              <ul className="bullet-list">
                {aiCourseContent.course_goals.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="stack" style={{ gap: 6 }}>
              <div className="row-between">
                <h4>HTML Output</h4>
                <small className="copy-hint">{copyHint}</small>
              </div>
              <div
                className="html-copy-box"
                role="button"
                tabIndex={0}
                onClick={copyHtmlPayload}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    void copyHtmlPayload()
                  }
                }}
              >
                <pre>{aiCourseContentHtml}</pre>
              </div>
            </div>
          </div>
        ) : (
          <p dir="rtl">هنوز محتوای هوش مصنوعی تولید نشده است. روی دکمه Generate AI Content بزنید.</p>
        )}
      </section>

      {hasExpiredLinks && (
        <section className="panel stack">
          <p className="operation-banner warn">
            Download links have expired. Please paste a fresh link batch, then start download again.
          </p>
          <div className="row">
            <button type="button" className="btn warn" onClick={jumpToLinkManager}>
              Paste New Links
            </button>
          </div>
        </section>
      )}

      <LinkManager courseId={courseId} showExpiredNotice={hasExpiredLinks} />

      <section className="panel stack">
        <h3>Episodes</h3>
        <EpisodeTable episodes={course.episodes} onAction={runEpisodeAction} runningAction={runningEpisodeAction} />
      </section>

      <DebugConsole connected={connected} messages={messages} />
    </div>
  )
}
