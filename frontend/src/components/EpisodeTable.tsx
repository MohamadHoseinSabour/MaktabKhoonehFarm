import { Fragment, ReactNode, useState } from 'react'

import { Episode } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type EpisodeActionType = 'download' | 'process' | 'upload' | 'retry' | 'translate'

type Props = {
  episodes: Episode[]
  onAction: (episodeId: string, action: EpisodeActionType) => void
  runningAction: { episodeId: string; action: EpisodeActionType } | null
}

/* ---------- status helpers ---------- */

const STATUS_LABELS: Record<string, string> = {
  pending: 'در انتظار',
  downloading: 'در حال دانلود',
  downloaded: 'دانلود شده',
  processing: 'در حال پردازش',
  processed: 'پردازش شده',
  uploading: 'در حال آپلود',
  uploaded: 'آپلود شده',
  skipped: 'رد شده',
  not_available: 'موجود نیست',
  error: 'خطا',
}

/** Determine a single human-readable status for the episode. */
function episodeStatusText(episode: Episode): string {
  const vs = episode.video_status
  const ss = episode.subtitle_status

  // Active operations take priority
  if (vs === 'uploading' || ss === 'uploading') return 'در حال آپلود'
  if (vs === 'processing' || ss === 'processing') return 'در حال پردازش'
  if (vs === 'downloading' || ss === 'downloading') return 'در حال دانلود'

  // Error state
  if (vs === 'error' || ss === 'error') {
    return episode.error_message ? `خطا: ${episode.error_message}` : 'خطا'
  }

  // Completed
  if (vs === 'uploaded' && (ss === 'uploaded' || ss === 'not_available' || ss === 'skipped')) {
    return 'آپلود شده ✓'
  }

  // Partially done
  if (vs === 'processed' || ss === 'processed') return 'پردازش شده'
  if (vs === 'downloaded' || ss === 'downloaded') return 'دانلود شده'

  return STATUS_LABELS[vs] ?? 'در انتظار'
}

/** Returns a CSS class for the status badge color. */
function statusClass(episode: Episode): string {
  const vs = episode.video_status
  const ss = episode.subtitle_status

  if (vs === 'uploading' || ss === 'uploading' || vs === 'downloading' || ss === 'downloading' || vs === 'processing' || ss === 'processing') {
    return 'status-active'
  }
  if (vs === 'error' || ss === 'error') return 'status-error'
  if (vs === 'uploaded' && (ss === 'uploaded' || ss === 'not_available' || ss === 'skipped')) return 'status-done'
  if (vs === 'processed' || vs === 'downloaded') return 'status-partial'
  return 'status-pending'
}

/* ---------- action availability ---------- */

/** Can this episode be downloaded? Only if video hasn't been downloaded yet. */
function canDownload(episode: Episode): boolean {
  return ['pending', 'error'].includes(episode.video_status)
}

/** Can this episode be processed? Only if video has been downloaded. */
function canProcess(episode: Episode): boolean {
  return episode.video_status === 'downloaded' ||
    (episode.video_status === 'processed' && episode.subtitle_status === 'downloaded')
}

/** Can this episode be uploaded? Only if video has been processed. */
function canUpload(episode: Episode): boolean {
  return (
    episode.video_status === 'processed' ||
    episode.video_status === 'uploaded' ||
    episode.subtitle_status === 'processed'
  )
}

/** Can retry? Only when there's an error. */
function canRetry(episode: Episode): boolean {
  return episode.video_status === 'error' || episode.subtitle_status === 'error' || episode.exercise_status === 'error'
}

/** Can translate? Only when title_fa is missing and title_en exists. */
function canTranslate(episode: Episode): boolean {
  return !!episode.title_en && !episode.title_fa
}

/* ---------- UI components ---------- */

