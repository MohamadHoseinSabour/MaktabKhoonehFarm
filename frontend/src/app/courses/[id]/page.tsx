'use client'

import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
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
  downloadEpisode,
  generateCourseAiContent,
  getCourse,
  Episode,
  processEpisode,
  retryEpisode,
  startProcessing,
  toggleDebug,
  translateEpisodeTitle,
  UploadEpisodeResponse,
  uploadEpisode,
  validateUploadCookies,
  getSettings,
} from '@/services/api'

function toWsUrl(base: string, courseId: string) {
  const wsBase = base.replace(/^http/i, 'ws')
  return `${wsBase}/ws/courses/${courseId}/live-logs/`
}

type GlobalAction = 'toggle_debug' | 'start_download' | 'auto_pipeline' | 'ai_course_content'
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

/* ---------- Auto-pipeline: download -> process -> translate -> upload ---------- */

async function runAutoPipelineForEpisode(
  episode: Episode,
  onStatus: (msg: string) => void,
): Promise<{ ok: boolean; error?: string }> {
  const label = `قسمت ${String(episode.episode_number ?? '-').padStart(3, '0')}`

  // Step 1: Download (only if pending or error)
  if (['pending', 'error'].includes(episode.video_status)) {
    onStatus(`${label}: در حال دانلود...`)
    try {
      await downloadEpisode(episode.id)
    } catch (err) {
      return { ok: false, error: `${label}: خطا در دانلود - ${(err as Error).message}` }
    }
  }

  // Step 2: Process (only if downloaded)
  if (['downloaded', 'pending', 'error'].includes(episode.video_status) || episode.subtitle_status === 'downloaded') {
    onStatus(`${label}: در حال پردازش...`)
    try {
      await processEpisode(episode.id)
    } catch (err) {
      return { ok: false, error: `${label}: خطا در پردازش - ${(err as Error).message}` }
    }
  }

  // Step 3: Translate title (only if title_fa is missing)
  if (episode.title_en && !episode.title_fa) {
    onStatus(`${label}: ترجمه عنوان...`)
    try {
      await translateEpisodeTitle(episode.id)
    } catch {
      // Non-critical, continue
    }
  }

  // Step 4: Upload
  if (!['uploaded', 'uploading'].includes(episode.video_status)) {
    onStatus(`${label}: در حال آپلود...`)
    try {
      await uploadEpisode(episode.id)
    } catch (err) {
      return { ok: false, error: `${label}: خطا در آپلود - ${(err as Error).message}` }
    }
  }

  return { ok: true }
}

/* ---------- Status indicator dots ---------- */

function StatusDot({ ok, label }: { ok: boolean | null; label: string }) {
  const color = ok === null ? 'var(--text-muted)' : ok ? 'var(--success)' : 'var(--danger)'
  const text = ok === null ? 'بررسی نشده' : ok ? 'فعال' : 'غیرفعال'
  return (
    <div className="row" style={{ gap: 6 }} title={`${label}: ${text}`}>
      <span className="dot" style={{ background: color, width: 10, height: 10, animation: ok === null ? 'none' : undefined }} />
      <span style={{ fontSize: '0.75rem', color, fontWeight: 600 }}>{label}</span>
    </div>
  )
}

