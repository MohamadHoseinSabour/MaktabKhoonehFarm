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
  const totalEpisodes = typeof uploadSummary?.total_episodes === 'number'
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
          <img src={thumbnail} alt={course.title_en ?? 'تصویر دوره'} loading="lazy" />
        ) : (
          <div className="course-thumb-placeholder">
            <span>بدون تصویر</span>
          </div>
        )}
      </div>

      <div className="course-card-header">
        <h3 dir="ltr" style={{ textAlign: 'left' }}>{course.title_en ?? 'بدون عنوان'}</h3>
        <StatusBadge status={course.status} />
      </div>

      <p style={{ fontWeight: 600, color: 'var(--text)', fontSize: '0.95rem', marginTop: '0.2rem' }}>
        {course.title_fa ?? 'عنوان فارسی موجود نیست'}
      </p>

      <p className="course-desc">
        {descFa ?? 'توضیح فارسی هنوز استخراج نشده است.'}
      </p>
      <p className="course-desc" style={{ fontSize: '0.85rem' }} dir="ltr">
        {descEn ?? 'توضیح انگلیسی ثبت نشده است.'}
      </p>

      <div className="course-meta" style={{ paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
        <span>{course.source_platform ?? 'نامشخص'}</span>
        <span>{course.instructor ?? 'تعیین نشده'}</span>
        <span>{course.lectures_count ?? 0} جلسه</span>
      </div>

      {uploadSummary && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="row-between">
            {hasUploadSuccess && <span className="upload-state upload-state-success" dir="rtl">تکمیل شده</span>}
            {hasUploadError && <span className="upload-state upload-state-error" dir="rtl">با خطا مواجه شد</span>}
            {(!hasUploadSuccess && !hasUploadError) && <span className="upload-state" style={{ background: 'var(--bg)', color: 'var(--text-muted)' }} dir="rtl">در حال پردازش</span>}

            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)' }} dir="rtl">
              آپلود: {uploadedTotal} / {totalEpisodes}
            </span>
          </div>

          <div className="progress-wrap">
            <div
              className="progress-fill"
              style={{ width: `${totalEpisodes > 0 ? (uploadedTotal / totalEpisodes) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}
    </Link>
  )
}
