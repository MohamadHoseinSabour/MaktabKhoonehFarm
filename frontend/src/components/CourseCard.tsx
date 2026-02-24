import Link from 'next/link'

import { Course } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type Props = {
  course: Course
}

export function CourseCard({ course }: Props) {
  const thumbnail = course.thumbnail_url ?? null
  const descEn = course.description_en?.trim()
  const descFa = course.description_fa?.trim()
  const metadata = (course.extra_metadata ?? {}) as Record<string, unknown>
  const uploadSummary = (metadata.upload_summary ?? null) as Record<string, unknown> | null
  const uploadedTotal = typeof uploadSummary?.uploaded_total === 'number' ? uploadSummary.uploaded_total : 0
  const totalEpisodes =
    typeof uploadSummary?.total_episodes === 'number'
      ? uploadSummary.total_episodes
      : (course.lectures_count ?? 0)
  const failedTotal = typeof uploadSummary?.failed_total === 'number' ? uploadSummary.failed_total : 0
  const uploadState = typeof uploadSummary?.state === 'string' ? uploadSummary.state : ''
  const hasUploadSuccess = uploadState === 'completed' && failedTotal === 0 && uploadedTotal > 0
  const hasUploadError = failedTotal > 0 || uploadState === 'failed' || uploadState === 'partial_error'
  const cardClass = `course-card${hasUploadSuccess ? ' upload-success' : ''}${hasUploadError ? ' upload-failed' : ''}`

  return (
    <Link href={`/courses/${course.id}`} className={cardClass}>
      <div className="course-thumb">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbnail} alt={course.title_en ?? 'Course thumbnail'} />
        ) : (
          <div className="course-thumb-placeholder">No Thumbnail</div>
        )}
      </div>
      <div className="course-card-header">
        <h3>{course.title_en ?? 'Untitled Course'}</h3>
        <StatusBadge status={course.status} />
      </div>
      <p dir="rtl">{course.title_fa ?? 'عنوان فارسی موجود نیست'}</p>
      <p className="course-desc">{descEn ?? 'No English description scraped yet.'}</p>
      <p className="course-desc" dir="rtl">
        {descFa ?? 'توضیح فارسی هنوز استخراج نشده است.'}
      </p>
      <div className="course-meta">
        <span>{course.source_platform ?? 'Unknown Platform'}</span>
        <span>{course.instructor ?? 'Unknown Instructor'}</span>
        <span>{course.lectures_count ?? 0} lectures</span>
      </div>
      {uploadSummary && (
        <div className="stack" style={{ gap: 4 }}>
          {hasUploadSuccess && <p className="upload-state upload-state-success" dir="rtl">با موفقیت آپلود شد</p>}
          {hasUploadError && <p className="upload-state upload-state-error" dir="rtl">آپلود با خطا مواجه شده است</p>}
          <p className="upload-counter" dir="rtl">
            آپلود موفق: {uploadedTotal} / {totalEpisodes}
          </p>
        </div>
      )}
    </Link>
  )
}
