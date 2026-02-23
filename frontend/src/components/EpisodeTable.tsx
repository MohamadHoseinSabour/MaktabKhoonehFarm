import { Episode } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type Props = {
  episodes: Episode[]
}

export function EpisodeTable({ episodes }: Props) {
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
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => (
            <tr key={episode.id}>
              <td>{episode.episode_number != null ? String(episode.episode_number).padStart(3, '0') : '-'}</td>
              <td>{episode.title_en ?? '-'}</td>
              <td dir="rtl">{episode.title_fa ?? '-'}</td>
              <td><StatusBadge status={episode.video_status} /></td>
              <td><StatusBadge status={episode.subtitle_status} /></td>
              <td><StatusBadge status={episode.exercise_status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
