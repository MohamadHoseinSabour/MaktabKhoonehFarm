import { Fragment, ReactNode, useState } from 'react'

import { Episode } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type EpisodeActionType = 'download' | 'process' | 'upload' | 'retry' | 'translate'

type Props = {
  episodes: Episode[]
  onAction: (episodeId: string, action: EpisodeActionType) => void
  runningAction: { episodeId: string; action: EpisodeActionType } | null
}

const STATUS_PERCENT: Record<string, number> = {
  pending: 0,
  downloading: 35,
  downloaded: 60,
  processing: 78,
  processed: 90,
  uploading: 95,
  uploaded: 100,
  skipped: 100,
  not_available: 100,
  error: 0,
}

function normalizePercent(status: string) {
  return STATUS_PERCENT[status] ?? 0
}

function episodeProgress(episode: Episode) {
  const values = [episode.video_status, episode.subtitle_status, episode.exercise_status].map(normalizePercent)
  return Math.round(values.reduce((acc, item) => acc + item, 0) / values.length)
}

function activeOperation(episode: Episode) {
  if (episode.video_status === 'downloading') return 'Downloading video'
  if (episode.subtitle_status === 'downloading') return 'Downloading subtitle'
  if (episode.exercise_status === 'downloading') return 'Downloading exercise'
  if (episode.video_status === 'processing' || episode.subtitle_status === 'processing' || episode.exercise_status === 'processing') {
    return 'Processing'
  }
  if (episode.video_status === 'uploading' || episode.subtitle_status === 'uploading' || episode.exercise_status === 'uploading') {
    return 'Uploading'
  }
  if (episode.video_status === 'error' || episode.subtitle_status === 'error' || episode.exercise_status === 'error') {
    return episode.error_message ? `Error: ${episode.error_message}` : 'Error'
  }
  if (episode.video_status === 'uploaded' && (episode.subtitle_status === 'uploaded' || episode.subtitle_status === 'not_available')) {
    return 'Uploaded'
  }
  return 'Idle'
}

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
            <th>Title EN</th>
            <th>Title FA</th>
            <th>Video</th>
            <th>Sub</th>
            <th>Ex</th>
            <th>Progress</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => {
            const progress = episodeProgress(episode)
            const operation = activeOperation(episode)
            const isRunning = runningAction?.episodeId === episode.id
            const isExpanded = !!expandedFiles[episode.id]

            return (
              <Fragment key={episode.id}>
                <tr key={episode.id}>
                  <td>{episode.episode_number != null ? String(episode.episode_number).padStart(3, '0') : '-'}</td>
                  <td>{episode.title_en ?? '-'}</td>
                  <td dir="rtl">{episode.title_fa ?? '-'}</td>
                  <td><StatusBadge status={episode.video_status} /></td>
                  <td><StatusBadge status={episode.subtitle_status} /></td>
                  <td><StatusBadge status={episode.exercise_status} /></td>
                  <td>
                    <div className="stack" style={{ gap: 6 }}>
                      <strong>{progress}%</strong>
                      <span className="operation-hint">{operation}</span>
                    </div>
                  </td>
                  <td>
                    <div className="row action-icons">
                      <IconButton
                        label={isRunning && runningAction?.action === 'download' ? 'Downloading...' : 'Download'}
                        className={isRunning && runningAction?.action === 'download' ? 'running' : ''}
                        disabled={isRunning}
                        onClick={() => onAction(episode.id, 'download')}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>
                      </IconButton>

                      <IconButton
                        label={isRunning && runningAction?.action === 'process' ? 'Processing...' : 'Process'}
                        className={`secondary ${isRunning && runningAction?.action === 'process' ? 'running' : ''}`}
                        disabled={isRunning}
                        onClick={() => onAction(episode.id, 'process')}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-.4-1 1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1-.4 1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 .4 1 1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1 .4H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1 .4 1.7 1.7 0 0 0-.6 1z"/></svg>
                      </IconButton>

                      <IconButton
                        label={isRunning && runningAction?.action === 'upload' ? 'Uploading...' : 'Upload'}
                        className={isRunning && runningAction?.action === 'upload' ? 'running' : ''}
                        disabled={isRunning}
                        onClick={() => onAction(episode.id, 'upload')}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M12 21V9"/><path d="M7 14l5-5 5 5"/><path d="M5 3h14"/></svg>
                      </IconButton>

                      <IconButton
                        label="Retry"
                        className={`warn ${isRunning && runningAction?.action === 'retry' ? 'running' : ''}`}
                        disabled={isRunning}
                        onClick={() => onAction(episode.id, 'retry')}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M3 12a9 9 0 0 1 15.55-6.36L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.55 6.36L3 16"/><path d="M3 21v-5h5"/></svg>
                      </IconButton>

                      <IconButton
                        label={isRunning && runningAction?.action === 'translate' ? 'Translating...' : 'Translate title'}
                        className={`secondary ${isRunning && runningAction?.action === 'translate' ? 'running' : ''}`}
                        disabled={isRunning}
                        onClick={() => onAction(episode.id, 'translate')}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M4 5h16"/><path d="M7 5c0 5 2 9 5 12"/><path d="M17 5c0 3-1 6-3 8"/><path d="M9 17h8"/><path d="M13 13l4 8"/></svg>
                      </IconButton>

                      <IconButton
                        label={isExpanded ? 'Hide files' : 'Show files'}
                        className="secondary"
                        disabled={false}
                        onClick={() => toggleFiles(episode.id)}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
                      </IconButton>
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="files-row">
                    <td colSpan={8}>
                      <div className="files-grid">
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
                        <div className="files-box">
                          <strong>Exercise</strong>
                          <p>Filename: {episode.exercise_filename ?? '-'}</p>
                          <p>Local: {episode.exercise_local_path ?? '-'}</p>
                          <p className="wrap">URL: {episode.exercise_download_url ?? '-'}</p>
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
