from enum import Enum


class CourseStatus(str, Enum):
    SCRAPING = 'scraping'
    SCRAPED = 'scraped'
    DOWNLOADING = 'downloading'
    PROCESSING = 'processing'
    READY_FOR_UPLOAD = 'ready_for_upload'
    UPLOADING = 'uploading'
    COMPLETED = 'completed'
    ERROR = 'error'


class AssetStatus(str, Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    DOWNLOADED = 'downloaded'
    PROCESSING = 'processing'
    PROCESSED = 'processed'
    UPLOADING = 'uploading'
    UPLOADED = 'uploaded'
    ERROR = 'error'
    SKIPPED = 'skipped'
    NOT_AVAILABLE = 'not_available'


class LogLevel(str, Enum):
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class ProcessingTaskType(str, Enum):
    SCRAPE = 'scrape'
    DOWNLOAD_VIDEO = 'download_video'
    DOWNLOAD_SUBTITLE = 'download_subtitle'
    DOWNLOAD_EXERCISE = 'download_exercise'
    PROCESS_SUBTITLE = 'process_subtitle'
    AI_TRANSLATE = 'ai_translate'
    UPLOAD = 'upload'
    CLEANUP = 'cleanup'


class QueueStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'