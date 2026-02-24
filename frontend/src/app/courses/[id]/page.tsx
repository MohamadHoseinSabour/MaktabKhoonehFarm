'use client'

import { useEffect, useMemo, useState, useRef } from 'react'
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
  const mounted = useRef(true)

  const [course, setCourse] = useState<Awaited<ReturnType<typeof getCourse>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)
  const [copyHint, setCopyHint] = useState<string>('Copy to Clipboard')
  const [runningGlobalAction, setRunningGlobalAction] = useState<GlobalAction | null>(null)
  const [runningEpisodeAction, setRunningEpisodeAction] = useState<{ episodeId: string; action: EpisodeAction } | null>(null)

  const { progress } = useCourseProgress(courseId)

  const wsUrl = useMemo(() => toWsUrl(API_BASE, courseId), [courseId])
  const { connected, messages } = useWebSocket(wsUrl)

  const load = async () => {
    try {
      const data = await getCourse(courseId)
      if (mounted.current) {
        setCourse(data)
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
    const timer = setInterval(() => {
      void load()
    }, 4000)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const runGlobalAction = async (action: GlobalAction, title: string, fn: () => Promise<unknown>) => {
    setRunningGlobalAction(action)
    setStatusNote(`${title} started...`)
    setError(null)
    try {
      const result = await fn()
      const payload = result as { mode?: string; status?: string }
      if (mounted.current) {
        setStatusNote(`${title} ${payload?.mode ? `(${payload.mode})` : ''} ${payload?.status ?? 'done'}`.trim())
        await load()
      }
    } catch (err) {
      if (mounted.current) {
        setError((err as Error).message)
        setStatusNote(`${title} failed`)
      }
    } finally {
      if (mounted.current) setRunningGlobalAction(null)
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
          if (mounted.current) setStatusNote(uploadResult.debug_halt ? 'Upload stopped in debug mode: similar episode exists.' : 'Upload skipped: exists on target.')
          if (mounted.current) await load()
          return
        }
        if (uploadResult.summary) {
          const summary = uploadResult.summary
          if (mounted.current) setStatusNote(`Uploaded=${summary.run_uploaded}, Failed=${summary.run_failed}, Skipped=${summary.run_skipped_existing}`)
          if (mounted.current) await load()
          return
        }
      } else if (action === 'translate') {
        await translateEpisodeTitle(episodeId)
      } else {
        await retryEpisode(episodeId)
      }
      if (mounted.current) {
        setStatusNote(`Action completed: ${action}`)
        await load()
      }
    } catch (err) {
      if (mounted.current) {
        setError((err as Error).message)
        setStatusNote(`${action} failed.`)
      }
    } finally {
      if (mounted.current) setRunningEpisodeAction(null)
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
    if (!aiCourseContentHtml) return
    try {
      await navigator.clipboard.writeText(aiCourseContentHtml)
      setCopyHint('Copied!')
      setTimeout(() => { if (mounted.current) setCopyHint('Copy to Clipboard') }, 2000)
    } catch {
      setCopyHint('Copy Failed')
      setTimeout(() => { if (mounted.current) setCopyHint('Copy to Clipboard') }, 2000)
    }
  }

  if (loading) {
    return <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading course workspace...</div>
  }

  if (!course) {
    return <div className="operation-banner warn" style={{ margin: '2rem' }}>{error ?? 'Course not found in database.'}</div>
  }

  return (
    <div className="grid">
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <div className="row-between" style={{ alignItems: 'flex-start' }}>
          <div className="stack" style={{ gap: '0.2rem' }}>
            <h1 style={{ fontSize: '1.8rem' }}>{course.title_en ?? 'Untitled Course'}</h1>
            <p dir="rtl" style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text)' }}>{course.title_fa ?? 'عنوان اصلی نامشخص'}</p>
            <div className="course-meta" style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
              <span className="badge badge-muted">{course.source_platform ?? 'Unknown'}</span>
              <span className="badge badge-muted">Instructor: {course.instructor ?? 'TBD'}</span>
            </div>
          </div>
          <StatusBadge status={course.status} />
        </div>

        <ProgressBar value={progress?.progress_percent ?? 0} />

        {activeEpisode && (
          <div className="operation-banner" style={{ background: 'var(--accent-soft)', borderColor: 'rgba(14,165,233,0.3)', color: 'var(--accent-hover)' }}>
            <strong>Active Process:</strong> Episode {String(activeEpisode.episode_number ?? '-').padStart(3, '0')} - {activeEpisode.title_en ?? '-'}
            <span style={{ opacity: 0.8, marginLeft: '0.5rem' }}>&mdash; {episodeCurrentOperation(activeEpisode)}</span>
          </div>
        )}

        {course.debug_mode && (
          <div className="operation-banner warn">
            <strong>Debug Mode Active:</strong> Only the first episode will be passed through the pipeline.
          </div>
        )}

        {statusNote && <div className="status-note">{statusNote}</div>}

        <div className="row" style={{ marginTop: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <button
            className={`btn secondary ${runningGlobalAction === 'toggle_debug' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('toggle_debug', 'Toggle debug', () => toggleDebug(courseId))}
          >
            {course.debug_mode ? 'Disable Debug Mode' : 'Enable Debug Mode'}
          </button>

          <button
            className={`btn ${runningGlobalAction === 'start_download' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('start_download', 'Pipeline', () => startProcessing(courseId))}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            Full Pipeline Run
          </button>

          <button
            className={`btn secondary ${runningGlobalAction === 'process_subtitles' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('process_subtitles', 'Subtitles', () => processSubtitles(courseId))}
          >
            Process Subtitles
          </button>

          <button
            className={`btn ${runningGlobalAction === 'ai_translate' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('ai_translate', 'Translating', () => aiTranslate(courseId))}
            style={{ background: 'var(--success)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 5h16" /><path d="M7 5c0 5 2 9 5 12" /><path d="M17 5c0 3-1 6-3 8" /><path d="M9 17h8" /><path d="M13 13l4 8" /></svg>
            Auto Translate
          </button>

          <button
            className={`btn secondary ${runningGlobalAction === 'ai_course_content' ? 'running' : ''}`}
            style={{ background: '#f59e0b', color: '#fff', border: 'none' }}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('ai_course_content', 'AI Write', () => generateCourseAiContent(courseId))}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" /></svg>
            Generate SEO Description
          </button>
        </div>

        {error && <div className="operation-banner warn" style={{ marginTop: '1rem' }}>{error}</div>}
      </section>

      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h2 style={{ fontSize: '1.4rem' }}>Episodes Workspace</h2>
        <EpisodeTable episodes={course.episodes} onAction={runEpisodeAction} runningAction={runningEpisodeAction} />
      </section>

      {hasExpiredLinks && (
        <section className="panel stack" style={{ border: '1px solid var(--danger-soft)' }}>
          <div className="operation-banner warn">
            <strong>Link Expiration Warning:</strong> Origin download links have expired. Please paste a fresh list immediately.
          </div>
          <button type="button" className="btn warn" style={{ alignSelf: 'flex-start' }} onClick={jumpToLinkManager}>
            Revive Links
          </button>
        </section>
      )}

      <div className="grid cols-2">
        <div className="stack" style={{ gap: '1.5rem' }}>
          <LinkManager courseId={courseId} showExpiredNotice={hasExpiredLinks} />

          <section className="panel stack">
            <h3 style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>Generated SEO Syllabus</h3>
            {aiCourseContent ? (
              <div className="stack ai-content" dir="rtl" style={{ background: 'var(--bg)', padding: '1.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                <div className="stack" style={{ gap: 6 }}>
                  <h4>شرح دوره</h4>
                  <p className="overview-text">{aiCourseContent.course_overview}</p>
                </div>
                <div className="grid cols-2" style={{ gap: '2rem', marginTop: '1rem' }}>
                  <div className="stack" style={{ gap: 6 }}>
                    <h4>اهداف دوره</h4>
                    <ul className="bullet-list">
                      {aiCourseContent.course_goals.map((item, index) => <li key={index}>{item}</li>)}
                    </ul>
                  </div>
                  <div className="stack" style={{ gap: 6 }}>
                    <h4>پیش نیاز ها</h4>
                    <ul className="bullet-list">
                      {aiCourseContent.prerequisites.map((item, index) => <li key={index}>{item}</li>)}
                    </ul>
                    <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>{aiCourseContent.prerequisites_description}</p>
                  </div>
                </div>
                <div className="stack" style={{ gap: 6, marginTop: '1rem' }}>
                  <h4>مسیری که طی میکنید</h4>
                  <ul className="bullet-list" style={{ columns: 2 }}>
                    {aiCourseContent.what_you_will_learn.map((item, index) => <li key={index}>{item}</li>)}
                  </ul>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>No syllabus generated yet. Run the 'Generate SEO Description' task.</p>
            )}
          </section>
        </div>

        <div className="stack" style={{ gap: '1.5rem' }}>
          <section className="panel stack" style={{ flex: 1 }}>
            <div className="row-between">
              <h3 style={{ fontSize: '1.2rem' }}>Raw Export</h3>
              <button className="btn secondary tiny" onClick={copyHtmlPayload} disabled={!aiCourseContentHtml}>
                {copyHint}
              </button>
            </div>
            <div className="html-copy-box" style={{ flex: 1, minHeight: '200px', cursor: aiCourseContentHtml ? 'copy' : 'default' }} onClick={copyHtmlPayload}>
              {aiCourseContentHtml ? <pre>{aiCourseContentHtml}</pre> : <div style={{ opacity: 0.5, padding: '2rem', textAlign: 'center' }}>Awaiting structural payload...</div>}
            </div>
          </section>

          <div className="panel stack">
            <div className="row-between">
              <h3 style={{ fontSize: '1.2rem' }}>Event Telemetry</h3>
              <div className="row">
                <span className="dot" style={{ background: connected ? 'var(--success)' : 'var(--danger)' }} />
                <span style={{ fontSize: '0.8rem', color: connected ? 'var(--success)' : 'var(--danger)' }}>{connected ? 'Streaming' : 'Offline'}</span>
              </div>
            </div>
            <DebugConsole connected={connected} messages={messages} />
          </div>
        </div>
      </div>
    </div>
  )
}
