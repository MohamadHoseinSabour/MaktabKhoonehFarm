import { Episode } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type EpisodeActionType = 'download' | 'process' | 'upload' | 'retry'

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
    const details = (episode as Episode & { error_message?: string | null }).error_message
    return details ? `Error: ${details}` : 'Error'
  }
  if (episode.video_status === 'uploaded' && (episode.subtitle_status === 'uploaded' || episode.subtitle_status === 'not_available')) {
    return 'Uploaded'
  }
  return 'Idle'
}

export function EpisodeTable({ episodes, onAction, runningAction }: Props) {
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

            return (
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
                  <div className="row">
                    <button
                      className={`btn tiny ${isRunning && runningAction?.action === 'download' ? 'running' : ''}`}
                      disabled={isRunning}
                      onClick={() => onAction(episode.id, 'download')}
                    >
                      {isRunning && runningAction?.action === 'download' ? 'Downloading...' : 'Download'}
                    </button>
                    <button
                      className={`btn tiny secondary ${isRunning && runningAction?.action === 'process' ? 'running' : ''}`}
                      disabled={isRunning}
                      onClick={() => onAction(episode.id, 'process')}
                    >
                      {isRunning && runningAction?.action === 'process' ? 'Processing...' : 'Process'}
                    </button>
                    <button
                      className={`btn tiny ${isRunning && runningAction?.action === 'upload' ? 'running' : ''}`}
                      disabled={isRunning}
                      onClick={() => onAction(episode.id, 'upload')}
                    >
                      {isRunning && runningAction?.action === 'upload' ? 'Uploading...' : 'Upload'}
                    </button>
                    <button
                      className={`btn tiny warn ${isRunning && runningAction?.action === 'retry' ? 'running' : ''}`}
                      disabled={isRunning}
                      onClick={() => onAction(episode.id, 'retry')}
                    >
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
