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

  return (
    <Link href={`/courses/${course.id}`} className="course-card">
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
    </Link>
  )
}
