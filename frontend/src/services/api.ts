const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

type ApiErrorPayload = {
  detail?: unknown
  message?: unknown
  error?: unknown
}

function normalizeErrorMessage(status: number, body: string): string {
  const fallback = `Request failed: ${status}`
  const trimmed = body.trim()
  if (!trimmed) {
    return fallback
  }

  try {
    const payload = JSON.parse(trimmed) as ApiErrorPayload
    const candidate = payload.detail ?? payload.message ?? payload.error
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim()
    }
  } catch {
    // Keep plain-text fallback below.
  }

  return trimmed || fallback
}

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
    throw new Error(normalizeErrorMessage(response.status, text))
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
  description_en?: string | null
  description_fa?: string | null
  thumbnail_url?: string | null
  thumbnail_local?: string | null
  instructor?: string | null
  source_platform?: string | null
  lectures_count?: number | null
  extra_metadata?: Record<string, unknown> | null
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
  video_download_url?: string | null
  video_local_path?: string | null
  video_status: string
  subtitle_download_url?: string | null
  subtitle_local_path?: string | null
  subtitle_status: string
  exercise_download_url?: string | null
  exercise_local_path?: string | null
  exercise_status: string
  video_filename?: string | null
  subtitle_filename?: string | null
  exercise_filename?: string | null
  subtitle_processed_path?: string | null
  error_message?: string | null
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

export type AICourseContent = {
  course_overview: string
  prerequisites: string[]
  prerequisites_description: string
  what_you_will_learn: string[]
  course_goals: string[]
}

export type UploadEpisodeResponse = {
  episode_id: string
  uploaded: string[]
  status?: string
  skip_existing?: boolean
  debug_halt?: boolean
  summary?: {
    state: string
    run_requested: number
    run_processed: number
    run_uploaded: number
    run_failed: number
    run_skipped_existing: number
    uploaded_total: number
    failed_total: number
    total_episodes: number
    updated_at: string
  }
  navigation?: Record<string, unknown>
}

export type Setting = {
  id: string
  key: string
  value: string
  category?: string | null
  description?: string | null
}

export async function getCourses() {
  return request<Course[]>('/api/courses/')
}

export async function deleteCourse(courseId: string) {
  return request<void>(`/api/courses/${courseId}/`, {
    method: 'DELETE',
  })
}

export async function getCourse(id: string) {
  return request<Course & { episodes: Episode[]; description_en?: string; description_fa?: string }>(`/api/courses/${id}/`)
}

export async function createCourse(sourceUrl: string, debugMode = true) {
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

export async function generateCourseAiContent(courseId: string) {
  return request<{ status: string; content: AICourseContent }>(`/api/courses/${courseId}/generate-ai-content/`, {
    method: 'POST',
  })
}

export async function getEpisodes(courseId: string) {
  return request<Episode[]>(`/api/courses/${courseId}/episodes/`)
}

export async function downloadEpisode(episodeId: string) {
  return request<{ episode_id: string; result: Record<string, string> }>(`/api/episodes/${episodeId}/download/`, {
    method: 'POST',
  })
}

export async function processEpisode(episodeId: string) {
  return request<{ episode_id: string; processed: string[] }>(`/api/episodes/${episodeId}/process/`, {
    method: 'POST',
  })
}

export async function uploadEpisode(episodeId: string) {
  return request<UploadEpisodeResponse>(`/api/episodes/${episodeId}/upload/`, {
    method: 'POST',
  })
}

export async function getSettings() {
  return request<Setting[]>('/api/settings/')
}

export async function saveSettings(items: Array<Pick<Setting, 'key' | 'value' | 'category' | 'description'>>) {
  return request<Setting[]>('/api/settings/', {
    method: 'PUT',
    body: JSON.stringify(items),
  })
}

export async function validateUploadCookies() {
  return request<{ valid: boolean; message: string }>('/api/upload-automation/validate-cookies/', {
    method: 'POST',
  })
}

export async function retryEpisode(episodeId: string) {
  return request<{ episode_id: string; reset: string[] }>(`/api/episodes/${episodeId}/retry/`, {
    method: 'POST',
  })
}

export async function translateEpisodeTitle(episodeId: string) {
  return request<Episode>(`/api/episodes/${episodeId}/translate-title/`, {
    method: 'POST',
  })
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