export default function CourseDetailPage() {
  const params = useParams<{ id: string }>()
  const courseId = params.id
  const mounted = useRef(true)
  const pipelineAbort = useRef(false)

  const [course, setCourse] = useState<Awaited<ReturnType<typeof getCourse>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState<string | null>(null)
  const [copyHint, setCopyHint] = useState<string>('Copy to Clipboard')
  const [runningGlobalAction, setRunningGlobalAction] = useState<GlobalAction | null>(null)
  const [runningEpisodeAction, setRunningEpisodeAction] = useState<{ episodeId: string; action: EpisodeAction } | null>(null)

  // Service status indicators
  const [cookiesOk, setCookiesOk] = useState<boolean | null>(null)
  const [aiApiOk, setAiApiOk] = useState<boolean | null>(null)

  const { progress } = useCourseProgress(courseId)

  const wsUrl = useMemo(() => toWsUrl(API_BASE, courseId), [courseId])
  const { connected, messages } = useWebSocket(wsUrl)

  const load = useCallback(async () => {
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
  }, [courseId])

  // Check cookie and AI API status on mount
  useEffect(() => {
    async function checkServices() {
      try {
        const result = await validateUploadCookies()
        if (mounted.current) setCookiesOk(result.valid)
      } catch {
        if (mounted.current) setCookiesOk(false)
      }

      try {
        const settings = await getSettings()
        const aiKey = settings.find((s) => s.key === 'openai_api_key')
        if (mounted.current) setAiApiOk(!!(aiKey && aiKey.value && aiKey.value.trim().length > 0))
      } catch {
        if (mounted.current) setAiApiOk(false)
      }
    }
    void checkServices()
  }, [])

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
  }, [courseId, load])

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

  const runAutoPipeline = async () => {
    if (!course) return
    setRunningGlobalAction('auto_pipeline')
    setError(null)
    pipelineAbort.current = false

    const episodesQueue = [...course.episodes]
      .sort((a, b) => (a.episode_number ?? 0) - (b.episode_number ?? 0))
      .filter((ep) => ep.video_status !== 'uploaded')

    if (episodesQueue.length === 0) {
      setStatusNote('همه اپیزودها قبلاً آپلود شده‌اند.')
      setRunningGlobalAction(null)
      return
    }

    setStatusNote(`شروع پردازش خودکار ${episodesQueue.length} اپیزود...`)

    let processed = 0
    let failed = 0
    for (const episode of episodesQueue) {
      if (pipelineAbort.current || !mounted.current) break

      const result = await runAutoPipelineForEpisode(episode, (msg) => {
        if (mounted.current) setStatusNote(msg)
      })

      if (result.ok) {
        processed++
      } else {
        failed++
        if (mounted.current) setError(result.error ?? 'خطای ناشناخته')
      }

      // Reload course data to get updated statuses
      if (mounted.current) await load()
    }

    if (mounted.current) {
      setStatusNote(`پردازش خودکار تمام شد. موفق: ${processed} | ناموفق: ${failed}`)
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
    return <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>در حال بارگذاری اطلاعات دوره...</div>
  }

  if (!course) {
    return <div className="operation-banner warn" style={{ margin: '2rem' }}>{error ?? 'دوره در دیتابیس یافت نشد.'}</div>
  }

  return (
    <div className="grid">
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <div className="row-between" style={{ alignItems: 'flex-start' }}>
          <div className="stack" style={{ gap: '0.2rem' }}>
            <h1 style={{ fontSize: '1.8rem' }} dir="ltr">{course.title_en ?? 'بدون عنوان'}</h1>
            <p dir="rtl" style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text)' }}>{course.title_fa ?? 'عنوان اصلی نامشخص'}</p>
            <div className="course-meta" style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
              <span className="badge badge-muted">{course.source_platform ?? 'نامشخص'}</span>
              <span className="badge badge-muted">مدرس: {course.instructor ?? 'تعیین نشده'}</span>
            </div>
          </div>
          <StatusBadge status={course.status} />
        </div>

        <ProgressBar value={progress?.progress_percent ?? 0} />

        {activeEpisode && (
          <div className="operation-banner" style={{ background: 'var(--accent-soft)', borderColor: 'rgba(14,165,233,0.3)', color: 'var(--accent-hover)' }}>
            <strong>پردازش فعال:</strong> قسمت {String(activeEpisode.episode_number ?? '-').padStart(3, '0')} - {activeEpisode.title_en ?? '-'}
            <span style={{ opacity: 0.8, marginRight: '0.5rem' }}>&mdash; {episodeCurrentOperation(activeEpisode)}</span>
          </div>
        )}

        {course.debug_mode && (
          <div className="operation-banner warn">
            <strong>حالت دیباگ فعال است:</strong> فقط قسمت اول برای پردازش به ربات ارسال خواهد شد.
          </div>
        )}

        {statusNote && <div className="status-note">{statusNote}</div>}

        <div className="row" style={{ marginTop: '1rem', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
          <button
            className={`btn secondary ${runningGlobalAction === 'toggle_debug' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('toggle_debug', 'Toggle debug', () => toggleDebug(courseId))}
          >
            {course.debug_mode ? 'غیرفعال‌سازی دیباگ' : 'فعال‌سازی دیباگ'}
          </button>

          <button
            className={`btn ${runningGlobalAction === 'start_download' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={() => runGlobalAction('start_download', 'Pipeline', () => startProcessing(courseId))}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            شروع دانلود
          </button>

          <button
            className={`btn ${runningGlobalAction === 'auto_pipeline' ? 'running' : ''}`}
            disabled={runningGlobalAction !== null}
            onClick={runAutoPipeline}
            style={{ background: 'var(--success)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg>
            پردازش کامل (خودکار)
          </button>

          {/* Status indicator dots */}
          <div style={{ marginRight: 'auto', display: 'flex', gap: '1rem', alignItems: 'center', paddingRight: '0.5rem' }}>
            <StatusDot ok={cookiesOk} label="کوکی سایت" />
            <StatusDot ok={aiApiOk} label="API هوش مصنوعی" />
          </div>
        </div>

        {error && <div className="operation-banner warn" style={{ marginTop: '1rem' }}>{error}</div>}
      </section>

      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h2 style={{ fontSize: '1.4rem' }}>فهرست قسمت‌ها</h2>
        <EpisodeTable episodes={course.episodes} onAction={runEpisodeAction} runningAction={runningEpisodeAction} />
      </section>

      {hasExpiredLinks && (
        <section className="panel stack" style={{ border: '1px solid var(--danger-soft)' }}>
          <div className="operation-banner warn">
            <strong>اخطار انقضای لینک:</strong> لینک‌های دانلود منبع منقضی شده‌اند. لطفاً بلافاصله لیست جدیدی را جایگذاری کنید.
          </div>
          <button type="button" className="btn warn" style={{ alignSelf: 'flex-start' }} onClick={jumpToLinkManager}>
            بازنشانی لینک‌ها
          </button>
        </section>
      )}

      <div className="grid cols-2">
        <div className="stack" style={{ gap: '1.5rem' }}>
          <LinkManager courseId={courseId} showExpiredNotice={hasExpiredLinks} />

          <section className="panel stack">
            <h3 style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>محتوای تولید شده (سئو)</h3>
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
              <p style={{ color: 'var(--text-muted)' }}>هنوز محتوایی تولید نشده است. روی &quot;تولید سرفصل (SEO)&quot; کلیک کنید.</p>
            )}
          </section>
        </div>

        <div className="stack" style={{ gap: '1.5rem' }}>
          <section className="panel stack" style={{ flex: 1 }}>
            <div className="row-between">
              <h3 style={{ fontSize: '1.2rem' }}>خروجی خام</h3>
              <button className="btn secondary tiny" onClick={copyHtmlPayload} disabled={!aiCourseContentHtml}>
                {copyHint}
              </button>
            </div>
            <div className="html-copy-box" style={{ flex: 1, minHeight: '200px', cursor: aiCourseContentHtml ? 'copy' : 'default' }} onClick={copyHtmlPayload}>
              {aiCourseContentHtml ? <pre dir="ltr">{aiCourseContentHtml}</pre> : <div style={{ opacity: 0.5, padding: '2rem', textAlign: 'center' }}>در انتظار ساختاردهی خروجی...</div>}
            </div>
          </section>

          <div className="panel stack">
            <div className="row-between">
              <h3 style={{ fontSize: '1.2rem' }}>وضعیت ارتباط</h3>
              <div className="row">
                <span className="dot" style={{ background: connected ? 'var(--success)' : 'var(--danger)' }} />
                <span style={{ fontSize: '0.8rem', color: connected ? 'var(--success)' : 'var(--danger)' }}>{connected ? 'متصل' : 'آفلاین'}</span>
              </div>
            </div>
            <DebugConsole connected={connected} messages={messages} />
          </div>
        </div>
      </div>
    </div>
  )
}