function IconButton({
  label,
  onClick,
  className,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  className?: string
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <button type="button" className={`icon-btn ${className ?? ''}`} title={label} aria-label={label} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}

export function EpisodeTable({ episodes, onAction, runningAction }: Props) {
  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({})

  const toggleFiles = (episodeId: string) => {
    setExpandedFiles((prev) => ({ ...prev, [episodeId]: !prev[episodeId] }))
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>عنوان اصلی</th>
            <th>عنوان فارسی</th>
            <th>ویدیو</th>
            <th>زیرنویس</th>
            <th>وضعیت</th>
            <th>عملیات</th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => {
            const isRunning = runningAction?.episodeId === episode.id
            const isExpanded = !!expandedFiles[episode.id]

            const showDownload = canDownload(episode)
            const showProcess = canProcess(episode)
            const showUpload = canUpload(episode)
            const showRetry = canRetry(episode)
            const showTranslate = canTranslate(episode)

            const vs = episode.video_status
            const ss = episode.subtitle_status
            const isDone = vs === 'uploaded' && (ss === 'uploaded' || ss === 'not_available' || ss === 'skipped')
            const isActive = ['downloading', 'processing', 'uploading'].includes(vs) || ['downloading', 'processing', 'uploading'].includes(ss)
            const rowClass = isDone ? 'ep-row-done' : isActive ? 'ep-row-active' : ''

            return (
              <Fragment key={episode.id}>
                <tr key={episode.id} className={rowClass}>
                  <td>{episode.episode_number != null ? String(episode.episode_number).padStart(3, '0') : '-'}</td>
                  <td dir="ltr">{episode.title_en ?? '-'}</td>
                  <td dir="rtl">{episode.title_fa ?? '-'}</td>
                  <td><StatusBadge status={episode.video_status} /></td>
                  <td><StatusBadge status={episode.subtitle_status} /></td>
                  <td>
                    <span className={`episode-status ${statusClass(episode)}`}>
                      {episodeStatusText(episode)}
                    </span>
                  </td>
                  <td>
                    <div className="row action-icons" dir="ltr">
                      {showDownload && (
                        <IconButton
                          label={isRunning && runningAction?.action === 'download' ? 'در حال دانلود...' : 'دانلود'}
                          className={isRunning && runningAction?.action === 'download' ? 'running' : ''}
                          disabled={isRunning}
                          onClick={() => onAction(episode.id, 'download')}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg>
                        </IconButton>
                      )}

                      {showProcess && (
                        <IconButton
                          label={isRunning && runningAction?.action === 'process' ? 'در حال پردازش...' : 'پردازش فایل'}
                          className={`secondary ${isRunning && runningAction?.action === 'process' ? 'running' : ''}`}
                          disabled={isRunning}
                          onClick={() => onAction(episode.id, 'process')}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-.4-1 1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1-.4 1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 .4 1 1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1 .4H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1 .4 1.7 1.7 0 0 0-.6 1z" /></svg>
                        </IconButton>
                      )}

                      {showUpload && (
                        <IconButton
                          label={isRunning && runningAction?.action === 'upload' ? 'درحال آپلود...' : 'شروع آپلود'}
                          className={isRunning && runningAction?.action === 'upload' ? 'running' : ''}
                          disabled={isRunning}
                          onClick={() => onAction(episode.id, 'upload')}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M12 21V9" /><path d="M7 14l5-5 5 5" /><path d="M5 3h14" /></svg>
                        </IconButton>
                      )}

                      {showRetry && (
                        <IconButton
                          label="تلاش مجدد"
                          className={`warn ${isRunning && runningAction?.action === 'retry' ? 'running' : ''}`}
                          disabled={isRunning}
                          onClick={() => onAction(episode.id, 'retry')}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M3 12a9 9 0 0 1 15.55-6.36L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15.55 6.36L3 16" /><path d="M3 21v-5h5" /></svg>
                        </IconButton>
                      )}

                      {showTranslate && (
                        <IconButton
                          label={isRunning && runningAction?.action === 'translate' ? 'در حال ترجمه...' : 'ترجمه عنوان'}
                          className={`secondary ${isRunning && runningAction?.action === 'translate' ? 'running' : ''}`}
                          disabled={isRunning}
                          onClick={() => onAction(episode.id, 'translate')}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M4 5h16" /><path d="M7 5c0 5 2 9 5 12" /><path d="M17 5c0 3-1 6-3 8" /><path d="M9 17h8" /><path d="M13 13l4 8" /></svg>
                        </IconButton>
                      )}

                      <IconButton
                        label={isExpanded ? 'مخفی کردن جزئیات فایل' : 'نمایش جزئیات فایل‌ها'}
                        className="secondary"
                        disabled={false}
                        onClick={() => toggleFiles(episode.id)}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" /></svg>
                      </IconButton>
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="files-row">
                    <td colSpan={7}>
                      <div className="files-grid" dir="ltr" style={{ textAlign: 'left' }}>
                        <div className="files-box">
                          <strong>Video</strong>
                          <p>Filename: {episode.video_filename ?? '-'}</p>
                          <p>Local: {episode.video_local_path ?? '-'}</p>
                          <p className="wrap">URL: {episode.video_download_url ?? '-'}</p>
                        </div>
                        <div className="files-box">
                          <strong>Subtitle</strong>
                          <p>Filename: {episode.subtitle_filename ?? '-'}</p>
                          <p>Local: {episode.subtitle_local_path ?? '-'}</p>
                          <p>Processed: {episode.subtitle_processed_path ?? '-'}</p>
                          <p className="wrap">URL: {episode.subtitle_download_url ?? '-'}</p>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
