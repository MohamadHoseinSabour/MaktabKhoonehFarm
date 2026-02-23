const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export type Course = {
  id: string
  source_url: string
  slug?: string | null
  title_en?: string | null
  title_fa?: string | null
  instructor?: string | null
  source_platform?: string | null
  lectures_count?: number | null
  status: string
  debug_mode: boolean
  created_at: string
  updated_at: string
}

export type Episode = {
  id: string
  episode_number?: number | null
  title_en?: string | null
  title_fa?: string | null
  video_status: string
  subtitle_status: string
  exercise_status: string
  video_filename?: string | null
  subtitle_filename?: string | null
  exercise_filename?: string | null
}

export type DashboardStats = {
  total_courses: number
  active_downloads: number
  queued_tasks: number
  failed_tasks_24h: number
}

export type CourseProgress = {
  course_id: string
  total_episodes: number
  downloaded_videos: number
  processed_subtitles: number
  failed_items: number
  progress_percent: number
}

export type TaskLog = {
  id: string
  level: string
  message: string
  task_type: string
  status: string
  created_at: string
}

export async function getCourses() {
  return request<Course[]>('/api/courses/')
}

export async function getCourse(id: string) {
  return request<Course & { episodes: Episode[]; description_en?: string; description_fa?: string }>(`/api/courses/${id}/`)
}

export async function createCourse(sourceUrl: string, debugMode = false) {
  return request<Course>('/api/courses/', {
    method: 'POST',
    body: JSON.stringify({ source_url: sourceUrl, debug_mode: debugMode }),
  })
}

export async function toggleDebug(courseId: string) {
  return request<{ course_id: string; debug_mode: boolean }>(`/api/courses/${courseId}/toggle-debug/`, {
    method: 'POST',
  })
}

export async function startProcessing(courseId: string) {
  return request<{ task_id: string; status: string }>(`/api/courses/${courseId}/process/`, {
    method: 'POST',
  })
}

export async function processSubtitles(courseId: string) {
  return request<{ task_id: string; status: string }>(`/api/courses/${courseId}/process-subtitles/`, {
    method: 'POST',
  })
}

export async function aiTranslate(courseId: string) {
  return request<{ task_id: string; status: string }>(`/api/courses/${courseId}/ai-translate/`, {
    method: 'POST',
  })
}

export async function getEpisodes(courseId: string) {
  return request<Episode[]>(`/api/courses/${courseId}/episodes/`)
}

export async function getDashboardStats() {
  return request<DashboardStats>('/api/dashboard/stats/')
}

export async function getCourseProgress(courseId: string) {
  return request<CourseProgress>(`/api/courses/${courseId}/progress/`)
}

export async function getCourseLogs(courseId: string) {
  return request<TaskLog[]>(`/api/courses/${courseId}/logs/`)
}

export async function updateLinks(courseId: string, rawLinks: string) {
  return request(`/api/courses/${courseId}/links/`, {
    method: 'POST',
    body: JSON.stringify({ raw_links: rawLinks, apply_changes: true }),
  })
}

export { API_BASE }