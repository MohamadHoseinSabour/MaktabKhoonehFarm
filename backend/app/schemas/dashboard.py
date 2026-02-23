from pydantic import BaseModel


class DashboardStatsOut(BaseModel):
    total_courses: int
    active_downloads: int
    queued_tasks: int
    failed_tasks_24h: int


class CourseProgressOut(BaseModel):
    course_id: str
    total_episodes: int
    downloaded_videos: int
    processed_subtitles: int
    failed_items: int
    progress_percent: float