import Link from 'next/link'

import { Course } from '@/services/api'
import { StatusBadge } from './StatusBadge'

type Props = {
  course: Course
}

export function CourseCard({ course }: Props) {
  return (
    <Link href={`/courses/${course.id}`} className="course-card">
      <div className="course-card-header">
        <h3>{course.title_en ?? 'Untitled Course'}</h3>
        <StatusBadge status={course.status} />
      </div>
      <p dir="rtl">{course.title_fa ?? '???? ?????'}</p>
      <div className="course-meta">
        <span>{course.source_platform ?? 'Unknown Platform'}</span>
        <span>{course.instructor ?? 'Unknown Instructor'}</span>
        <span>{course.lectures_count ?? 0} lectures</span>
      </div>
    </Link>
  )
}